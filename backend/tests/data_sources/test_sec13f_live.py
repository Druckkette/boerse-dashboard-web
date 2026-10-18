from datetime import date
from types import SimpleNamespace
import csv
import io
import zipfile

import pandas as pd
import pytest

from app.data_sources import sec13f_client as bulk, sec13f_live as live


def filing(accession="0000000001-26-000001", period="2026-09-30", form="13F-HR"):
    return {
        "accession": accession,
        "period": period,
        "cik": "0000000001",
        "filing_date": "2026-10-01",
        "form": form,
    }


def submission(*, count=1, amendment="", shares=20):
    return f"""<DOCUMENT><XML><?xml version="1.0"?>
      <edgarSubmission xmlns="urn:cover"><cik>1</cik><reportCalendarOrQuarter>09-30-2026</reportCalendarOrQuarter>
      <reportType>13F HOLDINGS REPORT</reportType><amendmentType>{amendment}</amendmentType>
      <tableEntryTotal>{count}</tableEntryTotal></edgarSubmission></XML></DOCUMENT>
      <DOCUMENT><XML><informationTable xmlns="urn:holdings"><infoTable><nameOfIssuer>Apple Inc</nameOfIssuer>
      <titleOfClass>COM</titleOfClass><cusip>037833100</cusip><value>4000</value>
      <shrsOrPrnAmt><sshPrnamt>{shares}</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt>
      </infoTable></informationTable></XML></DOCUMENT>""".encode()


def test_complete_submission_parses_namespaces_and_preserves_security_values():
    row = live.parse_submission(submission(), filing())
    assert row["period"] == "2026-09-30"
    assert row["holdings"][0]["CUSIP"] == "037833100"
    assert row["holdings"][0]["SSHPRNAMT"] == "20"


def test_incomplete_or_conflicting_document_is_rejected():
    with pytest.raises(ValueError, match="row count"):
        live.parse_submission(submission(count=2), filing())
    with pytest.raises(ValueError, match="disagree"):
        live.parse_submission(submission(), filing(period="2026-06-30"))
    with pytest.raises(ValueError, match="amendment type"):
        live.parse_submission(submission(), filing(form="13F-HR/A"))


def test_filing_archive_is_verified_and_reused_without_network(tmp_path, monkeypatch):
    calls = []

    def get(*args, **kwargs):
        calls.append(args[0])
        return SimpleNamespace(content=submission(), raise_for_status=lambda: None)

    monkeypatch.setattr(live, "sec_get", get)
    first = live.load_filing(filing(), tmp_path, user_agent="test")
    assert live.load_filing(filing(), tmp_path, user_agent="test") == first
    assert len(calls) == 1
    next(tmp_path.glob("*.sha256")).write_text("broken")
    assert live.load_filing(filing(), tmp_path, user_agent="test") == first
    assert len(calls) == 2


def test_inconsistent_filing_is_archived_without_entering_aggregate(tmp_path, monkeypatch):
    monkeypatch.setattr(
        live,
        "sec_get",
        lambda *a, **kw: SimpleNamespace(
            content=submission(count=2), raise_for_status=lambda: None
        ),
    )
    result = live.load_filing(filing(), tmp_path, user_agent="test")
    assert "row count" in result["validation_error"]
    assert result["holdings"] == []
    assert len(list(tmp_path.glob("*.rejected.gz"))) == 1
    assert not list(tmp_path.glob("*.txt.gz"))


def test_revalidation_can_quarantine_previously_cached_document(tmp_path, monkeypatch):
    monkeypatch.setattr(
        live,
        "sec_get",
        lambda *a, **kw: SimpleNamespace(content=submission(), raise_for_status=lambda: None),
    )
    live.load_filing(filing(), tmp_path, user_agent="test")
    monkeypatch.setattr(
        live, "sec_get", lambda *a, **kw: pytest.fail("Cached source fetched again")
    )

    def reject(*args):
        raise ValueError("New validation rule")

    monkeypatch.setattr(live, "parse_submission", reject)
    result = live.load_filing(filing(), tmp_path, user_agent="test")
    assert result["validation_error"] == "New validation rule"
    assert result["holdings"] == []
    assert list(tmp_path.glob("*.rejected.gz"))


