from __future__ import annotations

import math
import random
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Literal

from app.data_sources.yfinance_client import FetchedPriceBar, fetch_daily_price_bars, fetch_daily_price_bars_batch
from app.repositories.prices import (
    PriceBarWrite,
    PriceRepositoryUnavailable,
    get_latest_price_bar_date,
    get_price_cache_metadata,
    list_price_bars,
    upsert_price_bars,
)
from app.schemas import PriceBarPoint, PriceHistoryResponse, PriceRefreshResponse


PriceRange = Literal["1m", "3m", "6m", "1y", "2y", "5y"]

RANGE_DAYS: dict[PriceRange, int] = {
    "1m": 31,
    "3m": 93,
    "6m": 186,
    "1y": 370,
    "2y": 740,
    "5y": 1850,
}

YFINANCE_PERIOD_BY_RANGE: dict[PriceRange, str] = {
    "1m": "3mo",
    "3m": "6mo",
    "6m": "1y",
    "1y": "2y",
    "2y": "5y",
    "5y": "10y",
}

DEFAULT_INCREMENTAL_PRICE_OVERLAP_DAYS = 1


@dataclass(frozen=True)
class PriceRefreshSymbol:
    ticker: str
    yahoo_symbol: str | None = None


def get_price_history(ticker: str, *, range_key: PriceRange = "1y") -> PriceHistoryResponse:
    clean = _normalize_ticker(ticker)
    start_date = date.today() - timedelta(days=RANGE_DAYS[range_key])
    cache_updated_at = None

    try:
        rows = list_price_bars(clean, start_date=start_date)
        metadata = get_price_cache_metadata(clean)
        cache_updated_at = metadata.cache_updated_at if metadata else None
    except PriceRepositoryUnavailable:
        rows = []

    if rows:
        points = [
            PriceBarPoint(
                date=row.date.isoformat(),
                open=row.open,
                high=row.high,
                low=row.low,
                close=float(row.close or 0),
                adj_close=row.adj_close,
                volume=row.volume,
            )
            for row in rows
            if row.close is not None
        ]
        return _build_response(
            clean,
            range_key=range_key,
            source="database",
            points=points,
            cache_updated_at=cache_updated_at,
        )

    fallback_points = _synthetic_price_points(clean, start_date=start_date)
    return _build_response(
        clean,
        range_key=range_key,
        source="synthetic_fallback",
        points=fallback_points,
        cache_updated_at=None,
    )


def refresh_and_get_price_history(
    ticker: str,
    *,
    range_key: PriceRange = "1y",
    fetch_range_key: PriceRange = "2y",
    incremental: bool = True,
    timeout: int = 15,
    overlap_days: int = DEFAULT_INCREMENTAL_PRICE_OVERLAP_DAYS,
) -> PriceRefreshResponse:
    clean = _normalize_ticker(ticker)
    refresh_result = refresh_price_cache_for_ticker(
        clean,
        range_key=fetch_range_key,
        incremental=incremental,
        timeout=timeout,
        overlap_days=overlap_days,
    )
    history = get_price_history(clean, range_key=range_key)
    return PriceRefreshResponse(
        ticker=clean,
        ok=bool(refresh_result.get("ok")),
        refreshed_at=datetime.now(UTC),
        refresh=refresh_result,
        history=history,
    )


def refresh_price_cache_for_ticker(
    ticker: str,
    *,
    range_key: PriceRange = "1y",
    yahoo_symbol: str | None = None,
    incremental: bool = False,
    timeout: int = 15,
    overlap_days: int = DEFAULT_INCREMENTAL_PRICE_OVERLAP_DAYS,
) -> dict:
    clean = _normalize_ticker(ticker)
    fetch_symbol = (yahoo_symbol or clean).strip().upper()
    period = YFINANCE_PERIOD_BY_RANGE[range_key]
    latest_cached_date = _latest_cached_date(clean) if incremental else None
    start_date = (
        _incremental_start_date(latest_cached_date, overlap_days=overlap_days)
        if latest_cached_date
        else None
    )
    fetched = fetch_daily_price_bars(fetch_symbol, period=period, start=start_date, timeout=timeout)
    return _write_price_cache_result(
        ticker=clean,
        yahoo_symbol=fetch_symbol,
        fetched=fetched,
        latest_cached_date=latest_cached_date,
        start_date=start_date,
        timeout=timeout,
        overlap_days=overlap_days,
        batch=False,
    )


def refresh_price_cache_for_symbols(
    symbols: list[PriceRefreshSymbol],
    *,
    range_key: PriceRange = "1y",
    incremental: bool = False,
    timeout: int = 15,
    batch_size: int = 50,
    overlap_days: int = DEFAULT_INCREMENTAL_PRICE_OVERLAP_DAYS,
) -> list[dict]:
    period = YFINANCE_PERIOD_BY_RANGE[range_key]
    normalized = [_normalize_refresh_symbol(symbol) for symbol in symbols]
    normalized = [symbol for symbol in normalized if symbol is not None]
    if not normalized:
        return []

    results: list[dict] = []
    chunk_size = max(1, min(250, int(batch_size)))
    for index in range(0, len(normalized), chunk_size):
        chunk = normalized[index : index + chunk_size]
        results.extend(
            _refresh_price_cache_chunk(
                chunk,
                period=period,
                range_key=range_key,
                incremental=incremental,
                timeout=timeout,
                overlap_days=overlap_days,
            )
        )
    return results


