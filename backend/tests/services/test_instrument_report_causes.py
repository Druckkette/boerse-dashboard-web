from datetime import date
from types import SimpleNamespace

import pandas as pd
import pytest

from app.data_sources import fundamentals_client as client
from app.domain.stocks.instrument_type import classify_instrument, required_histories
from app.domain.stocks.assessment import evaluate_fundamentals_context
from app.repositories.fundamentals import FundamentalSnapshotWrite
from app.repositories.fundamentals import _missing_required_history_keys
from app.services import report_refresh
from app.services.report_missing_export import build_missing_rows
from app.services.report_reclassification import _cached_sec_forms
from app.services import report_reclassification


@pytest.mark.parametrize(("name", "flags", "kind"), [
    ("Eaton Vance Senior Income Trust", {}, "investment_trust"),
    ("Nuveen Municipal Income Fund", {}, "closed_end_fund"),
    ("Acme Acquisition Corp", {}, "spac"),
    ("Example Exchange Traded Note", {}, "etn"),
    ("Example Common Stock", {"etf": "Y"}, "etf"),
    ("Example Preferred Shares", {}, "preferred_stock"),
    ("Example Warrants", {}, "warrant"),
    ("Example Rights", {}, "right"),
    ("Example Units", {}, "unit"),
    ("Example Trust Certificates", {}, "structured_security"),
])
def test_structured_and_non_operating_types(name, flags, kind):
    assert classify_instrument(name=name, **flags) == kind
    assert required_histories(kind) == ()


def test_sec_forms_identify_foreign_reporting():
    assert classify_instrument(name="Global PLC", sec_forms=["20-F", "6-K"]) == "foreign_private_issuer"
    assert required_histories("foreign_private_issuer") == ("annual_eps_history", "annual_revenue_history")
    assert classify_instrument(name="Domestic Inc", sec_forms=["10-K", "10-Q"]) == "operating_company"
    assert classify_instrument(name="Migrated PLC", sec_forms=["20-F", "10-K"]) == "unknown"
    assert classify_instrument(ticker="FNGD", name="FNGD") == "etn"
    assert classify_instrument(ticker="AAC", name="AAC") == "spac"
    assert classify_instrument(ticker="AAC", name="Operating Business Inc", sec_forms=["10-K"]) == "operating_company"
    assert classify_instrument(name="Unit Corporation", sec_forms=["10-K"]) == "operating_company"
    assert classify_instrument(name="MicroSectors Leveraged ETNs due 2038") == "etn"
    assert classify_instrument(name="Synthetic Fixed-Income Securities Inc STRATS") == "structured_security"
    assert classify_instrument(name="PPlus Tr GSC-2 Tr Ctf Fltg Rate") == "structured_security"
    assert classify_instrument(name="StoneBridge Acquisition II Corporation") == "spac"
    assert classify_instrument(name="Archimedes Tech SPAC Partners II Co") == "spac"
    assert classify_instrument(name="Graf Global Corp. Class A ordinary shares",
                               sec_sic="6770", sec_forms=["10-Q"]) == "spac"
    assert classify_instrument(name="Graf Global Corp. Class A ordinary shares",
                               sec_sic="8742", sec_forms=["10-Q"]) == "operating_company"
    assert classify_instrument(name="BlackRock Resources Inc", sec_forms=["N-CSR", "N-CEN"],
                               previous_type="operating_company") == "closed_end_fund"
    assert classify_instrument(name="BlackRock Income Trust Inc", sec_forms=["N-CSRS"]) == "investment_trust"


def test_backfill_reads_foreign_forms_from_existing_companyfacts():
    facts = {"us-gaap": {"EarningsPerShareDiluted": {"units": {"USD/shares": [
        {"form": "20-F", "filed": "2026-05-20"},
        {"form": "6-K", "filed": "2026-08-01"},
    ]}}}}
    forms, latest_annual = _cached_sec_forms(facts)
    assert forms == ["20-F", "6-K"]
    assert latest_annual == "20-F"


