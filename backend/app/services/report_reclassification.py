"""Idempotent, provider-free reclassification of the stored stock universe."""
from __future__ import annotations

from collections import Counter
import csv
import json
import re
from io import StringIO
from datetime import UTC, datetime, timedelta
import zipfile

from sqlalchemy import select

from app.db.models import FundamentalSnapshot, Instrument, RefreshWorkItem, Universe, UniverseMember
from app.db.session import SessionLocal
from app.domain.stocks.instrument_type import classify_instrument, inapplicable_reason
from app.repositories.fundamentals import _missing_required_history_keys, _metadata_history, _usable_history_count
from app.services.report_refresh import history_gap_reason
from app.data_sources.provider_usage import capture_provider_usage


def verify_sec_registrant(ticker: str) -> dict:
    """Persist official SEC SIC and filing forms after matching the registrant CIK."""
    from app.core_config import get_settings
    from app.data_sources.fundamentals_client import _sec_cik_map
    from app.data_sources.sec_request import sec_get
    from app.services.settings import get_runtime_config_value

    clean = ticker.strip().upper()
    with SessionLocal() as db:
        instrument = db.scalar(select(Instrument).where(Instrument.ticker == clean))
        if instrument is None:
            raise ValueError(f"Unknown ticker: {clean}")
        metadata = instrument.metadata_json or {}
        agent = get_runtime_config_value("SEC_USER_AGENT") or get_settings().sec_user_agent
        cik = str(metadata.get("primary_cik") or _sec_cik_map(agent, 15).get(clean) or "").zfill(10)
        if not cik.isdigit() or cik == "0000000000":
            raise ValueError(f"No verified SEC CIK for {clean}")
        url = f"https://data.sec.gov/submissions/CIK{cik}.json"
        response = sec_get(url, user_agent=agent, timeout=15)
        response.raise_for_status()
        payload = response.json()
        if str(payload.get("cik") or "").zfill(10) != cik:
            raise ValueError(f"SEC CIK mismatch for {clean}")
        sic = str(payload.get("sic") or "")
        recent = ((payload.get("filings") or {}).get("recent") or {})
        forms = sorted({str(form).upper().removesuffix("/A") for form in recent.get("form") or []
                        if isinstance(form, str)} | set(metadata.get("sec_forms") or []))
        verified = {"primary_cik": cik, "sec_forms": forms,
                    "sec_filing_checked_at": datetime.now(UTC).isoformat(),
                    "sec_filing_evidence": url}
        if sic.isdigit():
            verified.update({"sec_sic": sic, "sec_sic_description": payload.get("sicDescription") or "",
                             "sec_sic_cik": cik, "sec_sic_checked_at": datetime.now(UTC).isoformat(),
                             "sec_sic_evidence": url})
        instrument.metadata_json = {**metadata, **verified}
        db.commit()
    return {"ticker": clean, "primary_cik": cik, "sec_sic": sic,
            "sic_description": payload.get("sicDescription") or "", "sec_forms": forms, "evidence": url}


def verify_sec_sic(ticker: str) -> dict:
    """Verify a SEC SIC; retained for callers that require a numeric SIC."""
    result = verify_sec_registrant(ticker)
    if not result["sec_sic"].isdigit():
        raise ValueError(f"SEC SIC missing for {ticker.strip().upper()}")
    return result