def _refresh_price_cache_chunk(
    symbols: list[PriceRefreshSymbol],
    *,
    period: str,
    range_key: PriceRange,
    incremental: bool,
    timeout: int,
    overlap_days: int,
) -> list[dict]:
    latest_by_ticker: dict[str, date | None] = {}
    for symbol in symbols:
        ticker = _normalize_ticker(symbol.ticker)
        latest_by_ticker[ticker] = _latest_cached_date(ticker) if incremental else None

    if not incremental:
        return _fetch_and_write_price_symbol_group(
            symbols,
            period=period,
            range_key=range_key,
            start=None,
            latest_by_ticker=latest_by_ticker,
            timeout=timeout,
        )

    grouped_by_start: dict[date | None, list[PriceRefreshSymbol]] = {}
    for symbol in symbols:
        ticker = _normalize_ticker(symbol.ticker)
        latest_cached_date = latest_by_ticker.get(ticker)
        start = (
            _incremental_start_date(latest_cached_date, overlap_days=overlap_days)
            if latest_cached_date
            else None
        )
        grouped_by_start.setdefault(start, []).append(symbol)

    result_by_ticker: dict[str, dict] = {}
    for start, group in grouped_by_start.items():
        for item in _fetch_and_write_price_symbol_group(
            group,
            period=period,
            range_key=range_key,
            start=start,
            latest_by_ticker=latest_by_ticker,
            timeout=timeout,
            overlap_days=overlap_days,
        ):
            result_by_ticker[str(item.get("ticker") or "").upper()] = item

    ordered_results: list[dict] = []
    for symbol in symbols:
        ticker = _normalize_ticker(symbol.ticker)
        item = result_by_ticker.get(ticker)
        if item is not None:
            ordered_results.append(item)
    return ordered_results


def _fetch_and_write_price_symbol_group(
    symbols: list[PriceRefreshSymbol],
    *,
    period: str,
    range_key: PriceRange,
    start: date | None,
    latest_by_ticker: dict[str, date | None],
    timeout: int,
    overlap_days: int,
) -> list[dict]:
    fetch_symbols = list(dict.fromkeys(_fetch_symbol(symbol) for symbol in symbols))
    try:
        fetched_by_symbol = fetch_daily_price_bars_batch(
            fetch_symbols,
            period=period,
            start=start,
            timeout=timeout,
        )
    except Exception as exc:
        return _refresh_price_cache_chunk_fallback(
            symbols,
            range_key=range_key,
            incremental=start is not None,
            timeout=timeout,
            overlap_days=overlap_days,
            batch_error=exc,
        )

    results: list[dict] = []
    for symbol in symbols:
        ticker = _normalize_ticker(symbol.ticker)
        fetch_symbol = _fetch_symbol(symbol)
        fetched = fetched_by_symbol.get(fetch_symbol, [])
        if start is not None:
            fetched = [bar for bar in fetched if bar.date >= start]
        results.append(
            _write_price_cache_result(
                ticker=ticker,
                yahoo_symbol=fetch_symbol,
                fetched=fetched,
                latest_cached_date=latest_by_ticker.get(ticker),
                start_date=start,
                timeout=timeout,
                overlap_days=overlap_days,
                batch=True,
                batch_size=len(symbols),
                batch_start_date=start,
            )
        )
    return results


def _refresh_price_cache_chunk_fallback(
    symbols: list[PriceRefreshSymbol],
    *,
    range_key: PriceRange,
    incremental: bool,
    timeout: int,
    overlap_days: int,
    batch_error: Exception,
) -> list[dict]:
    results: list[dict] = []
    for symbol in symbols:
        ticker = _normalize_ticker(symbol.ticker)
        fetch_symbol = _fetch_symbol(symbol)
        try:
            item = refresh_price_cache_for_ticker(
                ticker,
                range_key=range_key,
                yahoo_symbol=fetch_symbol,
                incremental=incremental,
                timeout=timeout,
                overlap_days=overlap_days,
            )
            item["batch_fallback"] = True
            item["batch_error_message"] = f"{type(batch_error).__name__}: {batch_error}"
            results.append(item)
        except Exception as exc:
            results.append(
                {
                    "ticker": ticker,
                    "yahoo_symbol": fetch_symbol,
                    "ok": False,
                    "records_seen": 0,
                    "records_written": 0,
                    "error_message": f"{type(exc).__name__}: {exc}",
                    "batch_error_message": f"{type(batch_error).__name__}: {batch_error}",
                    "source": "yfinance",
                }
            )
    return results


