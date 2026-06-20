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


@dataclass(frozen=True)
class FetchedFundamentals:
    ticker: str
    as_of: date
    source: str
    fiscal_period: str
    quarterly_eps_growth_pct: float | None
    annual_eps_growth_pct: float | None
    quarterly_revenue_growth_pct: float | None
    annual_revenue_growth_pct: float | None
    roe_pct: float | None
    profit_margin_pct: float | None
    trailing_eps: float | None
    institutional_holders: int | None
    institutional_ownership_pct: float | None
    next_earnings_date: date | None
    beta: float | None


def fetch_daily_price_bars(
    symbol: str,
    *,
    period: str = "1y",
    start: date | None = None,
) -> list[FetchedPriceBar]:
    """Fetch daily OHLC bars from yfinance for worker-side cache refreshes."""
    import yfinance as yf

    clean_symbol = symbol.strip().upper()
    if not clean_symbol:
        return []

    download_kwargs = {
        "interval": "1d",
        "auto_adjust": False,
        "progress": False,
        "threads": False,
    }
    if start is not None:
        download_kwargs["start"] = start.isoformat()
    else:
        download_kwargs["period"] = period

    frame = yf.download(clean_symbol, **download_kwargs)
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


def probe_daily_price_symbol(symbol: str, *, period: str = "1mo") -> dict:
    """Return a compact yfinance availability probe for a symbol candidate."""
    clean_symbol = symbol.strip().upper()
    if not clean_symbol:
        return {"symbol": clean_symbol, "ok": False, "records_seen": 0, "error_message": "Leeres Symbol."}
    try:
        bars = fetch_daily_price_bars(clean_symbol, period=period)
    except Exception as exc:
        return {
            "symbol": clean_symbol,
            "ok": False,
            "records_seen": 0,
            "error_message": f"{type(exc).__name__}: {exc}",
        }
    return {
        "symbol": clean_symbol,
        "ok": bool(bars),
        "records_seen": len(bars),
        "last_date": bars[-1].date.isoformat() if bars else None,
        "last_close": bars[-1].close if bars else None,
        "error_message": "" if bars else "Keine Daily-Bars gefunden.",
    }


def fetch_fundamentals(symbol: str, *, include_holders: bool = True) -> FetchedFundamentals:
    """Fetch a compact fundamental snapshot for worker-side caching."""
    import yfinance as yf

    clean_symbol = symbol.strip().upper()
    if not clean_symbol:
        raise ValueError("symbol must not be empty")

    ticker = yf.Ticker(clean_symbol)
    info = _safe_info(ticker)
    return FetchedFundamentals(
        ticker=clean_symbol,
        as_of=date.today(),
        source="yfinance",
        fiscal_period=str(info.get("mostRecentQuarter") or info.get("lastFiscalYearEnd") or ""),
        quarterly_eps_growth_pct=_ratio_to_pct(
            info.get("earningsQuarterlyGrowth") or info.get("quarterlyEarningsGrowth")
        ),
        annual_eps_growth_pct=_ratio_to_pct(info.get("earningsGrowth")),
        quarterly_revenue_growth_pct=_ratio_to_pct(
            info.get("revenueGrowth") or info.get("quarterlyRevenueGrowth")
        ),
        annual_revenue_growth_pct=_ratio_to_pct(info.get("annualRevenueGrowth")),
        roe_pct=_ratio_to_pct(info.get("returnOnEquity")),
        profit_margin_pct=_ratio_to_pct(info.get("profitMargins")),
        trailing_eps=_float_or_none(info.get("trailingEps")),
        institutional_holders=None,
        institutional_ownership_pct=None,
        next_earnings_date=_next_earnings_date(ticker),
        beta=_float_or_none(info.get("beta")),
    )


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


def _safe_info(ticker: Any) -> dict:
    try:
        info = ticker.get_info()
    except Exception:
        try:
            info = ticker.info
        except Exception:
            info = {}
    return info if isinstance(info, dict) else {}


def _next_earnings_date(ticker: Any) -> date | None:
    try:
        frame = ticker.get_earnings_dates(limit=12)
    except Exception:
        return None
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return None
    now = pd.Timestamp.utcnow()
    try:
        index = pd.DatetimeIndex(frame.index)
    except Exception:
        return None
    if index.tz is None:
        index = index.tz_localize("UTC")
    else:
        index = index.tz_convert("UTC")
    future = index[index > now]
    if future.empty:
        return None
    return future.min().date()


def _ratio_to_pct(value: Any) -> float | None:
    number = _float_or_none(value)
    if number is None:
        return None
    if abs(number) <= 5:
        return number * 100
    return number


def _float_or_none(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    number = float(value)
    if isnan(number):
        return None
    return number