def verify_suspected_fund_filings(*, limit: int = 150) -> dict:
    """Check ambiguous, still-open fund-like rows against SEC submissions once.

    This narrow probe uses the SEC ticker index and registrant filings. A name
    only selects candidates; N-CSR/N-CSRS is required for classification.
    Successful checks are timestamped so a rerun resumes with unchecked rows.
    """
    with SessionLocal() as db:
        rows = db.execute(select(Instrument.ticker, Instrument.name, Instrument.metadata_json,
                                 RefreshWorkItem.result_json)
                          .join(RefreshWorkItem, RefreshWorkItem.ticker == Instrument.ticker)
                          .where(RefreshWorkItem.data_group == "statements",
                                 RefreshWorkItem.status.in_(("waiting_source", "error", "queued")))
                          .order_by(Instrument.ticker)).all()
    candidates = []
    for ticker, name, metadata, result in rows:
        saved = metadata or {}
        if saved.get("sec_filing_checked_at") or inapplicable_reason(saved.get("instrument_type", "")):
            continue
        title = (name or "").lower()
        if ((result or {}).get("reason_code") == "provider_error" or
                re.search(r"\btrust\b|shares of beneficial", title) or
                title.startswith(("blackrock", "gabelli", "general american investors", "central securities"))):
            candidates.append(ticker)
    counts: Counter = Counter()
    errors = []
    for ticker in candidates[:max(1, min(limit, 500))]:
        try:
            result = verify_sec_registrant(ticker)
            counts["verified"] += 1
            if set(result["sec_forms"]) & {"N-CSR", "N-CSRS"}:
                counts["fund_filings_found"] += 1
        except Exception as exc:
            counts["errors"] += 1
            if len(errors) < 10:
                errors.append({"ticker": ticker, "error": type(exc).__name__})
    return {**dict(counts), "candidates": len(candidates), "errors_sample": errors}


def _cached_sec_forms(facts: dict) -> tuple[list[str], str | None]:
    """Read filing forms from existing XBRL facts without requesting a company."""
    from app.data_sources.fundamentals_client import SEC_CONCEPTS, SEC_FORMS

    seen: set[str] = set()
    annual: dict[str, str] = {}
    for taxonomy, concepts in ((tax, names) for by_tax in SEC_CONCEPTS.values()
                               for tax, names in by_tax.items()):
        namespace = (facts.get(taxonomy) or {})
        for concept in concepts:
            for entries in ((namespace.get(concept) or {}).get("units") or {}).values():
                for entry in entries:
                    form = str(entry.get("form") or "").removesuffix("/A")
                    if form not in SEC_FORMS:
                        continue
                    seen.add(form)
                    if form in {"10-K", "20-F", "40-F"} and entry.get("filed"):
                        annual[form] = max(annual.get(form, ""), str(entry["filed"]))
    latest = max(annual, key=annual.get) if annual else None
    return sorted(seen), latest


