"""Small report-group fetches; preserve valid history on partial provider responses."""
from dataclasses import asdict, fields, replace
from datetime import UTC, date, datetime, timedelta
import hashlib
import json
from math import isfinite

from app.core_config import get_settings
from app.data_sources.fundamentals_client import fetch_fundamental_enrichment
from app.data_sources.sec_companyfacts_cache import bulk_status
from app.data_sources.yfinance_client import FetchedFundamentals, fetch_fundamentals
from app.repositories import fundamentals, prices
from app.services.fundamentals import _to_write, merge_snapshot_write
from app.services.settings import get_runtime_config_value
from app.domain.stocks.instrument_type import classify_instrument, inapplicable_reason
from app.data_sources.provider_usage import record_provider_event


HISTORIES = ("eps_quarter_history", "annual_eps_history", "revenue_quarter_history", "annual_revenue_history", "roe_history")
PERIODIC_FILINGS = {"10-Q", "10-K", "20-F", "40-F"}

def filing_needs_live_sec(payload: dict) -> bool:
    """Only bypass the bulk archive for filings it cannot yet contain."""
    if not payload.get("filing"):
        return False
    status = bulk_status()
    if not status.get("available"):
        return True
    try:
        fetched = datetime.fromisoformat(str(status.get("fetched_at", ""))).date()
        filed = date.fromisoformat(str(payload.get("event_date", "")))
    except ValueError:
        return True
    return filed >= fetched


def cached_price_beta(ticker: str, *, min_returns: int = 90) -> float | None:
    """Estimate one-year market beta from locally cached adjusted daily closes."""
    if ticker == "SPY":
        return 1.0
    bars = prices.list_price_bars_for_tickers([ticker, "SPY"], start_date=date.today() - timedelta(days=400))

    def closes(rows: list) -> dict[date, float]:
        return {row.date: float(row.adj_close) for row in rows
                if row.adj_close is not None and isfinite(float(row.adj_close)) and row.adj_close > 0}

    stock = closes(bars.get(ticker, []))
    market = closes(bars.get("SPY", []))
    days = sorted(stock.keys() & market.keys())[-253:]
    if len(days) < min_returns + 1 or days[-1] < date.today() - timedelta(days=14):
        return None
    if any((day - previous).days > 10 for previous, day in zip(days, days[1:])):
        return None
    x = [market[day] / market[previous] - 1 for previous, day in zip(days, days[1:])]
    y = [stock[day] / stock[previous] - 1 for previous, day in zip(days, days[1:])]
    # A 500% daily move in adjusted closes usually indicates a bad adjustment,
    # ticker reuse or a split discontinuity. Do not fit a beta to that series.
    if any(abs(value) > 5 for value in y):
        return None
    mean_x = sum(x) / len(x)
    mean_y = sum(y) / len(y)
    variance = sum((value - mean_x) ** 2 for value in x)
    if variance <= 1e-12:
        return None
    beta = sum((a - mean_x) * (b - mean_y) for a, b in zip(x, y)) / variance
    return round(beta, 4) if isfinite(beta) and abs(beta) <= 10 else None


def expected_report_arrived(enrichment, payload: dict) -> bool:
    target = payload.get("expected_period")
    if target:
        ends = enrichment.metadata.get("report_ends", {})
        keys = (("AnnualDilutedEPS", "AnnualTotalRevenue") if payload.get("form") in {"20-F", "40-F"}
                else ("DilutedEPS", "TotalRevenue"))
        return all(ends.get(key, "") >= target for key in keys)
    # An older index hit has already had a chance to enter the newer bulk
    # archive. A just-filed periodic report must show a changed period or be
    # checked again after the next archive refresh; SEC may publish XBRL later.
    if payload.get("filing"):
        if payload.get("form") in PERIODIC_FILINGS and filing_needs_live_sec(payload):
            return bool(enrichment.fiscal_period and enrichment.fiscal_period != payload.get("baseline_period"))
        return True
    if payload.get("event_date"):
        return bool(enrichment.fiscal_period and enrichment.fiscal_period != payload.get("baseline_period"))
    return True