def test_all_zero_placeholder_is_an_empty_restatement():
    content = submission(count=0, amendment="RESTATEMENT", shares=0).replace(
        b"<cusip>037833100</cusip><value>4000</value>", b"<cusip>000000000</cusip><value>0</value>"
    )
    result = live.parse_submission(content, filing(form="13F-HR/A"))
    assert result["holdings"] == []
    assert result["amendment_type"] == "RESTATEMENT"


def test_search_paginates_root_form_including_amendments(monkeypatch):
    urls = []

    def get(url, **kwargs):
        urls.append(url)
        n = len(urls)
        row = {
            "adsh": f"0000000001-26-{n:06d}",
            "period_ending": "2026-09-30",
            "file_date": "2026-10-01",
            "ciks": ["1"],
            "form": "13F-HR" if n == 1 else "13F-HR/A",
        }
        return SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {
                "hits": {"total": {"value": 2, "relation": "eq"}, "hits": [{"_source": row}]}
            },
        )

    monkeypatch.setattr(live, "sec_get", get)
    rows = live.discover_filings(date(2026, 9, 1), date(2026, 10, 18), user_agent="test")
    assert len(rows) == 2
    assert "forms=13F-HR&" in urls[0]
    assert "from=1" in urls[1]
    assert rows[-1]["form"] == "13F-HR/A"


def test_live_zip_stream_keeps_validated_records_and_reuses_same_artifact(tmp_path, monkeypatch):
    monkeypatch.setattr(live, "discover_filings", lambda *a, **kw: [filing()])

    def load(*args, **kwargs):
        return {**live.parse_submission(submission(), filing()), "source_sha256": "test-content"}

    monkeypatch.setattr(live, "load_filing", load)
    path, status = live.build_live_dataset(
        since=date(2026, 9, 1),
        baseline="2026-06-30",
        previous="2026-03-31",
        cache_dir=tmp_path,
        user_agent="test",
    )
    before = path.stat().st_mtime_ns
    same, _ = live.build_live_dataset(
        since=date(2026, 9, 1),
        baseline="2026-06-30",
        previous="2026-03-31",
        cache_dir=tmp_path,
        user_agent="test",
    )
    assert same == path and same.stat().st_mtime_ns == before
    assert status["preliminary_filings_count"] == 1
    with zipfile.ZipFile(path) as archive:
        rows = pd.read_csv(archive.open("INFOTABLE.tsv"), sep="\t", dtype=str)
    assert rows.iloc[0]["SSHPRNAMT"] == "20"


def test_restated_holdings_replace_original_and_new_holdings_add_once():
    rows = []
    for n, form, amendment in [
        (1, "13F-HR", ""),
        (2, "13F-HR/A", "RESTATEMENT"),
        (3, "13F-HR/A", "NEW HOLDINGS"),
    ]:
        rows.append(
            {
                "ACCESSION_NUMBER": str(n),
                "CIK": "1",
                "period_date": date(2026, 6, 30),
                "filing_date": date(2026, 8, n),
                "SUBMISSIONTYPE": form,
                "AMENDMENTTYPE": amendment,
            }
        )
    frame = pd.DataFrame(rows)
    result = live.effective_submissions([frame, frame])
    assert list(result.ACCESSION_NUMBER) == ["2", "3"]


def write_zip(path, submissions, holdings):
    with zipfile.ZipFile(path, "w") as archive:
        for name, columns, rows in [
            ("SUBMISSION.tsv", live.SUBMISSION_COLUMNS, submissions),
            (
                "COVERPAGE.tsv",
                ["ACCESSION_NUMBER", "AMENDMENTTYPE"],
                [
                    {
                        "ACCESSION_NUMBER": r["ACCESSION_NUMBER"],
                        "AMENDMENTTYPE": r.get("amendment", ""),
                    }
                    for r in submissions
                ],
            ),
            ("INFOTABLE.tsv", live.HOLDING_COLUMNS, holdings),
        ]:
            stream = io.StringIO()
            writer = csv.DictWriter(
                stream, fieldnames=columns, delimiter="\t", extrasaction="ignore"
            )
            writer.writeheader()
            writer.writerows(rows)
            archive.writestr(name, stream.getvalue())