def enrich_stored_instrument_evidence() -> dict:
    """Attach two bulk exchange lists and locally cached SEC forms to legacy rows.

    The stored universe membership is untouched. Missing SEC archive members do
    not trigger live per-ticker requests.
    """
    from app.core_config import get_settings
    from app.data_sources.fundamentals_client import _sec_cik_map, SEC_SUCCESSORS
    from app.data_sources.nasdaq_trader import fetch_us_common_stock_universe
    from app.data_sources.sec_companyfacts_cache import cache_dir
    from app.services.settings import get_runtime_config_value

    listing = fetch_us_common_stock_universe()
    details = listing.instruments or {}
    archive_path = cache_dir() / "companyfacts.zip"
    sec_map: dict[str, str] = {}
    sec_error = ""
    agent = get_runtime_config_value("SEC_USER_AGENT") or get_settings().sec_user_agent
    if archive_path.is_file() and agent:
        try:
            sec_map = _sec_cik_map(agent, 15)
        except Exception as exc:
            sec_error = type(exc).__name__
    elif not archive_path.is_file():
        sec_error = "bulk_archive_unavailable"
    else:
        sec_error = "sec_user_agent_unavailable"

    counts: Counter = Counter()
    with SessionLocal() as db:
        members = db.scalars(select(Instrument).join(UniverseMember, UniverseMember.instrument_id == Instrument.id)
                             .join(Universe, Universe.id == UniverseMember.universe_id)
                             .where(Universe.key == "us_common_stocks", UniverseMember.valid_to.is_(None))
                             .order_by(Instrument.ticker)).all()
        waiting = set(db.scalars(select(RefreshWorkItem.ticker).where(
            RefreshWorkItem.data_group == "statements",
            RefreshWorkItem.status.in_(("waiting_source", "error", "queued")))).all())
        archive = zipfile.ZipFile(archive_path) if sec_map else None
        try:
            for instrument in members:
                ticker = instrument.ticker
                old = instrument.metadata_json or {}
                detail = details.get(ticker) or {}
                new = dict(old)
                if detail:
                    new["nasdaq_listing"] = detail
                    if detail.get("name") and (instrument.name == ticker or
                                                instrument.name == (old.get("nasdaq_listing") or {}).get("name")):
                        instrument.name = detail["name"][:255]
                    counts["nasdaq_listings_found"] += 1
                if archive and ticker in waiting and ticker in sec_map:
                    cik = SEC_SUCCESSORS.get(ticker, {}).get("primary_cik") or sec_map[ticker]
                    if old.get("sec_sic_cik") and old["sec_sic_cik"] != cik:
                        for key in ("sec_sic", "sec_sic_description", "sec_sic_cik",
                                    "sec_sic_checked_at", "sec_sic_evidence"):
                            new.pop(key, None)
                    try:
                        with archive.open(f"CIK{cik}.json") as source:
                            facts = (json.load(source).get("facts") or {})
                        forms, latest_annual = _cached_sec_forms(facts)
                        if forms:
                            new["sec_forms"] = sorted(set(forms) | {form for form in old.get("sec_forms") or []
                                                                       if form in {"N-CSR", "N-CSRS"}})
                            new["sec_latest_annual_form"] = latest_annual
                            new["primary_cik"] = cik
                            counts["sec_forms_found"] += 1
                    except (KeyError, ValueError, OSError):
                        counts["sec_archive_misses"] += 1
                if new != old:
                    instrument.metadata_json = new
                counts["instruments_seen"] += 1
            db.commit()
        finally:
            if archive:
                archive.close()
    return {**dict(counts), "sec_evidence_error": sec_error,
            "nasdaq_sources": [listing.metadata.get("nasdaq_source_url"),
                               listing.metadata.get("nyse_source_url")]}


