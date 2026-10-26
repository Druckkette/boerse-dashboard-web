"""One bounded worker-side history refresh for chart data-quality failures.

No read endpoint calls this module. Yahoo OHLC already reflect stock splits;
corporate-action factors are persisted as provenance and are never applied here.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from math import isfinite
import re
from billiard.exceptions import SoftTimeLimitExceeded, TimeLimitExceeded

from app.data_sources.yfinance_client import fetch_daily_price_bars_strict as fetch_daily_price_bars
from app.repositories.prices import PriceBarWrite, list_price_bars, upsert_price_bars


REPAIR_TIMEOUT_SECONDS = 10
MIN_FRESH_BARS = 25


def _positive(value) -> bool:
    try:
        return value is not None and isfinite(value) and value > 0
    except (TypeError, ValueError, OverflowError):
        return False


def _valid_bar(bar) -> bool:
    values = [bar.open, bar.high, bar.low, bar.close]
    if not all(_positive(value) for value in values):
        return False
    if not bar.low <= min(bar.open, bar.close) <= max(bar.open, bar.close) <= bar.high:
        return False
    volume = bar.volume
    try:
        if volume is not None and (not isfinite(volume) or volume < 0):
            return False
    except (TypeError, ValueError, OverflowError):
        return False
    for field in ("adj_close", "split_adjustment_factor"):
        value = getattr(bar, field, None)
        if value is not None and not _positive(value):
            return False
    ratio = getattr(bar, "stock_split", None)
    return ratio in (None, 0) or _positive(ratio)


def repair_chart_history(
    ticker: str,
    yahoo_symbol: str | None = None,
    *,
    start_date: date,
    end_date: date,
) -> dict:
    """Refresh a complete shared price basis, or leave the existing cache intact.

    The caller owns scheduling, cooldowns and the total request budget. This
    function issues at most one provider fetch, with a ten-second request timeout
    and no service-level retry. The complete existing cache is included when
    changing its price basis, even outside the caller's chart-analysis window.
    Database exceptions deliberately propagate instead of becoming provider errors.
    """
    clean = ticker.strip().upper()
    explicit_symbol = (yahoo_symbol or "").strip().upper()
    alias = re.fullmatch(r"(\d{1,5})-HK", clean)
    symbol = (
        f"{alias[1]}.HK" if alias and explicit_symbol in ("", clean) else explicit_symbol or clean
    )
    result = {
        "ticker": clean,
        "yahoo_symbol": symbol,
        "source": "yfinance",
        "attempted": False,
        "ok": False,
        "records_seen": 0,
        "records_in_window": 0,
        "valid_records": 0,
        "invalid_records": 0,
        "records_written": 0,
        "first_date": None,
        "last_date": None,
        "coverage_complete": False,
        "split_events": {},
        "extreme_jump_dates": [],
        "fresh_jump_verified": False,
        "timeout_seconds": REPAIR_TIMEOUT_SECONDS,
        "reason_code": "insufficient_fresh_history",
        "message": "Keine ausreichend vollständige neue Kurshistorie verfügbar.",
    }
    if not clean or start_date > end_date:
        result.update(reason_code="invalid_request", message="Ungültiger Ticker oder Zeitraum.")
        return result

    # A split can change every historical OHLC. Never replace only the last 850
    # days while leaving older quotes (or an existing intraday quote) on another basis.
    cached = list_price_bars(clean)
    cached_dates = {bar.date for bar in cached}
    basis_start = min(cached_dates | {start_date})
    basis_end = max(cached_dates | {end_date})
    if basis_end > date.today():
        result.update(
            reason_code="invalid_cached_date",
            message="Zukünftiges Datum im Kurscache; keine automatische Änderung.",
        )
        return result
    result.update(basis_start_date=basis_start.isoformat(), basis_end_date=basis_end.isoformat())
    result["attempted"] = True
    try:
        fetched = fetch_daily_price_bars(
            symbol,
            period="5y",
            start=basis_start,
            end=basis_end + timedelta(days=1),
            timeout=REPAIR_TIMEOUT_SECONDS,
        )
    except (SoftTimeLimitExceeded, TimeLimitExceeded):
        raise
    except Exception as exc:
        # Do not expose arbitrary provider exception text in the public result.
        code = getattr(exc, "status_code", None)
        response_code = getattr(getattr(exc, "response", None), "status_code", None)
        detail = f"{type(exc).__name__} {exc}".lower()
        limited = (
            code == 429
            or response_code == 429
            or any(
                marker in detail
                for marker in ("429", "rate limit", "ratelimit", "too many requests")
            )
        )
        result.update(
            reason_code="rate_limited" if limited else "provider_error",
            message=(
                "Yahoo begrenzt weitere Kursanfragen; vorhandene Kurse bleiben erhalten."
                if limited
                else "Neue Yahoo-Kurse konnten nicht abgerufen werden; Cache erhalten."
            ),
        )
        return result

    result["records_seen"] = len(fetched)
    if not fetched:
        result.update(
            reason_code="provider_empty",
            message="Yahoo lieferte keine neuen Kurse; vorhandene Kurse bleiben erhalten.",
        )
        return result

    incoming = []
    dates_seen = set()
    for bar in fetched:
        day = getattr(bar, "date", None)
        if not isinstance(day, date) or isinstance(day, datetime):
            result["invalid_records"] += 1
            continue
        if not basis_start <= day <= basis_end:
            continue
        result["records_in_window"] += 1
        if day in dates_seen or not _valid_bar(bar):
            result["invalid_records"] += 1
            continue
        dates_seen.add(day)
        incoming.append(bar)
    incoming.sort(key=lambda bar: bar.date)
    result["valid_records"] = len(incoming)
    if incoming:
        result["first_date"] = incoming[0].date.isoformat()
        result["last_date"] = incoming[-1].date.isoformat()
        result["split_events"] = {
            bar.date.isoformat(): float(bar.stock_split)
            for bar in incoming
            if getattr(bar, "stock_split", None)
        }

    if len(incoming) < MIN_FRESH_BARS:
        result["message"] = (
            "Weniger als 25 gültige neue Handelstage; vorhandene Kurse bleiben erhalten."
        )
        return result
    if result["invalid_records"]:
        result.update(
            reason_code="partially_repaired",
            message="Neue Historie enthält ungültige oder doppelte Kurse; Cache unverändert.",
        )
        return result

    span = (incoming[-1].date - incoming[0].date).days + 1
    gaps = [(right.date - left.date).days for left, right in zip(incoming, incoming[1:])]
    complete = (
        cached_dates.issubset(dates_seen)
        and (basis_end - incoming[-1].date).days <= 10
        and max(gaps, default=0) <= 10
        and len(incoming) / span >= 0.5
    )
    if not complete:
        result["message"] = (
            "Neue Historie ist verkürzt, lückenhaft oder veraltet; vorhandene Preisbasis bleibt erhalten."
        )
        return result
    result["coverage_complete"] = True
    jump_dates = [
        right.date.isoformat()
        for left, right in zip(incoming, incoming[1:])
        if abs(right.close - left.close) > left.close * 0.60
    ]
    result["extreme_jump_dates"] = jump_dates
    result["fresh_jump_verified"] = bool(jump_dates)
    writes = [
        PriceBarWrite(
            date=bar.date,
            open=bar.open,
            high=bar.high,
            low=bar.low,
            close=bar.close,
            adj_close=bar.adj_close,
            volume=bar.volume,
            stock_split=getattr(bar, "stock_split", None),
            split_adjustment_factor=getattr(bar, "split_adjustment_factor", None),
        )
        for bar in incoming
    ]
    result["records_written"] = upsert_price_bars(
        clean, writes, source="yfinance", yahoo_symbol=symbol
    )
    result.update(
        ok=not jump_dates,
        reason_code="partially_repaired" if jump_dates else "repaired",
        message=(
            "Neue konsistente Historie gespeichert; extremer Sprung besteht auch im Neuabruf."
            if jump_dates
            else "Vollständige neue Kurshistorie geprüft und gespeichert."
        ),
    )
    return result