def test_sec_sic_verification_requires_same_cik(monkeypatch):
    row = SimpleNamespace(metadata_json={"primary_cik": "0001897463"})
    commits = []

    class FakeDB:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def scalar(self, _query):
            return row

        def commit(self):
            commits.append(True)

    monkeypatch.setattr(report_reclassification, "SessionLocal", FakeDB)
    monkeypatch.setattr("app.services.settings.get_runtime_config_value", lambda key: "agent")
    payload = {"cik": 1897463, "sic": "6770", "sicDescription": "Blank Checks"}
    response = SimpleNamespace(json=lambda: payload, raise_for_status=lambda: None)
    monkeypatch.setattr("app.data_sources.sec_request.sec_get", lambda *a, **k: response)
    assert report_reclassification.verify_sec_sic("TONT")["sec_sic"] == "6770"
    assert row.metadata_json["sec_sic_cik"] == "0001897463"
    assert len(commits) == 1
    payload["cik"] = 9999999
    with pytest.raises(ValueError, match="CIK mismatch"):
        report_reclassification.verify_sec_sic("TONT")
    assert len(commits) == 1


def test_sec_submissions_forms_identify_fund_without_sic(monkeypatch):
    row = SimpleNamespace(metadata_json={"primary_cik": "0001234567"})

    class FakeDB:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def scalar(self, _query):
            return row

        def commit(self):
            pass

    monkeypatch.setattr(report_reclassification, "SessionLocal", FakeDB)
    monkeypatch.setattr("app.services.settings.get_runtime_config_value", lambda key: "agent")
    payload = {"cik": 1234567, "filings": {"recent": {"form": ["N-CSR", "N-CEN"]}}}
    response = SimpleNamespace(json=lambda: payload, raise_for_status=lambda: None)
    monkeypatch.setattr("app.data_sources.sec_request.sec_get", lambda *a, **k: response)
    result = report_reclassification.verify_sec_registrant("TEST")
    assert result["sec_forms"] == ["N-CEN", "N-CSR"]
    assert classify_instrument(name="Example Inc", sec_forms=row.metadata_json["sec_forms"]) == "closed_end_fund"

def test_non_operating_report_skips_all_statement_providers(monkeypatch):
    previous = FundamentalSnapshotWrite("EVF", date.today(), metadata_json={})
    writes = []
    monkeypatch.setattr(report_refresh.fundamentals, "get_latest_fundamentals", lambda ticker: previous)
    monkeypatch.setattr(report_refresh.fundamentals, "get_instrument_profile", lambda ticker: {
        "name": "Eaton Vance Senior Income Trust", "asset_class": "stock", "metadata": {}})
    monkeypatch.setattr(report_refresh.fundamentals, "upsert_fundamentals", lambda write: writes.append(write) or write)
    monkeypatch.setattr(report_refresh.fundamentals, "save_instrument_classification", lambda *a, **k: None)
    monkeypatch.setattr(report_refresh, "fetch_fundamental_enrichment", lambda *a, **k: pytest.fail("provider called"))
    monkeypatch.setattr(report_refresh, "record_provider_event", lambda *a, **k: None)
    result = report_refresh.refresh_report_group("EVF", "statements", {})
    assert result["complete"] and result["reason_code"] == "not_applicable_for_instrument_type"
    assert writes[0].metadata_json["instrument_type"] == "investment_trust"


def test_spac_waits_for_reclassification_without_growth_fetch(monkeypatch):
    monkeypatch.setattr(report_refresh.fundamentals, "get_latest_fundamentals", lambda ticker: None)
    monkeypatch.setattr(report_refresh.fundamentals, "get_instrument_profile", lambda ticker: {
        "name": "Aardvark Acquisition Corp", "asset_class": "stock", "metadata": {}})
    monkeypatch.setattr(report_refresh, "fetch_fundamental_enrichment", lambda *a, **k: pytest.fail("provider called"))
    monkeypatch.setattr(report_refresh, "record_provider_event", lambda *a, **k: None)
    monkeypatch.setattr(report_refresh.fundamentals, "save_instrument_classification", lambda *a, **k: None)
    result = report_refresh.refresh_report_group("AAC", "statements", {})
    assert result["reason_code"] == "spac_no_operating_history"