def reclassify_batch(*, after_ticker: str = "", limit: int = 250) -> dict:
    """Process a stable ticker page; call again with next_cursor until done."""
    now = datetime.now(UTC)
    limit = max(1, min(limit, 1000))
    counts: Counter = Counter()
    with SessionLocal() as db:
        tickers = db.scalars(
            select(Instrument.ticker).join(UniverseMember, UniverseMember.instrument_id == Instrument.id)
            .join(Universe, Universe.id == UniverseMember.universe_id)
            .where(Universe.key == "us_common_stocks", UniverseMember.valid_to.is_(None),
                   Instrument.ticker > after_ticker)
            .distinct().order_by(Instrument.ticker).limit(max(1, min(limit, 1000)))
        ).all()
        if not tickers:
            return {"processed": 0, "next_cursor": None, "counts": {}}
        instruments = {row.ticker: row for row in db.scalars(select(Instrument).where(Instrument.ticker.in_(tickers)))}
        snapshots = db.scalars(select(FundamentalSnapshot).where(FundamentalSnapshot.ticker.in_(tickers))
                               .distinct(FundamentalSnapshot.ticker)
                               .order_by(FundamentalSnapshot.ticker, FundamentalSnapshot.as_of.desc(),
                                         FundamentalSnapshot.updated_at.desc())).all()
        latest = {snapshot.ticker: snapshot for snapshot in snapshots}
        work = {row.ticker: row for row in db.scalars(select(RefreshWorkItem).where(
            RefreshWorkItem.ticker.in_(tickers), RefreshWorkItem.data_group == "statements"))}
        for ticker in tickers:
            instrument = instruments[ticker]
            saved = instrument.metadata_json or {}
            snapshot = latest.get(ticker)
            metadata = snapshot.metadata_json or {} if snapshot else {}
            diagnostics = metadata.get("statement_diagnostics") or {}
            latest_annual = diagnostics.get("latest_annual_form") or saved.get("sec_latest_annual_form")
            forms = ([latest_annual] if latest_annual else
                     diagnostics.get("forms_seen") or saved.get("sec_forms") or [])
            forms = list(dict.fromkeys([*forms, *(form for form in saved.get("sec_forms") or []
                                            if form in {"N-CSR", "N-CSRS"})]))
            listing = saved.get("nasdaq_listing") or {}
            kind = classify_instrument(ticker=ticker, name=instrument.name, asset_class=instrument.asset_class,
                                       etf=str(listing.get("etf") or ""),
                                       nextshares=str(listing.get("nextshares") or ""),
                                       sec_sic=saved.get("sec_sic") or "",
                                       sec_forms=forms, previous_type=saved.get("instrument_type", ""))
            if kind == "unknown":
                kind = metadata.get("instrument_type") or "unknown"
            if saved.get("instrument_type") != kind:
                instrument.metadata_json = {**saved, "instrument_type": kind,
                                            "classification_source": ("sec_submissions" if saved.get("sec_sic") == "6770" or
                                                                      set(forms) & {"N-CSR", "N-CSRS"}
                                                                      else "backfill_existing_evidence"),
                                            "sec_forms": forms}
                counts["types_changed"] += 1
            if snapshot and metadata.get("instrument_type") != kind:
                snapshot.metadata_json = {**metadata, "instrument_type": kind}
                metadata = snapshot.metadata_json
            row = work.get(ticker)
            missing = _missing_required_history_keys({**metadata, "instrument_type": kind})
            stale_current_reason = bool(row and ((row.result_json or {}).get("reason_code") or row.error))
            if row and _normalize_complete_current_row(row, kind, missing, metadata):
                if stale_current_reason:
                    counts["complete_current_rows_normalized"] += 1
                counts[kind] += 1
                continue
            reason = inapplicable_reason(kind)
            if not reason and row and row.status != "running":
                previous_reason = (row.result_json or {}).get("reason_code", "")
                reason = history_gap_reason(metadata, missing, previous_reason)
                if kind == "foreign_private_issuer" and not missing:
                    reason = "foreign_filer_reporting_structure"
            if row and row.status != "running" and reason:
                old_reason = (row.result_json or {}).get("reason_code")
                old_status = row.status
                if old_reason != reason:
                    counts["reasons_changed"] += 1
                row.result_json = {**(row.result_json or {}), "reason_code": reason,
                                   "instrument_type": kind, "complete": not missing,
                                   "reason": "Bestandsdaten anhand vorhandener Merkmale neu klassifiziert."}
                if inapplicable_reason(kind) or (kind == "foreign_private_issuer" and not missing):
                    row.status = "current"
                    if old_status != "current" or old_reason != reason:
                        row.due_at = now + timedelta(days=90 if kind == "spac" else 365)
                        counts["unnecessary_retries_disabled"] += 1
                        if inapplicable_reason(kind):
                            counts["avoided_fmp_fallbacks"] += 1
                            counts["avoided_yahoo_fallbacks"] += 1
                            counts["avoided_sec_requests"] += 1
                    row.error = ""
                elif _needs_first_operating_diagnostic(kind, metadata, missing, row.payload_json or {}):
                    row.status = "queued"
                    row.due_at = now
                    row.priority = min(row.priority, 20)
                    row.payload_json = {**(row.payload_json or {}), "diagnostic_only": True}
                    counts["operating_diagnostics_queued"] += 1
                elif ticker == "XOM" and not metadata.get("predecessor_ciks") and not (
                        row.payload_json or {}).get("diagnostic_only"):
                    row.status = "queued"
                    row.due_at = now
                    row.priority = min(row.priority, 20)
                    row.payload_json = {**(row.payload_json or {}), "diagnostic_only": True}
                    counts["predecessor_diagnostics_queued"] += 1
            counts[kind] += 1
        db.commit()
        return {"processed": len(tickers), "next_cursor": tickers[-1] if len(tickers) == limit else None,
                "counts": dict(counts)}


