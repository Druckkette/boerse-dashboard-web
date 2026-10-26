"""Cached chart analysis and worker-side universe scanning. No network I/O in reads."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from math import isfinite

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.db.models import Instrument
from app.db.session import SessionLocal
from app.domain.chart_patterns import (
    ALGORITHM_VERSION,
    Bar,
    LABELS,
    PatternParameters,
    detect_patterns,
    validate_bars,
)
from app.repositories import settings as repository
from app.repositories.prices import list_price_bars, list_price_bars_for_tickers
from app.services.market_calendar import completed_ticker_market_session


CONFIG_KEY = "chart_analysis_config_v1"
RESULT_KEY = "chart_analysis_scan_v1"


def get_config() -> dict:
    parameters = PatternParameters.model_validate(repository._read_json_setting(CONFIG_KEY))
    return {
        "parameters": parameters.model_dump(),
        "defaults": PatternParameters().model_dump(),
        "parameter_hash": parameters.fingerprint,
        "algorithm_version": ALGORITHM_VERSION,
        "patterns": LABELS,
    }


def save_config(parameters: PatternParameters) -> dict:
    repository._write_json_setting(
        CONFIG_KEY, parameters.model_dump(), description="Chartanalyse: Regeln aus Kapitel 4.2"
    )
    return get_config()


def _bar(row) -> Bar:
    # Yahoo OHLC already account for splits; split_adjustment_factor is ONLY
    # used for transaction valuation elsewhere. Applying it here would double-adjust.
    return Bar(
        date=row.date,
        open=float(row.open or 0),
        high=float(row.high or 0),
        low=float(row.low or 0),
        close=float(row.close or 0),
        volume=row.volume,
    )


def _chart_number(value):
    return value if value is not None and isfinite(value) else None


def analyse(ticker: str, *, as_of: date | None = None) -> dict:
    parameters = PatternParameters.model_validate(get_config()["parameters"])
    cutoff = min(as_of or date.max, completed_ticker_market_session(ticker).date)
    rows = list_price_bars(ticker, start_date=cutoff - timedelta(days=850))
    # Multiple providers for one date are ambiguous, never silently blended.
    rows = [r for r in rows if r.date <= cutoff]
    bars = [_bar(r) for r in rows]
    problems = validate_bars(bars)
    return {
        "ticker": ticker,
        "as_of": cutoff.isoformat(),
        "price_as_of": bars[-1].date.isoformat() if bars else None,
        "stale": bool(bars and bars[-1].date < cutoff),
        "algorithm_version": ALGORITHM_VERSION,
        "parameter_hash": parameters.fingerprint,
        "parameters": parameters.model_dump(),
        "diagnostics": problems,
        "points": [
            {
                "date": r.date.isoformat(),
                "open": _chart_number(r.open),
                "high": _chart_number(r.high),
                "low": _chart_number(r.low),
                "close": _chart_number(r.close),
                "volume": _chart_number(r.volume),
            }
            for r in rows
        ],
        "patterns": [v.model_dump() for v in detect_patterns(ticker, bars, parameters)]
        if not problems
        else [],
    }


def get_results(
    *,
    kind: str | None = None,
    status: str | None = None,
    search: str = "",
    offset: int = 0,
    limit: int = 100,
) -> dict:
    config = get_config()
    snapshot = repository._read_json_setting(RESULT_KEY)
    rows = snapshot.get("patterns", [])
    needle = search.strip().lower()
    filtered = [
        r
        for r in rows
        if (not kind or r["kind"] == kind)
        and (not status or r["status"] == status)
        and (not needle or needle in (r["ticker"] + " " + r.get("name", "")).lower())
    ]
    return {
        **{k: v for k, v in snapshot.items() if k != "patterns"},
        "available": bool(snapshot),
        "obsolete": bool(snapshot and snapshot.get("parameter_hash") != config["parameter_hash"]),
        "current_parameter_hash": config["parameter_hash"],
        "total": len(filtered),
        "rows": filtered[offset : offset + limit],
        "offset": offset,
        "limit": limit,
    }


def scan_universe(*, progress=None, cancelled=None) -> dict:
    config = get_config()
    parameters = PatternParameters.model_validate(config["parameters"])
    try:
        with SessionLocal() as db:
            stocks = [
                (r.ticker, r.name)
                for r in db.scalars(
                    select(Instrument)
                    .where(Instrument.asset_class == "stock", ~Instrument.ticker.startswith("^"))
                    .order_by(Instrument.ticker)
                ).all()
            ]
    except SQLAlchemyError as exc:
        raise repository.SettingsRepositoryUnavailable(str(exc)) from exc
    patterns, skipped = [], []
    as_of_dates = []
    for start in range(0, len(stocks), 25):
        if cancelled:
            cancelled()
        chunk = stocks[start : start + 25]
        # A single bounded query per batch, instead of one request per stock.
        data = list_price_bars_for_tickers(
            [t for t, _ in chunk], start_date=date.today() - timedelta(days=850)
        )
        for ticker, name in chunk:
            cutoff = completed_ticker_market_session(ticker).date
            bars = [_bar(row) for row in data.get(ticker, []) if row.date <= cutoff]
            problems = validate_bars(bars)
            if problems:
                skipped.append({"ticker": ticker, "reason": problems[0]})
                continue
            as_of_dates.append(bars[-1].date.isoformat())
            for pattern in detect_patterns(ticker, bars, parameters):
                patterns.append(
                    {
                        **pattern.model_dump(),
                        "name": name,
                        "price_as_of": bars[-1].date.isoformat(),
                        "stale": bars[-1].date < cutoff,
                    }
                )
        if progress:
            progress(min(start + len(chunk), len(stocks)), len(stocks))
    if cancelled:
        cancelled()
    snapshot = {
        "generated_at": datetime.now(UTC).isoformat(),
        "algorithm_version": ALGORITHM_VERSION,
        "parameter_hash": parameters.fingerprint,
        "parameters": parameters.model_dump(),
        "scanned_count": len(stocks),
        "analysed_count": len(stocks) - len(skipped),
        "skipped_count": len(skipped),
        "skipped": skipped,
        "oldest_price_date": min(as_of_dates) if as_of_dates else None,
        "newest_price_date": max(as_of_dates) if as_of_dates else None,
        "patterns": sorted(patterns, key=lambda r: r["detected_on"], reverse=True),
    }
    # Publish once after success; cancellation/failure retains the previous scan.
    repository._write_json_setting(
        RESULT_KEY, snapshot, description="Chartanalyse: abgeschlossener Universumscan"
    )
    return {
        "ok": True,
        "records_seen": len(stocks),
        "records_written": len(patterns),
        "skipped_count": len(skipped),
        "parameter_hash": parameters.fingerprint,
    }