def merge_history(old: list, new: list) -> list:
    rows = {}
    for item in [*old, *new]:
        key = item.get("fiscal_period") or item.get("fiscal_year")
        if key:
            rows[key] = {**rows.get(key, {}), **{k: v for k, v in item.items() if v is not None}}
            # Never retain a formerly positive growth rate after a changed loss/zero EPS.
            for name, value in item.items():
                if "growth" in name or name == "flag":
                    rows[key][name] = value
    return [rows[key] for key in sorted(rows, reverse=True)]


def content_revision(row) -> str:
    data = asdict(row)
    data.pop("as_of", None)
    data.pop("source", None)
    metadata = data.get("metadata_json") or {}
    data["metadata_json"] = {key: metadata.get(key) for key in HISTORIES}
    return hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()


def history_gap_reason(metadata: dict, missing: list[str], provider_reason: str = "") -> str:
    if provider_reason in {"provider_rate_limited", "rate_limited"}:
        return "provider_rate_limited"
    if provider_reason in {"provider_error", "waiting_sec_data", "waiting_yahoo_data", "waiting_fmp_fallback"}:
        return provider_reason
    kind = metadata.get("instrument_type", "unknown")
    if inapplicable_reason(kind):
        return inapplicable_reason(kind)
    if not missing and metadata.get("predecessor_ciks"):
        return "predecessor_cik_history_merged"
    if kind == "foreign_private_issuer" and any("quarter" in key for key in missing):
        return "foreign_filer_reporting_structure"
    diagnostics = metadata.get("statement_diagnostics") or {}
    if diagnostics.get("predecessor_errors") and missing:
        return "predecessor_cik_gap"
    concepts = diagnostics.get("relevant_xbrl_concepts") or {}
    if "revenue_quarter_history" in missing or "annual_revenue_history" in missing:
        if concepts.get("TotalRevenue") and not diagnostics.get("revenue_concept"):
            return "unsupported_taxonomy"
    latest_quarter = diagnostics.get("quarterly_latest_end") or {}
    try:
        eps_recent = (date.today() - date.fromisoformat(latest_quarter["DilutedEPS"])).days <= 2 * 366
    except (KeyError, TypeError, ValueError):
        eps_recent = False
    try:
        revenue_recent = (date.today() - date.fromisoformat(latest_quarter["TotalRevenue"])).days <= 2 * 366
    except (KeyError, TypeError, ValueError):
        revenue_recent = False
    if (("eps_quarter_history" in missing and revenue_recent and not eps_recent) or
        ("revenue_quarter_history" in missing and eps_recent and not revenue_recent)):
        return "unsupported_taxonomy"
    lengths = ((metadata.get("enrichment") or {}).get("series_lengths") or
               metadata.get("series_lengths") or {})
    annual = max(int(lengths.get(key) or 0) for key in ("AnnualDilutedEPS", "AnnualTotalRevenue"))
    quarterly = max(int(lengths.get(key) or 0) for key in ("DilutedEPS", "TotalRevenue"))
    listing_date = metadata.get("listing_date") or metadata.get("ipo_date")
    try:
        young_listing = bool(listing_date and (date.today() - date.fromisoformat(str(listing_date))).days < 4 * 366)
    except ValueError:
        young_listing = False
    if diagnostics.get("forms_seen") and annual < 4 and quarterly < 7 and (annual > 0 or young_listing):
        return "insufficient_operating_history"
    if diagnostics.get("verified_source_gap"):
        return "actual_missing_history"
    if provider_reason == "unsupported_taxonomy":
        return provider_reason
    return "unknown_data_gap"