def _older_operating_gap(metadata: dict) -> bool:
    return all(_usable_history_count(_metadata_history(metadata, key)) >= 3
               for key in ("annual_eps_history", "annual_revenue_history")) and any(
        _usable_history_count(_metadata_history(metadata, key)) < 3
        for key in ("eps_quarter_history", "revenue_quarter_history"))


def _needs_first_operating_diagnostic(kind: str, metadata: dict, missing: list[str], payload: dict) -> bool:
    """Queue a cached SEC diagnosis once; regular filing checks remain separate."""
    return (kind in {"operating_company", "unknown"} and bool(missing) and
            not payload.get("diagnostic_only") and _older_operating_gap(metadata))


def _normalize_complete_current_row(row: RefreshWorkItem, kind: str, missing: list[str], metadata: dict) -> bool:
    """Keep a complete operating snapshot free of stale gap/error codes."""
    if (row.status != "current" or missing or kind not in {"operating_company", "unknown"} or
            metadata.get("predecessor_ciks")):
        return False
    result = row.result_json or {}
    if result.get("reason_code") or row.error:
        row.result_json = {**result, "reason_code": "", "complete": True,
                           "reason": "Vollständige vergleichbare Berichtshistorie vorhanden."}
        row.error = ""
    return True


def problem_counts() -> dict:
    from app.services.report_missing_export import missing_report_csv

    with SessionLocal() as db:
        rows = db.scalars(select(RefreshWorkItem).where(RefreshWorkItem.ticker != "*")).all()
    problems = [row for row in rows if row.status in {"waiting_source", "error", "queued"}]
    causes = Counter((row.result_json or {}).get("reason_code") or "unknown_data_gap" for row in problems)
    type_counts = Counter((row.result_json or {}).get("instrument_type") or "unknown" for row in rows
                          if row.data_group == "statements")
    export_rows = list(csv.reader(StringIO(missing_report_csv().lstrip("\ufeff")), delimiter=";"))
    data_rows = export_rows[1:]
    return {"problem_tickers": len({row.ticker for row in problems}),
            "problem_rows": sum(row[2] in {"waiting_source", "error", "queued"} for row in data_rows if len(row) > 2),
            "informational_rows": sum(row[2] not in {"waiting_source", "error", "queued"} for row in data_rows if len(row) > 2),
            "missing_history": causes.get("missing_history", 0) + causes.get("actual_missing_history", 0),
            "provider_limits": causes.get("provider_rate_limited", 0) + causes.get("rate_limited", 0),
            "spacs": type_counts.get("spac", 0),
            "funds_and_trusts": type_counts.get("closed_end_fund", 0) + type_counts.get("investment_trust", 0),
            "foreign_private_issuers": type_counts.get("foreign_private_issuer", 0),
            "short_histories": causes.get("insufficient_operating_history", 0),
            "technical_gaps": sum(causes.get(code, 0) for code in
                                  ("unsupported_taxonomy", "predecessor_cik_gap", "provider_error")),
            "unexplained": causes.get("unknown_data_gap", 0), "causes": dict(causes)}


def run_full_reclassification(*, batch_size: int = 250) -> dict:
    """Run from the deployed backend with `python -m app.services.report_reclassification`."""
    before = problem_counts()
    evidence = enrich_stored_instrument_evidence()
    fund_filings = verify_suspected_fund_filings()
    totals: Counter = Counter()
    cursor = ""
    with capture_provider_usage() as usage:
        while True:
            result = reclassify_batch(after_ticker=cursor, limit=batch_size)
            totals.update(result["counts"])
            cursor = result["next_cursor"] or ""
            if not cursor:
                break
    return {"before": before, "after": problem_counts(), "evidence": evidence,
            "targeted_sec_filing_checks": fund_filings,
            "reclassified": dict(totals),
            "fmp_requests_during_backfill": usage.get("fmp_requests", 0)}


if __name__ == "__main__":
    print(json.dumps(run_full_reclassification(), ensure_ascii=False, indent=2))
