from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from math import isnan
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class FetchedPriceBar:
    date: date
    open: float | None
    high: float | None
    low: float | None
    close: float
    adj_close: float | None
    volume: float | None


def fetch_daily_price_bars(symbol: str, *, period: str = "1y") -> list[FetchedPriceBar]:
    """Fetch daily OHLC bars from yfinance for worker-side cache refreshes."""
    import yfinance as yf

    clean_symbol = symbol.strip().upper()
    if not clean_symbol:
        return []

    frame = yf.download(
        clean_symbol,
        period=period,
        interval="1d",
        auto_adjust=False,
        progress=False,
        threads=False,
    )
    if frame.empty:
        return []

    normalized = _normalize_download_frame(frame, clean_symbol)
    if "Close" not in normalized.columns:
        return []

    normalized = normalized.dropna(subset=["Close"])
    bars: list[FetchedPriceBar] = []
    for index, row in normalized.iterrows():
        bar_date = index.date() if hasattr(index, "date") else pd.Timestamp(index).date()
        close = _float_or_none(row.get("Close"))
        if close is None:
            continue
        bars.append(
            FetchedPriceBar(
                date=bar_date,
                open=_float_or_none(row.get("Open")),
                high=_float_or_none(row.get("High")),
                low=_float_or_none(row.get("Low")),
                close=close,
                adj_close=_float_or_none(row.get("Adj Close")),
                volume=_float_or_none(row.get("Volume")),
            )
        )
    return bars


def _normalize_download_frame(frame: pd.DataFrame, symbol: str) -> pd.DataFrame:
    if not isinstance(frame.columns, pd.MultiIndex):
        return frame

    last_level = frame.columns.get_level_values(-1)
    if symbol in set(str(value).upper() for value in last_level):
        for value in last_level:
            if str(value).upper() == symbol:
                return frame.xs(value, axis=1, level=-1)

    first_level = frame.columns.get_level_values(0)
    if symbol in set(str(value).upper() for value in first_level):
        for value in first_level:
            if str(value).upper() == symbol:
                return frame.xs(value, axis=1, level=0)

    flat = frame.copy()
    flat.columns = [str(column[0]) for column in flat.columns]
    return flat


def _float_or_none(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    number = float(value)
    if isnan(number):
        return None
    return number
