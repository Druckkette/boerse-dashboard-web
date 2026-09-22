"""Small report-group fetches; preserve valid history on partial provider responses."""
from dataclasses import asdict, fields, replace
from datetime import UTC, date, datetime
import hashlib
import json

from app.core_config import get_settings
from app.data_sources.fundamentals_client import fetch_fundamental_enrichment
from app.data_sources.yfinance_client import FetchedFundamentals, fetch_fundamentals
from app.repositories import fundamentals
from app.services.fundamentals import _to_write
from app.services.settings import get_runtime_config_value


HISTORIES = ("eps_quarter_history", "annual_eps_history", "revenue_quarter_history", "annual_revenue_history", "roe_history")
NON_PERIOD_FILINGS = {"8-K", "8-K/A", "6-K", "6-K/A", "10-Q/A", "10-K/A", "20-F/A", "40-F/A"}


def expected_report_arrived(enrichment, payload: dict) -> bool:
    target = payload.get("expected_period")
    if target:
        ends = enrichment.metadata.get("report_ends", {})
        return all(ends.get(key, "") >= target for key in ("DilutedEPS", "TotalRevenue"))
    if payload.get("event_date") and payload.get("form") not in NON_PERIOD_FILINGS:
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
    metadata = data.get("metadata_json") or {}
    data["metadata_json"] = {key: metadata.get(key) for key in HISTORIES}
    return hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()


def refresh_report_group(ticker: str, group: str, payload: dict) -> dict:
    previous = fundamentals.get_latest_fundamentals(ticker)
    if group == "beta":
        if previous is None:
            return {"complete": False, "changed": False, "reason": "Zuerst Statement-Snapshot aufbauen."}
        fetched = fetch_fundamentals(ticker, include_holders=False, include_calendar=False)
        if fetched.beta is None:
            return {"complete": False, "changed": False, "reason": "Provider liefert kein Beta; bestehende Daten bleiben erhalten."}
        values = {field.name: getattr(previous, field.name) for field in fields(fundamentals.FundamentalSnapshotWrite)}
        write = fundamentals.FundamentalSnapshotWrite(**values)
        write = replace(write, beta=fetched.beta)
        row = fundamentals.upsert_fundamentals(write)
        return {"complete": True, "changed": content_revision(previous) != content_revision(row), "beta": row.beta}

    settings = get_settings()
    enrichment = fetch_fundamental_enrichment(
        ticker, fmp_api_key=get_runtime_config_value("FMP_API_KEY") or settings.fmp_api_key,
        sec_user_agent=get_runtime_config_value("SEC_USER_AGENT") or settings.sec_user_agent,
        statements_only=True,
    )
    histories = {key: getattr(enrichment, key) for key in HISTORIES}
    if not any(histories.values()):
        return {"complete": False, "changed": False, "reason": "Keine verwertbaren Statements; bestehende Historie bleibt erhalten."}
    empty = {field.name: None for field in fields(FetchedFundamentals)}
    empty.update(ticker=ticker, as_of=date.today(), source="", fiscal_period="")
    write = _to_write(FetchedFundamentals(**empty), enrichment)
    values = asdict(write)
    if previous:
        for key, value in values.items():
            if value is None or value == "":
                values[key] = getattr(previous, key)
        metadata = {**previous.metadata_json, **values["metadata_json"]}
        for key in HISTORIES:
            metadata[key] = merge_history(previous.metadata_json.get(key, []), histories[key])
        values["metadata_json"] = metadata
    target = payload.get("expected_period")
    expected_arrived = expected_report_arrived(enrichment, payload)
    complete = not fundamentals._missing_required_history_keys(values["metadata_json"]) and expected_arrived
    values["metadata_json"]["report_refresh"] = {
        "checked_at": datetime.now(UTC).isoformat(), "expected_period": target,
        "event_date": payload.get("event_date"), "complete": complete,
        "status": "current" if complete else "waiting_source",
    }
    row = fundamentals.upsert_fundamentals(fundamentals.FundamentalSnapshotWrite(**values))
    return {"complete": complete, "changed": previous is None or content_revision(previous) != content_revision(row),
            "fiscal_period": row.fiscal_period, "expected_period": target,
            "reason": "Aktuelle Berichtsperiode und Historien vorhanden." if complete else "Erwartete Periode oder Historie fehlt noch."}