def refresh_report_group(ticker: str, group: str, payload: dict) -> dict:
    previous = fundamentals.get_latest_fundamentals(ticker)
    if group == "beta":
        if previous is None:
            return {"complete": False, "changed": False, "reason": "Zuerst Statement-Snapshot aufbauen."}
        previous_bad_local_beta = (
            previous.beta is not None
            and ((previous.metadata_json or {}).get("data_sources") or {}).get("beta") == "local_price_cache"
            and (not isfinite(float(previous.beta)) or abs(previous.beta) > 10)
        )
        beta = cached_price_beta(ticker)
        source = "Gespeicherte Aktien- und SPY-Kurse"
        beta_source = "local_price_cache"
        if beta is None:
            fetched = fetch_fundamentals(ticker, include_holders=False, include_calendar=False)
            beta = fetched.beta
            source = "Yahoo Finance"
            beta_source = "yfinance"
        if beta is not None and (not isfinite(float(beta)) or abs(beta) > 10):
            beta = None
        if beta is None:
            if previous_bad_local_beta:
                values = {field.name: getattr(previous, field.name) for field in fields(fundamentals.FundamentalSnapshotWrite)}
                metadata = {**(previous.metadata_json or {}), "data_sources": {
                    **((previous.metadata_json or {}).get("data_sources") or {}), "beta": "unavailable",
                }}
                fundamentals.upsert_fundamentals(fundamentals.FundamentalSnapshotWrite(
                    **{**values, "beta": None, "metadata_json": metadata}
                ))
            return {"complete": False, "changed": previous_bad_local_beta,
                    "reason_code": "waiting_yahoo_data",
                    "reason": "Kein belastbares Beta aus Kursen oder Yahoo verfügbar."}
        values = {field.name: getattr(previous, field.name) for field in fields(fundamentals.FundamentalSnapshotWrite)}
        write = fundamentals.FundamentalSnapshotWrite(**values)
        metadata = {**(write.metadata_json or {}), "data_sources": {
            **((write.metadata_json or {}).get("data_sources") or {}),
            "beta": beta_source,
        }}
        write = replace(write, beta=beta, metadata_json=metadata)
        row = fundamentals.upsert_fundamentals(write)
        return {"complete": True, "changed": content_revision(previous) != content_revision(row), "beta": row.beta, "source": source}

    profile = fundamentals.get_instrument_profile(ticker)
    profile_metadata = profile.get("metadata") or {}
    previous_metadata = previous.metadata_json if previous else {}
    kind = classify_instrument(ticker=ticker, name=profile.get("name", ""), asset_class=profile.get("asset_class", ""),
                               etf=str((profile_metadata.get("nasdaq_listing") or {}).get("etf", "")),
                               nextshares=str((profile_metadata.get("nasdaq_listing") or {}).get("nextshares", "")),
                               sec_sic=profile_metadata.get("sec_sic") or "",
                               sec_forms=([profile_metadata["sec_latest_annual_form"],
                                           *(form for form in profile_metadata.get("sec_forms") or []
                                             if form in {"N-CSR", "N-CSRS"})]
                                          if profile_metadata.get("sec_latest_annual_form") else
                                          profile_metadata.get("sec_forms")),
                               previous_type=profile_metadata.get("instrument_type") or previous_metadata.get("instrument_type", ""))
    if kind == "unknown":
        kind = profile_metadata.get("instrument_type") or previous_metadata.get("instrument_type") or "unknown"
    skip_reason = inapplicable_reason(kind)
    if skip_reason:
        if profile and kind != profile_metadata.get("instrument_type"):
            fundamentals.save_instrument_classification(ticker, kind, source="instrument_profile")
        for metric in ("avoided_sec_requests", "avoided_yahoo_fallbacks", "avoided_fmp_fallbacks",
                       "instrument_type_skipped"):
            record_provider_event(metric)
        if previous and previous_metadata.get("instrument_type") != kind:
            values = {field.name: getattr(previous, field.name) for field in fields(fundamentals.FundamentalSnapshotWrite)}
            values["metadata_json"] = {**previous_metadata, "instrument_type": kind,
                                       "report_refresh": {"status": "not_applicable", "complete": True,
                                                          "reason_code": skip_reason}}
            fundamentals.upsert_fundamentals(fundamentals.FundamentalSnapshotWrite(**values))
        return {"complete": True, "changed": bool(previous and previous_metadata.get("instrument_type") != kind),
                "reason_code": skip_reason, "instrument_type": kind,
                "reason": "Fundamentalkriterium für diesen Wertpapiertyp nicht anwendbar."}
    settings = get_settings()
    enrichment = fetch_fundamental_enrichment(
        ticker, fmp_api_key=get_runtime_config_value("FMP_API_KEY") or settings.fmp_api_key,
        sec_user_agent=get_runtime_config_value("SEC_USER_AGENT") or settings.sec_user_agent,
        statements_only=True,
        previous_metadata={**previous_metadata, "instrument_type": kind},
        force_live_sec=filing_needs_live_sec(payload),
        refresh_sec=bool(payload.get("filing") or payload.get("diagnostic_only")),
        allow_fallbacks=not bool(payload.get("diagnostic_only")),
    )
    histories = {key: getattr(enrichment, key) for key in HISTORIES}
    enrichment_metadata = getattr(enrichment, "metadata", {}) or {}
    actual_kind = enrichment_metadata.get("instrument_type") or kind
    diagnostics = enrichment_metadata.get("statement_diagnostics") or {}
    forms = ([diagnostics["latest_annual_form"]] if diagnostics.get("latest_annual_form") else
             diagnostics.get("forms_seen") or [])
    if actual_kind != "unknown" and profile and (actual_kind != profile_metadata.get("instrument_type") or forms != profile_metadata.get("sec_forms", [])):
        fundamentals.save_instrument_classification(ticker, actual_kind, source="sec_companyfacts", sec_forms=forms)
    if not any(histories.values()):
        complete = bool(previous and not fundamentals._missing_required_history_keys(previous_metadata)
                        and enrichment_metadata.get("reason_code") not in {"provider_rate_limited", "provider_error"}
                        and not (payload.get("filing") and enrichment_metadata.get("reason_code")))
        return {"complete": complete, "changed": False,
                "reason_code": history_gap_reason({**previous_metadata, **enrichment_metadata},
                                                  fundamentals._missing_required_history_keys(previous_metadata),
                                                  enrichment_metadata.get("reason_code", "")),
                "instrument_type": actual_kind,
                "statement_diagnostics": enrichment_metadata.get("statement_diagnostics", {}),
                "primary_cik": enrichment_metadata.get("primary_cik"),
                "predecessor_ciks": enrichment_metadata.get("predecessor_ciks", []),
                "reason": "Keine verwertbaren Statements; bestehende Historie bleibt erhalten."}
    empty = {field.name: None for field in fields(FetchedFundamentals)}
    empty.update(ticker=ticker, as_of=date.today(), source="", fiscal_period="")
    write = _to_write(FetchedFundamentals(**empty), enrichment)
    values = asdict(merge_snapshot_write(previous, write))
    values["metadata_json"]["instrument_type"] = actual_kind
    if enrichment_metadata.get("listing_date"):
        values["metadata_json"]["listing_date"] = enrichment_metadata["listing_date"]
    if profile_metadata.get("listing_date") or profile_metadata.get("ipo_date"):
        values["metadata_json"]["listing_date"] = (profile_metadata.get("listing_date") or
                                                      profile_metadata.get("ipo_date"))
    target = payload.get("expected_period")
    expected_arrived = expected_report_arrived(enrichment, payload)
    complete = (not fundamentals._missing_required_history_keys(values["metadata_json"]) and expected_arrived
                and enrichment_metadata.get("reason_code") not in {"provider_rate_limited", "provider_error"})
    missing = fundamentals._missing_required_history_keys(values["metadata_json"])
    reason_code = ("provider_rate_limited" if enrichment_metadata.get("reason_code") == "provider_rate_limited" else
                   "provider_error" if enrichment_metadata.get("reason_code") == "provider_error" else
                   "waiting_sec_data" if not expected_arrived else
                   history_gap_reason(values["metadata_json"], missing, enrichment_metadata.get("reason_code", ""))
                   if not complete else
                   "foreign_filer_reporting_structure" if actual_kind == "foreign_private_issuer" and
                   any(not getattr(enrichment, key) for key in ("eps_quarter_history", "revenue_quarter_history")) else
                   "predecessor_cik_history_merged" if enrichment_metadata.get("predecessor_ciks") else "")
    values["metadata_json"]["report_refresh"] = {
        "checked_at": datetime.now(UTC).isoformat(), "expected_period": target,
        "event_date": payload.get("event_date"), "complete": complete,
        "status": "current" if complete else "waiting_source",
        "reason_code": reason_code,
    }
    row = fundamentals.upsert_fundamentals(fundamentals.FundamentalSnapshotWrite(**values))
    return {"complete": complete, "changed": previous is None or content_revision(previous) != content_revision(row),
            "fiscal_period": row.fiscal_period, "expected_period": target,
            "reason_code": reason_code,
            "reason": "Aktuelle Berichtsperiode und Historien vorhanden." if complete else "Erwartete Periode oder Historie fehlt noch."}
