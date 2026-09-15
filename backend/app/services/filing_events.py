"""Discover report changes from bounded SEC daily indexes, not 5,000 Companyfacts calls."""
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
import hashlib

import requests

from app.data_sources.fundamentals_client import _sec_cik_map
from app.repositories import fundamentals, universes
from app.repositories.refresh_work import WorkRequest, enqueue
from app.repositories.settings import _read_json_setting, _write_json_setting
from app.services.settings import get_runtime_config_value


REPORT_FORMS = {"10-Q", "10-Q/A", "10-K", "10-K/A", "8-K", "8-K/A", "6-K", "6-K/A", "20-F", "20-F/A", "40-F", "40-F/A"}


def parse_daily_index(content: str, tickers_by_cik: dict[str, list[str]]) -> list[WorkRequest]:
    now = datetime.now(UTC)
    found = {}
    for line in content.splitlines():
        parts = line.split("|")
        if len(parts) != 5 or parts[2] not in REPORT_FORMS or not parts[0].strip().isdigit():
            continue
        cik, _, form, filed, path = parts
        try:
            date.fromisoformat(filed)
        except ValueError:
            continue
        for ticker in tickers_by_cik.get(cik.strip().zfill(10), []):
            # An accession is a change trigger, not proof that a new quarter is present.
            revision = f"revision:{filed}:sec:{path.rsplit('/', 1)[-1]}"[:128]
            request = WorkRequest(ticker, "statements", revision, now, 25, {"filing": path, "form": form, "event_date": filed})
            if ticker not in found or revision > found[ticker].revision:
                found[ticker] = request
    return list(found.values())


def discover_filing_events(*, today: date | None = None) -> dict:
    today = today or date.today()
    agent = get_runtime_config_value("SEC_USER_AGENT")
    if not agent:
        raise RuntimeError("SEC_USER_AGENT fehlt; Filing-Pruefung nicht moeglich.")
    universe = set(universes.list_universe_tickers(limit=None))
    mapping = {}
    for ticker, cik in _sec_cik_map(agent, 15).items():
        if ticker in universe:
            mapping.setdefault(cik, []).append(ticker)
    state = _read_json_setting("report_filing_indexes") or {}
    scanned = dict(state.get("scanned", {}))
    events = 0
    # Revisit a short window to catch late index publication; safety checks cover longer outages.
    for offset in range(1, 8):
        day = today - timedelta(days=offset)
        if day.weekday() >= 5:
            continue
        quarter = (day.month - 1) // 3 + 1
        url = f"https://www.sec.gov/Archives/edgar/daily-index/{day.year}/QTR{quarter}/master.{day:%Y%m%d}.idx"
        response = requests.get(url, headers={"User-Agent": agent}, timeout=15)
        if response.status_code == 404:
            continue
        response.raise_for_status()
        revision = hashlib.sha256(response.content).hexdigest()
        if scanned.get(day.isoformat()) == revision:
            continue
        requests_to_queue = parse_daily_index(response.text, mapping)
        snapshots = fundamentals.get_latest_fundamentals_for_tickers([r.ticker for r in requests_to_queue])
        requests_to_queue = [replace(r, payload={**r.payload, "baseline_period": snapshots[r.ticker].fiscal_period if r.ticker in snapshots else ""}) for r in requests_to_queue]
        events += enqueue(requests_to_queue)
        scanned[day.isoformat()] = revision
        # Persist only after enqueue committed, so an interrupted scan can safely repeat.
        _write_json_setting("report_filing_indexes", {"scanned": {k: v for k, v in scanned.items() if k >= (today - timedelta(days=14)).isoformat()}}, description="SEC filing index checkpoints")
    return {"ok": True, "events": events, "checked_at": datetime.now(UTC).isoformat()}
