"""Resolve missing security IDs using the existing FMP account and shared backoff.

No positions are read or changed. Existing manual CUSIP mappings are preserved.
Only explicit symbol matches and checksum-valid identifiers are stored.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
import json
from pathlib import Path
from threading import Event

from sqlalchemy import select

from app.data_sources.fmp_client import FMP_PROFILE_URL
from app.data_sources.provider_guard import guarded_fmp_get
from app.db.models import Instrument, Sec13fCusipMapping
from app.db.session import SessionLocal
from app.repositories import jobs
from app.services.settings import get_runtime_config_value


def valid_cusip(value: str) -> bool:
    if len(value) != 9 or any(char not in "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ" for char in value[:8]) or not value[-1].isdigit():
        return False
    total = 0
    for offset, char in enumerate(value[:8]):
        number = int(char) if char.isdigit() else ord(char) - 55
        if offset % 2:
            number *= 2
        total += number // 10 + number % 10
    return (10 - total % 10) % 10 == int(value[-1])


def save_profile(profile: dict) -> str:
    ticker = profile["symbol"]
    cusip = str(profile.get("cusip") or "").strip().upper()
    with SessionLocal() as db:
        instrument = db.scalar(select(Instrument).where(Instrument.ticker == ticker))
        if instrument is None:
            return "instrument_missing"
        metadata = dict(instrument.metadata_json or {})
        metadata["sec13f_identity"] = {**profile, "source": "fmp_profile", "checked_at": datetime.now(UTC).isoformat()}
        instrument.metadata_json = metadata
        isin = str(profile.get("isin") or "")
        if not instrument.isin and len(isin) == 12:
            instrument.isin = isin
        status = "no_valid_cusip"
        if valid_cusip(cusip):
            existing = list(db.scalars(select(Sec13fCusipMapping).where(Sec13fCusipMapping.cusip == cusip)))
            if any(row.ticker != ticker for row in existing):
                status = "mapping_conflict"
            else:
                if not existing:
                    db.add(Sec13fCusipMapping(cusip=cusip, ticker=ticker, instrument_id=instrument.id,
                        issuer_name=str(profile.get("companyName") or instrument.name),
                        source="fmp_profile", confidence=1., metadata_json={"source": FMP_PROFILE_URL}))
                status = "identified"
        db.commit()
        return status


def repair(tickers: list[str], *, workers: int = 2) -> dict:
    key = get_runtime_config_value("FMP_API_KEY")
    if not key:
        return {"status": "provider_unavailable", "profiles": []}
    # Successful profiles survive provider limits and subsequent runs. Do not
    # spend a daily quota repeatedly on the first alphabetic block of symbols.
    with SessionLocal() as db:
        cached = {}
        for instrument in db.scalars(select(Instrument).where(Instrument.ticker.in_(tickers))):
            profile = (instrument.metadata_json or {}).get("sec13f_identity") or {}
            try:
                age = datetime.now(UTC) - datetime.fromisoformat(profile.get("checked_at", ""))
            except (ValueError, TypeError):
                continue
            if age.days < 30:
                cached[instrument.ticker] = {name: profile.get(name) for name in ["symbol", "companyName", "cusip", "isin", "ipoDate", "isEtf", "isFund"]}
    stopped = Event()
    def fetch(ticker):
        if ticker in cached:
            return {**cached[ticker], "status": "cached"}
        if stopped.is_set():
            return {"symbol": ticker, "status": "deferred"}
        try:
            response = guarded_fmp_get(FMP_PROFILE_URL, params={"symbol": ticker, "apikey": key}, timeout=20)
            if response.status_code in {401, 402, 403, 429}:
                stopped.set()
                return {"symbol": ticker, "status": "provider_blocked", "http_status": response.status_code}
            if response.status_code != 200:
                return {"symbol": ticker, "status": "provider_error", "http_status": response.status_code}
            data = response.json()
            rows = [row for row in data if isinstance(row, dict) and row.get("symbol") == ticker] if isinstance(data, list) else []
            if len(rows) != 1:
                return {"symbol": ticker, "status": "profile_missing_or_ambiguous"}
            profile = {name: rows[0].get(name) for name in ["symbol", "companyName", "cusip", "isin", "ipoDate", "isEtf", "isFund"]}
            return {**profile, "status": save_profile(profile)}
        except Exception as exc:
            # Exceptions can contain authenticated URLs; persist only their type.
            return {"symbol": ticker, "status": "lookup_error", "error_type": type(exc).__name__}
    tickers = list(dict.fromkeys(tickers))
    job = jobs.create_job("refresh_sec13f", {"source": "identifier_repair", "ticker_count": len(tickers)}, requested_by="codex_user_request")
    jobs.mark_running(job.job_id, step="Wertpapierkennungen über vorhandene FMP-Verbindung prüfen")
    profiles = []
    try:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for row in pool.map(fetch, tickers):
                profiles.append(row)
                if len(profiles) % 25 == 0:
                    jobs.update_progress(job.job_id, progress=min(95, int(100*len(profiles)/len(tickers))),
                        step="CUSIP und Börsengang prüfen", message=f"{len(profiles)}/{len(tickers)} Kennungen geprüft.")
        counts = {status: sum(row["status"] == status for row in profiles) for status in sorted({row["status"] for row in profiles})}
        result = {"status": "partial" if stopped.is_set() else "completed", "job_id": job.job_id, "counts": counts, "profiles": profiles}
        jobs.mark_done(job.job_id, result={key: value for key, value in result.items() if key != "profiles"}, message="Wertpapierkennungen geprüft; SEC-Holdings werden getrennt importiert.")
        return result
    except Exception as exc:
        jobs.mark_failed(job.job_id, error_message=type(exc).__name__)
        raise


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tickers", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    result = repair(json.loads(args.tickers.read_text()))
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False))
    print(json.dumps({key: value for key, value in result.items() if key != "profiles"}))