def test_foreign_filer_annual_history_is_sufficient(monkeypatch):
    years = [2022, 2023, 2024, 2025]
    annual = pd.Series({pd.Timestamp(f"{year}-12-31"): float(year - 2020) for year in years})
    enrichment = client.compute_fundamental_enrichment("FPI", {
        "AnnualDilutedEPS": annual, "AnnualTotalRevenue": annual * 100,
    })
    enrichment = client.replace(enrichment, metadata={**enrichment.metadata,
        "instrument_type": "foreign_private_issuer", "statement_diagnostics": {"forms_seen": ["20-F", "6-K"]}})
    monkeypatch.setattr(report_refresh.fundamentals, "get_latest_fundamentals", lambda ticker: None)
    monkeypatch.setattr(report_refresh.fundamentals, "get_instrument_profile", lambda ticker: {
        "name": "Global PLC", "asset_class": "stock", "metadata": {"sec_forms": ["20-F", "6-K"]}})
    monkeypatch.setattr(report_refresh.fundamentals, "save_instrument_classification", lambda *a, **k: None)
    monkeypatch.setattr(report_refresh, "fetch_fundamental_enrichment", lambda *a, **k: enrichment)
    monkeypatch.setattr(report_refresh.fundamentals, "upsert_fundamentals", lambda write: write)
    result = report_refresh.refresh_report_group("FPI", "statements", {})
    assert result["complete"]
    assert result["reason_code"] == "foreign_filer_reporting_structure"


def test_complete_foreign_annual_snapshot_preserves_sec_provenance_without_fallback(monkeypatch):
    annual = pd.Series({pd.Timestamp(f"{year}-12-31"): float(year - 2020)
                        for year in range(2022, 2026)})
    saved = client.compute_fundamental_enrichment("FPI", {
        "AnnualDilutedEPS": annual, "AnnualTotalRevenue": annual * 100,
    }).metadata
    previous = {"enrichment": saved, "instrument_type": "foreign_private_issuer",
                "listing_date": "2021-01-01", "data_sources": {"eps": "sec_bulk_cache", "revenue": "sec_bulk_cache"},
                "statement_diagnostics": {"forms_seen": ["20-F"], "latest_annual_form": "20-F",
                                          "primary_cik": "0000000001", "sec_ciks": ["0000000001"]}}
    monkeypatch.setattr(client, "fetch_quarterly_sec_companyfacts", lambda *a, **k: pytest.fail("SEC called"))
    monkeypatch.setattr(client, "fetch_yfinance_statement_history", lambda *a: pytest.fail("Yahoo called"))
    monkeypatch.setattr(client, "fetch_quarterly_fmp", lambda *a, **k: pytest.fail("FMP called"))
    monkeypatch.setattr(client, "record_provider_event", lambda *a, **k: None)
    result = client.fetch_fundamental_enrichment("FPI", sec_user_agent="agent", fmp_api_key="key",
                                                 previous_metadata=previous)
    assert result.metadata["listing_date"] == "2021-01-01"
    assert result.metadata["primary_cik"] == "0000000001"
    assert result.metadata["data_sources"]["revenue"] == "sec_bulk_cache"
    assert result.metadata["fallbacks_used"] == []


def test_diagnostic_only_rechecks_sec_even_with_complete_local_raw(monkeypatch):
    quarter = pd.Series({pd.Timestamp(f"{year}-{month:02d}-28"): 2.0
                         for year in range(2021, 2026) for month in (3, 6, 9, 12)})
    annual = pd.Series({pd.Timestamp(f"{year}-12-31"): 8.0 for year in range(2021, 2026)})
    saved = client.compute_fundamental_enrichment("TEST", {
        "DilutedEPS": quarter, "TotalRevenue": quarter * 100,
        "AnnualDilutedEPS": annual, "AnnualTotalRevenue": annual * 100,
        "NetIncome": quarter * 1000, "AnnualStockholdersEquity": annual * 10000,
    }).metadata
    calls = []
    monkeypatch.setattr(client, "fetch_quarterly_sec_companyfacts", lambda *a, **k: (
        calls.append(k) or {"DilutedEPS": quarter}, "SEC sec_bulk_cache currency=USD"))
    monkeypatch.setattr(client, "fetch_yfinance_statement_history", lambda *a: pytest.fail("Yahoo called"))
    monkeypatch.setattr(client, "fetch_quarterly_fmp", lambda *a, **k: pytest.fail("FMP called"))
    client.fetch_fundamental_enrichment("TEST", sec_user_agent="agent", fmp_api_key="key",
                                        previous_metadata={"enrichment": saved},
                                        refresh_sec=True, allow_fallbacks=False)
    assert len(calls) == 1