def test_early_quarter_never_replaces_full_comparison_and_amendments_update_baseline(
    tmp_path, monkeypatch
):
    def row(n, period, form="13F-HR", amendment=""):
        return {
            "ACCESSION_NUMBER": str(n),
            "CIK": "1",
            "PERIODOFREPORT": period,
            "FILING_DATE": "2026-10-01" if n >= 3 else "2026-08-01",
            "SUBMISSIONTYPE": form,
            "amendment": amendment,
        }

    def holding(n, shares):
        return {
            "ACCESSION_NUMBER": str(n),
            "NAMEOFISSUER": "Apple Inc",
            "TITLEOFCLASS": "COM",
            "CUSIP": "037833100",
            "VALUE": str(shares * 100),
            "SSHPRNAMT": str(shares),
            "SSHPRNAMTTYPE": "SH",
            "PUTCALL": "",
        }

    first, second, extra = [tmp_path / n for n in ("bulk1.zip", "bulk2.zip", "live.zip")]
    write_zip(first, [row(1, "2026-06-30")], [holding(1, 120)])
    write_zip(second, [row(2, "2026-03-31")], [holding(2, 100)])
    write_zip(
        extra,
        [
            row(3, "2026-06-30", "13F-HR/A", "RESTATEMENT"),
            row(4, "2026-06-30", "13F-HR/A", "NEW HOLDINGS"),
            row(5, "2026-09-30"),
        ],
        [holding(3, 130), holding(4, 5), holding(5, 200)],
    )
    links = [
        bulk.DatasetLink(
            "2026 June July August 13F", "https://www.sec.gov/01jun2026-31aug2026_form13f.zip"
        ),
        bulk.DatasetLink(
            "2026 March April May 13F", "https://www.sec.gov/01mar2026-31may2026_form13f.zip"
        ),
    ]
    monkeypatch.setattr(bulk, "list_sec_13f_datasets", lambda **kw: links)
    monkeypatch.setattr(
        bulk, "download_dataset", lambda link, *a, **kw: first if link == links[0] else second
    )
    monkeypatch.setattr(
        bulk,
        "fetch_sec_company_symbol_records",
        lambda *a, **kw: [bulk.SymbolRecord("AAPL", "Apple Inc")],
    )
    monkeypatch.setattr(
        live,
        "build_live_dataset",
        lambda **kw: (extra, {"checked_at": "2026-10-18", "latest_filing_date": "2026-10-01"}),
    )
    result = bulk.build_institutional_13f_payload(
        universe=["AAPL"], cache_dir=tmp_path, sec_user_agent="test"
    )
    item = result.payload["tickers"]["AAPL"]
    assert item["period"] == "2026-06-30"
    assert item["total_shares"] == 135
    assert item["previous_total_shares"] == 100
    assert item["holder_count"] == 1
    assert result.payload["preliminary_reports"]["AAPL"]["total_shares"] == 200
    assert live.bulk_comparison_periods(date(2027, 2, 28)) == ("2026-12-31", "2026-09-30")


def test_setup_distinguishes_coverage_from_stale_reporting_period():
    from app.schemas import ServiceFreshness
    from app.services.setup import _institutional_13f_step

    step = _institutional_13f_step(
        ServiceFreshness(
            name="institutional_13f",
            status="stale",
            lag_minutes=1,
            as_of="2026-06-30",
            metadata={
                "required_report_period": "2026-06-30",
                "missing_count": 10,
                "stale_count": 2,
                "next_due_date": "2026-11-16",
            },
        ),
        [],
    )
    assert "fristgerecht aktuell" in step.detail
    assert "10 Aktien ohne Daten" in step.detail
    assert "11-16" in step.detail
    assert step.job_payload["universe"] == "us_common_stocks"
