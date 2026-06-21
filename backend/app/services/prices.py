from __future__ import annotations

import math
import random
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Literal

from app.data_sources.yfinance_client import fetch_daily_price_bars, fetch_daily_price_bars_batch
from app.repositories.prices import (
    PriceBarWrite,
    PriceRepositoryUnavailable,
    get_latest_price_bar_date,
    list_price_bars,
    upsert_price_bars,
)
from app.schemas import PriceBarPoint, PriceHistoryResponse


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


@dataclass(frozen=True)
class PriceRefreshSymbol:
    ticker: str
    yahoo_symbol: str | None = None


def get_price_history(ticker: str, *, range_key: PriceRange = "1y") -> PriceHistoryResponse:
    clean = _normalize_ticker(ticker)
    start_date = date.today() - timedelta(days=RANGE_DAYS[range_key])

    try:
        rows = list_price_bars(clean, start_date=start_date)
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
        return _build_response(clean, range_key=range_key, source="database", points=points)

    fallback_points = _synthetic_price_points(clean, start_date=start_date)
    return _build_response(
        clean,
        range_key=range_key,
        source="synthetic_fallback",
        points=fallback_points,
    )


def refresh_price_cache_for_ticker(
    ticker: str,
    *,
    range_key: PriceRange = "1y",
    yahoo_symbol: str | None = None,
    incremental: bool = False,
    timeout: int = 15,
) -> dict:
    clean = _normalize_ticker(ticker)
    fetch_symbol = (yahoo_symbol or clean).strip().upper()
    period = YFINANCE_PERIOD_BY_RANGE[range_key]
    latest_cached_date = _latest_cached_date(clean) if incremental else None
    start_date = _incremental_start_date(latest_cached_date) if latest_cached_date else None
    fetched = fetch_daily_price_bars(fetch_symbol, period=period, start=start_date, timeout=timeout)
    return _write_price_cache_result(
        ticker=clean,
        yahoo_symbol=fetch_symbol,
        fetched=fetched,
        latest_cached_date=latest_cached_date,
        start_date=start_date,
        timeout=timeout,
        batch=False,
    )


def refresh_price_cache_for_symbols(
    symbols: list[PriceRefreshSymbol],
    *,
    range_key: PriceRange = "1y",
    incremental: bool = False,
    timeout: int = 15,
    batch_size: int = 50,
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
) -> list[dict]:
    latest_by_ticker: dict[str, date | None] = {}
    for symbol in symbols:
        ticker = _normalize_ticker(symbol.ticker)
        latest_by_ticker[ticker] = _latest_cached_date(ticker) if incremental else None

    start_by_ticker = {
        ticker: _incremental_start_date(latest_cached_date)
        for ticker, latest_cached_date in latest_by_ticker.items()
        if latest_cached_date is not None
    }
    batch_start = min(start_by_ticker.values()) if len(start_by_ticker) == len(symbols) and start_by_ticker else None
    fetch_symbols = list(dict.fromkeys(_fetch_symbol(symbol) for symbol in symbols))
    try:
        fetched_by_symbol = fetch_daily_price_bars_batch(
            fetch_symbols,
            period=period,
            start=batch_start,
            timeout=timeout,
        )
    except Exception as exc:
        return _refresh_price_cache_chunk_fallback(
            symbols,
            range_key=range_key,
            incremental=incremental,
            timeout=timeout,
            batch_error=exc,
        )

    results: list[dict] = []
    for symbol in symbols:
        ticker = _normalize_ticker(symbol.ticker)
        fetch_symbol = _fetch_symbol(symbol)
        ticker_start = start_by_ticker.get(ticker) if batch_start is not None else None
        fetched = fetched_by_symbol.get(fetch_symbol, [])
        if ticker_start is not None:
            fetched = [bar for bar in fetched if bar.date >= ticker_start]
        results.append(
            _write_price_cache_result(
                ticker=ticker,
                yahoo_symbol=fetch_symbol,
                fetched=fetched,
                latest_cached_date=latest_by_ticker.get(ticker),
                start_date=ticker_start,
                timeout=timeout,
                batch=True,
                batch_size=len(symbols),
                batch_start_date=batch_start,
            )
        )
    return results


def _refresh_price_cache_chunk_fallback(
    symbols: list[PriceRefreshSymbol],
    *,
    range_key: PriceRange,
    incremental: bool,
    timeout: int,
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
    fetched: list,
    latest_cached_date: date | None,
    start_date: date | None,
    timeout: int,
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


def _incremental_start_date(latest_cached_date: date | None) -> date | None:
    if latest_cached_date is None:
        return None
    # A small overlap keeps the most recent adjusted prices and late provider updates consistent.
    return max(date(2000, 1, 1), latest_cached_date - timedelta(days=7))


def _build_response(
    ticker: str,
    *,
    range_key: PriceRange,
    source: Literal["database", "synthetic_fallback"],
    points: list[PriceBarPoint],
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