def test_report_diagnostic_only_requests_sec_and_disables_fallbacks(monkeypatch):
    previous = FundamentalSnapshotWrite("TEST", date.today(), metadata_json={"instrument_type": "operating_company"})
    captured = {}
    monkeypatch.setattr(report_refresh.fundamentals, "get_latest_fundamentals", lambda ticker: previous)
    monkeypatch.setattr(report_refresh.fundamentals, "get_instrument_profile", lambda ticker: {})

    def fetch(*_args, **kwargs):
        captured.update(kwargs)
        return client.FundamentalEnrichment(metadata={"reason_code": "waiting_sec_data"})

    monkeypatch.setattr(report_refresh, "fetch_fundamental_enrichment", fetch)
    report_refresh.refresh_report_group("TEST", "statements", {"diagnostic_only": True})
    assert captured["refresh_sec"] is True
    assert captured["allow_fallbacks"] is False


def test_young_issuer_and_rate_limit_have_separate_causes():
    metadata = {"instrument_type": "operating_company", "listing_date": "2025-01-01",
        "statement_diagnostics": {"forms_seen": ["10-Q", "10-K"]},
        "series_lengths": {"AnnualDilutedEPS": 2, "AnnualTotalRevenue": 2,
                           "DilutedEPS": 3, "TotalRevenue": 3}}
    assert report_refresh.history_gap_reason(metadata, ["eps_quarter_history"]) == "insufficient_operating_history"
    assert report_refresh.history_gap_reason(metadata, ["eps_quarter_history"], "provider_rate_limited") == "provider_rate_limited"
    metadata.pop("listing_date")
    assert report_refresh.history_gap_reason(metadata, ["eps_quarter_history"]) == "insufficient_operating_history"


def test_recent_peer_statement_with_stale_eps_is_technical_gap():
    metadata = {"instrument_type": "operating_company", "statement_diagnostics": {
        "forms_seen": ["10-K", "10-Q"],
        "quarterly_latest_end": {"DilutedEPS": "2020-06-30", "TotalRevenue": date.today().isoformat()},
    }}
    assert report_refresh.history_gap_reason(metadata, ["eps_quarter_history"]) == "unsupported_taxonomy"


def test_available_for_sale_tags_are_not_revenue_candidates():
    facts = {"us-gaap": {"AvailableForSaleSecurities": {"units": {"USD": [
        {"form": "10-K", "filed": "2025-02-01", "end": "2024-12-31", "val": 100},
    ]}}}}
    diagnostics = client._sec_fact_diagnostics(facts, {}, currency="USD")
    assert diagnostics["relevant_xbrl_concepts"]["TotalRevenue"] == []


def test_normal_us_filer_has_four_complete_comparison_histories():
    quarter_ends = pd.date_range("2021-03-31", periods=20, freq="QE-DEC")
    annual_ends = pd.date_range("2021-12-31", periods=5, freq="YE-DEC")
    quarter = pd.Series({end: float(index + 1) for index, end in enumerate(quarter_ends)})
    annual = pd.Series({end: float(index + 1) for index, end in enumerate(annual_ends)})
    enriched = client.compute_fundamental_enrichment("USCO", {
        "DilutedEPS": quarter, "TotalRevenue": quarter * 100,
        "AnnualDilutedEPS": annual, "AnnualTotalRevenue": annual * 100,
    })
    assert not _missing_required_history_keys({**enriched.metadata, "instrument_type": "operating_company"})


def test_sec_429_stops_yahoo_and_fmp(monkeypatch):
    monkeypatch.setattr(client, "fetch_quarterly_sec_companyfacts", lambda *a, **k: (None, "SEC rate_limited: HTTP 429"))
    monkeypatch.setattr(client, "fetch_yfinance_statement_history", lambda *a: pytest.fail("Yahoo called"))
    monkeypatch.setattr(client, "fetch_quarterly_fmp", lambda *a, **k: pytest.fail("FMP called"))
    monkeypatch.setattr(client, "record_provider_event", lambda *a, **k: None)
    result = client.fetch_fundamental_enrichment("USCO", sec_user_agent="agent", fmp_api_key="key")
    assert result.metadata["reason_code"] == "provider_rate_limited"
    assert result.metadata["fallbacks_used"] == []


def test_export_explains_non_applicable_instrument():
    rows = build_missing_rows([{"ticker": "EVF", "data_group": "statements", "status": "current",
                                "result_json": {"reason_code": "not_applicable_for_instrument_type"},
                                "payload_json": {}, "error": ""}],
                              {"EVF": {"instrument_type": "closed_end_fund", "metadata_json": {}}}, {})
    assert len(rows) == 1
    assert rows[0][2] == "not_applicable_for_instrument_type"
    assert rows[0][10] == "Closed-End Fund"
    assert rows[0][15] == "Keine weitere Abfrage notwendig"