def _write_price_cache_result(
    *,
    ticker: str,
    yahoo_symbol: str,
    fetched: list[FetchedPriceBar],
    latest_cached_date: date | None,
    start_date: date | None,
    timeout: int,
    overlap_days: int,
    batch: bool,
    batch_size: int | None = None,
    batch_start_date: date | None = None,
) -> dict:
    writes = [
        PriceBarWrite(
            date=bar.date,
            open=bar.open,
            high=bar.high,
            low=bar.low,
            close=bar.close,
            adj_close=bar.adj_close,
            volume=bar.volume,
        )
        for bar in fetched
    ]
    written = upsert_price_bars(ticker, writes, yahoo_symbol=yahoo_symbol)
    result = {
        "ticker": ticker,
        "yahoo_symbol": yahoo_symbol,
        "ok": True,
        "records_seen": len(fetched),
        "records_written": written,
        "first_date": fetched[0].date.isoformat() if fetched else None,
        "last_date": fetched[-1].date.isoformat() if fetched else None,
        "fetch_mode": "incremental" if start_date else "range",
        "incremental_start_date": start_date.isoformat() if start_date else None,
        "latest_cached_date": latest_cached_date.isoformat() if latest_cached_date else None,
        "timeout_seconds": max(3, int(timeout)),
        "overlap_days": _normalize_overlap_days(overlap_days),
        "batch": batch,
        "source": "yfinance",
    }
    if batch_size is not None:
        result["batch_size"] = batch_size
    if batch_start_date is not None:
        result["batch_start_date"] = batch_start_date.isoformat()
    return result


def _latest_cached_date(ticker: str) -> date | None:
    try:
        return get_latest_price_bar_date(ticker)
    except PriceRepositoryUnavailable:
        return None


def _incremental_start_date(
    latest_cached_date: date | None,
    *,
    overlap_days: int = DEFAULT_INCREMENTAL_PRICE_OVERLAP_DAYS,
) -> date | None:
    if latest_cached_date is None:
        return None
    # Smart Refresh runs twice per day, so the default overlap stays tight.
    # Larger repair windows can opt in via the job payload.
    return max(date(2000, 1, 1), latest_cached_date - timedelta(days=_normalize_overlap_days(overlap_days)))


def _build_response(
    ticker: str,
    *,
    range_key: PriceRange,
    source: Literal["database", "synthetic_fallback"],
    points: list[PriceBarPoint],
    cache_updated_at: datetime | None,
) -> PriceHistoryResponse:
    first_close = points[0].close if points else None
    last_close = points[-1].close if points else None
    change_pct = None
    if first_close and last_close:
        change_pct = (last_close / first_close - 1) * 100

    as_of = points[-1].date if points else datetime.now(UTC).date().isoformat()
    return PriceHistoryResponse(
        ticker=ticker,
        name=ticker,
        range=range_key,
        source=source,
        data_status="fallback" if source == "synthetic_fallback" else "fresh",
        as_of=as_of,
        first_date=points[0].date if points else None,
        last_date=points[-1].date if points else None,
        cache_updated_at=cache_updated_at,
        last_close=last_close,
        change_pct=change_pct,
        points=points,
    )


def _synthetic_price_points(ticker: str, *, start_date: date) -> list[PriceBarPoint]:
    seed = sum(ord(char) for char in ticker)
    rng = random.Random(seed)
    price = 60 + seed % 140
    trend = ((seed % 17) - 8) / 10000
    points: list[PriceBarPoint] = []
    current = start_date

    while current <= date.today():
        if current.weekday() >= 5:
            current += timedelta(days=1)
            continue

        drift = trend + math.sin(len(points) / 12) * 0.001
        shock = rng.uniform(-0.012, 0.013)
        previous = price
        price = max(2.0, price * (1 + drift + shock))
        high = max(previous, price) * (1 + rng.uniform(0.002, 0.018))
        low = min(previous, price) * (1 - rng.uniform(0.002, 0.018))
        volume = 1_000_000 + rng.randint(0, 7_500_000)
        points.append(
            PriceBarPoint(
                date=current.isoformat(),
                open=round(previous, 2),
                high=round(high, 2),
                low=round(low, 2),
                close=round(price, 2),
                adj_close=round(price, 2),
                volume=float(volume),
            )
        )
        current += timedelta(days=1)

    return points


def _normalize_ticker(ticker: str) -> str:
    clean = ticker.strip().upper()
    if not clean:
        raise ValueError("Ticker must not be empty")
    return clean


def _normalize_refresh_symbol(symbol: PriceRefreshSymbol) -> PriceRefreshSymbol | None:
    try:
        ticker = _normalize_ticker(symbol.ticker)
    except ValueError:
        return None
    yahoo_symbol = (symbol.yahoo_symbol or ticker).strip().upper()
    return PriceRefreshSymbol(ticker=ticker, yahoo_symbol=yahoo_symbol or ticker)


def _fetch_symbol(symbol: PriceRefreshSymbol) -> str:
    return (symbol.yahoo_symbol or symbol.ticker).strip().upper()


def _normalize_overlap_days(value: object) -> int:
    try:
        return max(0, min(30, int(value)))
    except (TypeError, ValueError):
        return DEFAULT_INCREMENTAL_PRICE_OVERLAP_DAYS
