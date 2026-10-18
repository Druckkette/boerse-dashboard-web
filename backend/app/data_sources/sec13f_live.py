"""Incremental EDGAR filings between SEC's quarterly bulk releases.

Original complete submissions are retained as gzip files in the persistent
backend volume. Accession numbers identify immutable SEC submissions; a local
checksum is verified before reusing one. Partial quarters never become the
baseline for the broad institutional trend.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import re
import tempfile
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlencode
from xml.etree import ElementTree as ET

import pandas as pd

from app.data_sources.sec_request import sec_get

SEARCH_URL = "https://efts.sec.gov/LATEST/search-index"
SUBMISSION_COLUMNS = ["ACCESSION_NUMBER", "FILING_DATE", "SUBMISSIONTYPE", "CIK", "PERIODOFREPORT"]
HOLDING_COLUMNS = [
    "ACCESSION_NUMBER",
    "NAMEOFISSUER",
    "TITLEOFCLASS",
    "CUSIP",
    "VALUE",
    "SSHPRNAMT",
    "SSHPRNAMTTYPE",
    "PUTCALL",
]


def discover_filings(since: date, until: date, *, user_agent: str) -> list[dict]:
    """A single root form includes 13F-HR/A. Comma-separated forms do not."""
    found = {}
    offset = 0
    while True:
        url = (
            SEARCH_URL
            + "?"
            + urlencode(
                {
                    "dateRange": "custom",
                    "startdt": since.isoformat(),
                    "enddt": until.isoformat(),
                    "forms": "13F-HR",
                    "from": offset,
                    "size": 100,
                }
            )
        )
        response = sec_get(url, user_agent=user_agent, timeout=45)
        response.raise_for_status()
        result = response.json()["hits"]
        total = result["total"]["value"]
        if total >= 10000 or result["total"].get("relation") != "eq":
            # Fail explicitly rather than silently truncating a busy filing window.
            if since >= until:
                raise RuntimeError("SEC 13F search exceeds the daily result limit.")
            middle = since + (until - since) // 2
            return discover_filings(since, middle, user_agent=user_agent) + discover_filings(
                middle + timedelta(days=1), until, user_agent=user_agent
            )
        hits = result["hits"]
        for hit in hits:
            row = hit["_source"]
            accession = str(row["adsh"])
            if row.get("form") not in {"13F-HR", "13F-HR/A"}:
                continue
            if not re.fullmatch(r"\d{10}-\d{2}-\d{6}", accession):
                raise ValueError("Invalid SEC accession number")
            ciks = row.get("ciks") or []
            if len(ciks) != 1 or not str(ciks[0]).isdigit():
                raise ValueError("Ambiguous SEC filing manager")
            found[accession] = {
                "accession": accession,
                "cik": str(ciks[0]).zfill(10),
                "period": row["period_ending"],
                "filing_date": row["file_date"],
                "form": row["form"],
            }
        offset += len(hits)
        if offset >= total:
            break
        if not hits:
            raise RuntimeError("Incomplete SEC 13F search pagination")
    return sorted(found.values(), key=lambda row: (row["filing_date"], row["accession"]))


def _text(element: ET.Element, name: str, default: str = "") -> str:
    node = element.find(".//{*}" + name)
    return (node.text or "").strip() if node is not None else default


def parse_submission(content: bytes, filing: dict) -> dict:
    documents = []
    # A complete EDGAR submission contains independent XML documents, not one XML tree.
    for xml in re.findall(rb"<XML>\s*(.*?)\s*</XML>", content, flags=re.S | re.I):
        if b"<!DOCTYPE" in xml.upper() or b"<!ENTITY" in xml.upper():
            raise ValueError("Unsupported SEC XML declaration")
        documents.append(ET.fromstring(xml.strip()))
    covers = [root for root in documents if root.tag.rsplit("}", 1)[-1] == "edgarSubmission"]
    tables = [root for root in documents if root.tag.rsplit("}", 1)[-1] == "informationTable"]
    if len(covers) != 1:
        raise ValueError("SEC submission has no unique 13F cover page")
    cover = covers[0]
    period_text = _text(cover, "reportCalendarOrQuarter") or _text(cover, "periodOfReport")
    period = None
    for fmt in ("%m-%d-%Y", "%Y-%m-%d", "%m/%d/%Y"):
        try:
            period = datetime.strptime(period_text, fmt).date().isoformat()
            break
        except ValueError:
            continue
    if period != filing["period"] or _text(cover, "cik").zfill(10) != filing["cik"]:
        raise ValueError("SEC search and source document disagree")
    report_day = date.fromisoformat(period)
    next_day = report_day + timedelta(days=1)
    if report_day.month not in {3, 6, 9, 12} or next_day.day != 1 or period > filing["filing_date"]:
        raise ValueError("Invalid SEC 13F quarter end")
    amendment = _text(cover, "amendmentType").upper()
    if filing["form"] == "13F-HR/A" and amendment not in {"RESTATEMENT", "NEW HOLDINGS"}:
        raise ValueError("Unknown 13F amendment type")
    report_type = _text(cover, "reportType")
    expected = _text(cover, "tableEntryTotal")
    entries = [node for table in tables for node in table.findall(".//{*}infoTable")]
    # Some empty restatements use the SEC XML's all-zero placeholder row.
    # It does not represent a security or a holder.
    if (
        expected == "0"
        and entries
        and all(
            _text(node, "cusip") == "000000000"
            and _text(node, "value") == "0"
            and _text(node, "sshPrnamt") == "0"
            for node in entries
        )
    ):
        entries = []
    if expected and int(expected) != len(entries):
        raise ValueError(
            f"SEC information table row count mismatch: {filing['accession']} ({expected} announced, {len(entries)} found)"
        )
    if not tables and report_type != "13F NOTICE" and expected != "0":
        raise ValueError("SEC holdings table missing")
    rows = [
        {
            "ACCESSION_NUMBER": filing["accession"],
            "NAMEOFISSUER": _text(node, "nameOfIssuer"),
            "TITLEOFCLASS": _text(node, "titleOfClass"),
            "CUSIP": _text(node, "cusip"),
            "VALUE": _text(node, "value"),
            "SSHPRNAMT": _text(node, "sshPrnamt"),
            "SSHPRNAMTTYPE": _text(node, "sshPrnamtType"),
            "PUTCALL": _text(node, "putCall"),
        }
        for node in entries
    ]
    return {
        **filing,
        "amendment_type": amendment,
        "amendment_number": _text(cover, "amendmentNo", "0"),
        "holdings": rows,
    }


def _atomic_write(path: Path, content: bytes) -> None:
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
        temporary = Path(handle.name)
        handle.write(content)
    temporary.replace(path)


def load_filing(filing: dict, directory: Path, *, user_agent: str) -> dict:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (filing["accession"] + ".txt.gz")
    digest_path = path.with_suffix(".sha256")
    content = None
    if path.exists() and digest_path.exists():
        try:
            raw = gzip.decompress(path.read_bytes())
            if hashlib.sha256(raw).hexdigest() == digest_path.read_text().strip():
                content = raw
        except (OSError, EOFError):
            pass
    if content is None:
        url = f"https://www.sec.gov/Archives/edgar/data/{int(filing['cik'])}/{filing['accession'].replace('-', '')}/{filing['accession']}.txt"
        response = sec_get(url, user_agent=user_agent, timeout=60)
        response.raise_for_status()
        content = response.content
        # Validate before publishing anything into the reusable archive.
        try:
            parsed = parse_submission(content, filing)
        except ValueError as exc:
            _atomic_write(path.with_suffix(".rejected.gz"), gzip.compress(content, mtime=0))
            # Preserve a malformed as-filed source, but do not replace validated
            # holdings with an incomplete or ambiguous correction.
            return {**filing, "validation_error": str(exc), "holdings": []}
        _atomic_write(path, gzip.compress(content, mtime=0))
        _atomic_write(digest_path, hashlib.sha256(content).hexdigest().encode())
        return {**parsed, "source_sha256": hashlib.sha256(content).hexdigest()}
    try:
        parsed = parse_submission(content, filing)
    except ValueError as exc:
        # A stricter parser can also discover a problem in an earlier archive.
        _atomic_write(path.with_suffix(".rejected.gz"), gzip.compress(content, mtime=0))
        return {**filing, "validation_error": str(exc), "holdings": []}
    return {**parsed, "source_sha256": hashlib.sha256(content).hexdigest()}


def build_live_dataset(
    *, since: date, baseline: str, previous: str, cache_dir: Path, user_agent: str, progress=None
) -> tuple[Path, dict]:
    today = datetime.now(UTC).date()
    filings = discover_filings(since, today, user_agent=user_agent)
    relevant = [
        row for row in filings if row["period"] >= previous and row["period"] <= today.isoformat()
    ]
    completed = []
    excluded = []
    cache_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=cache_dir, delete=False) as handle:
        temporary = Path(handle.name)
    # The shared Redis SEC gate also limits these requests across other workers.
    try:
        with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as archive:
            # Stream millions of holdings, retaining only small filing metadata.
            # Bound pending results too: Executor.map over the entire quarter
            # otherwise retains large completed documents behind one slow request.
            with (
                archive.open("INFOTABLE.tsv", "w") as raw,
                io.TextIOWrapper(raw, encoding="utf-8", newline="") as stream,
            ):
                writer = csv.DictWriter(stream, fieldnames=HOLDING_COLUMNS, delimiter="\t")
                writer.writeheader()
                with ThreadPoolExecutor(max_workers=4) as pool:
                    index = 0
                    for offset in range(0, len(relevant), 8):
                        for parsed in pool.map(
                            lambda row: load_filing(
                                row, cache_dir / "filings", user_agent=user_agent
                            ),
                            relevant[offset : offset + 8],
                        ):
                            index += 1
                            if parsed.get("validation_error"):
                                excluded.append(
                                    {
                                        key: value
                                        for key, value in parsed.items()
                                        if key != "holdings"
                                    }
                                )
                            else:
                                writer.writerows(parsed.pop("holdings"))
                                completed.append(parsed)
                            if progress and (index % 25 == 0 or index == len(relevant)):
                                progress(
                                    24,
                                    "EDGAR-Einzelmeldungen laden",
                                    f"{index} von {len(relevant)} Einreichungen geprüft.",
                                    {
                                        "live_filings_loaded": index,
                                        "live_filings_total": len(relevant),
                                    },
                                )

            def write_table(name, columns, rows):
                stream = io.StringIO()
                writer = csv.DictWriter(stream, fieldnames=columns, delimiter="\t")
                writer.writeheader()
                writer.writerows(rows)
                archive.writestr(name, stream.getvalue())

            write_table(
                "SUBMISSION.tsv",
                SUBMISSION_COLUMNS,
                [
                    {
                        "ACCESSION_NUMBER": row["accession"],
                        "FILING_DATE": row["filing_date"],
                        "SUBMISSIONTYPE": row["form"],
                        "CIK": row["cik"],
                        "PERIODOFREPORT": row["period"],
                    }
                    for row in completed
                ],
            )
            write_table(
                "COVERPAGE.tsv",
                ["ACCESSION_NUMBER", "AMENDMENTTYPE", "AMENDMENTNO"],
                [
                    {
                        "ACCESSION_NUMBER": row["accession"],
                        "AMENDMENTTYPE": row["amendment_type"],
                        "AMENDMENTNO": row["amendment_number"],
                    }
                    for row in completed
                ],
            )
        signature = hashlib.sha256(
            json.dumps(
                {
                    "filings": completed,
                    "engine": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                },
                sort_keys=True,
            ).encode()
        ).hexdigest()
        target = cache_dir / f"live-{signature}.zip"
        if target.exists():
            temporary.unlink()
        else:
            temporary.replace(target)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    early = [row for row in completed if row["period"] > baseline]
    status = {
        "checked_at": datetime.now(UTC).isoformat(),
        "search_since": since.isoformat(),
        "discovered_count": len(filings),
        "loaded_count": len(completed),
        "latest_filing_date": max((row["filing_date"] for row in completed), default=None),
        "latest_report_period": max((row["period"] for row in completed), default=baseline),
        "preliminary_filings_count": len(early),
        "baseline_report_period": baseline,
        "preliminary_managers_count": len({row["cik"] for row in early}),
        "baseline_updates_count": sum(row["period"] == baseline for row in completed),
        "excluded_filings_count": len(excluded),
        "excluded_filings": [
            {key: row[key] for key in ("accession", "period", "validation_error")}
            for row in excluded
        ],
        "source_url": SEARCH_URL,
    }
    return target, status


def effective_submissions(indexes: list[pd.DataFrame]) -> pd.DataFrame:
    """Restatements replace, NEW HOLDINGS amendments add, duplicate files don't."""
    frame = pd.concat(indexes, ignore_index=True).drop_duplicates("ACCESSION_NUMBER")
    frame["amendment_order"] = pd.to_numeric(
        frame.get("AMENDMENTNO", pd.Series(0, index=frame.index)), errors="coerce"
    ).fillna(0)
    frame = frame.sort_values(["filing_date", "amendment_order", "ACCESSION_NUMBER"])
    selected = []
    for _, group in frame.groupby(["CIK", "period_date"]):
        current = []
        for idx, row in group.iterrows():
            amendment = str(row.get("AMENDMENTTYPE") or "").strip().upper()
            if row["SUBMISSIONTYPE"] == "13F-HR" or amendment == "RESTATEMENT":
                current = [idx]
            elif amendment == "NEW HOLDINGS":
                current.append(idx)
            else:
                raise ValueError(f"Unsupported 13F amendment: {row['ACCESSION_NUMBER']}")
        selected.extend(current)
    return frame.loc[selected]


def bulk_comparison_periods(coverage_end: date) -> tuple[str, str]:
    """Use completed, due quarters; one mistyped/future period cannot win."""
    cutoff = coverage_end - timedelta(days=45)
    start = date(cutoff.year, ((cutoff.month - 1) // 3) * 3 + 1, 1)
    current = start - timedelta(days=1)
    previous = date(current.year, ((current.month - 1) // 3) * 3 + 1, 1) - timedelta(days=1)
    return current.isoformat(), previous.isoformat()