def test_assessment_does_not_flag_inapplicable_or_foreign_quarters():
    checks, score, available = evaluate_fundamentals_context({"instrument_type": "closed_end_fund"})
    assert not available and score == 50.0
    assert len(checks) == 1 and checks[0].passed
    checks, _, _ = evaluate_fundamentals_context({"instrument_type": "foreign_private_issuer"})
    assert not any("Quartale" in check.label for check in checks)


def test_xom_predecessor_facts_merge_with_successor(monkeypatch):
    assert client.SEC_SUCCESSORS["XOM"]["predecessor_ciks"] == ["0000034088"]
    monkeypatch.setattr(client, "_sec_cik_map", lambda *a: {"XOM": "0002115436"})

    def payload(end, start, value):
        return {"facts": {"us-gaap": {
            "EarningsPerShareDiluted": {"units": {"USD/shares": [{
                "form": "10-Q", "fp": "Q2", "filed": end, "start": start, "end": end, "val": value}]}},
            "RevenueFromContractWithCustomerExcludingAssessedTax": {"units": {"USD": [{
                "form": "10-Q", "fp": "Q2", "filed": end, "start": start, "end": end, "val": value * 100}]}},
        }}}

    calls = []
    def load(cik, *_args, **_kwargs):
        calls.append(cik)
        return (payload("2026-06-30", "2026-04-01", 2) if cik == "0002115436" else
                payload("2025-06-30", "2025-04-01", 1)), "sec_bulk_cache"
    monkeypatch.setattr(client, "load_companyfacts", load)
    raw, _ = client.fetch_quarterly_sec_companyfacts("XOM", "agent")
    assert calls == ["0002115436", "0000034088"]
    assert len(raw["DilutedEPS"]) == 2
    assert raw["_sec_diagnostics"]["sec_ciks"] == calls
    assert client.quarterly_yoy_growth(raw, "eps")[0].growth_pct == 100.0


def test_unmapped_revenue_tag_is_diagnosed_without_inventing_a_total(monkeypatch):
    monkeypatch.setattr(client, "_sec_cik_map", lambda *a: {"TEST": "0000000001"})
    facts = {"facts": {"us-gaap": {"SalesRevenueGoodsNet": {"units": {"USD": [{
        "form": "10-K", "fp": "FY", "filed": "2026-02-01", "start": "2025-01-01",
        "end": "2025-12-31", "val": 100,
    }]}}}}}
    monkeypatch.setattr(client, "load_companyfacts", lambda *a, **k: (facts, "sec_bulk_cache"))
    raw, note = client.fetch_quarterly_sec_companyfacts("TEST", "agent")
    assert "unsupported_taxonomy" in note
    assert "TotalRevenue" not in raw
    assert "us-gaap:SalesRevenueGoodsNet" in raw["_sec_diagnostics"]["relevant_xbrl_concepts"]["TotalRevenue"]
    assert raw["_sec_diagnostics"]["revenue_concept"] is None


@pytest.mark.parametrize("reason_code", ["provider_error", "provider_rate_limited"])
def test_provider_error_keeps_complete_snapshot(monkeypatch, reason_code):
    old = FundamentalSnapshotWrite("TEST", date.today(),
        metadata_json={"eps_quarter_history": [{"current": 2, "previous": 1}] * 3,
                       "annual_eps_history": [{"current": 2, "previous": 1}] * 3,
                       "revenue_quarter_history": [{"current": 2, "previous": 1}] * 3,
                       "annual_revenue_history": [{"current": 2, "previous": 1}] * 3})
    monkeypatch.setattr(report_refresh.fundamentals, "get_latest_fundamentals", lambda ticker: old)
    monkeypatch.setattr(report_refresh.fundamentals, "get_instrument_profile", lambda ticker: {})
    monkeypatch.setattr(report_refresh, "fetch_fundamental_enrichment", lambda *a, **k: client.FundamentalEnrichment(
        metadata={"reason_code": reason_code}))
    monkeypatch.setattr(report_refresh.fundamentals, "upsert_fundamentals", lambda write: pytest.fail("snapshot overwritten"))
    result = report_refresh.refresh_report_group("TEST", "statements", {})
    assert not result["complete"] and not result["changed"]
    assert result["reason_code"] == reason_code
