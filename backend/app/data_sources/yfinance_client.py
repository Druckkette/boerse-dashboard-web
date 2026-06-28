from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
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


@dataclass(frozen=True)
class FetchedAfterHoursQuote:
    ticker: str
    regular_price: float | None
    after_hours_price: float | None
    after_hours_change: float | None
    after_hours_change_pct: float | None
    currency: str
    market_state: str
    source: str
    fetched_at: datetime
    error_message: str = ""


def fetch_daily_price_bars(
    symbol: str,
    *,
    period: str = "1y",
    start: date | None = None,
    timeout: int = 15,
) -> list[FetchedPriceBar]:
    """Fetch daily OHLC bars from yfinance for worker-side cache refreshes."""
    import yfinance as yf

    clean_symbol = symbol.strip().upper()
    if not clean_symbol:
        return []

    download_kwargs = _download_kwargs(period=period, start=start, timeout=timeout)
    frame = yf.download(clean_symbol, **download_kwargs)
    if frame.empty:
        return []

    normalized = _normalize_download_frame(frame, clean_symbol)
    return _bars_from_frame(normalized)


def fetch_daily_price_bars_batch(
    symbols: list[str],
    *,
    period: str = "1y",
    start: date | None = None,
    timeout: int = 15,
) -> dict[str, list[FetchedPriceBar]]:
    """Fetch daily OHLC bars for several symbols with one yfinance request."""
    import yfinance as yf

    clean_symbols = list(dict.fromkeys(symbol.strip().upper() for symbol in symbols if symbol and symbol.strip()))
    if not clean_symbols:
        return {}
    if len(clean_symbols) == 1:
        return {
            clean_symbols[0]: fetch_daily_price_bars(
                clean_symbols[0],
                period=period,
                start=start,
                timeout=timeout,
            )
        }

    download_kwargs = _download_kwargs(period=period, start=start, timeout=timeout)
    download_kwargs["group_by"] = "column"
    frame = yf.download(clean_symbols, **download_kwargs)
    if frame.empty:
        return {symbol: [] for symbol in clean_symbols}

    result: dict[str, list[FetchedPriceBar]] = {}
    for symbol in clean_symbols:
        normalized = _normalize_download_frame(frame, symbol)
        result[symbol] = _bars_from_frame(normalized)
    return result


def fetch_after_hours_quotes(symbols: list[str]) -> dict[str, FetchedAfterHoursQuote]:
    """Fetch Yahoo quote data for portfolio after-hours display.

    yfinance exposes Yahoo's quote fields through ``Ticker.get_info()``. The
    important fields for this use case are ``postMarketPrice`` and the regular
    market price. Missing post-market data is returned as an unavailable quote
    instead of falling back silently to the regular close.
    """
    import yfinance as yf

    clean_symbols = list(dict.fromkeys(symbol.strip().upper() for symbol in symbols if symbol and symbol.strip()))
    fetched_at = datetime.now(UTC)
    quotes: dict[str, FetchedAfterHoursQuote] = {}
    for symbol in clean_symbols:
        try:
            info = _safe_info(yf.Ticker(symbol))
            regular_price = _first_float(
                info,
                "regularMarketPrice",
                "currentPrice",
                "regularMarketPreviousClose",
                "previousClose",
            )
            after_price = _first_float(info, "postMarketPrice")
            after_change = _first_float(info, "postMarketChange")
            after_change_pct = _normalize_percent(_first_float(info, "postMarketChangePercent"))
            if after_price is None and after_change is not None and regular_price is not None:
                after_price = regular_price + after_change
            if after_price is not None and regular_price is not None and regular_price > 0:
                after_change = after_price - regular_price
                after_change_pct = after_change / regular_price * 100
            quotes[symbol] = FetchedAfterHoursQuote(
                ticker=symbol,
                regular_price=regular_price,
                after_hours_price=after_price,
                after_hours_change=after_change,
                after_hours_change_pct=after_change_pct,
                currency=str(info.get("currency") or "USD"),
                market_state=str(info.get("marketState") or ""),
                source="yfinance",
                fetched_at=fetched_at,
                error_message="" if after_price is not None else "Yahoo liefert aktuell keinen After-Market-Kurs.",
            )
        except Exception as exc:  # noqa: BLE001 - a single quote failure must not break the portfolio response
            quotes[symbol] = FetchedAfterHoursQuote(
                ticker=symbol,
                regular_price=None,
                after_hours_price=None,
                after_hours_change=None,
                after_hours_change_pct=None,
                currency="USD",
                market_state="",
                source="yfinance",
                fetched_at=fetched_at,
                error_message=f"{type(exc).__name__}: {exc}",
            )
    return quotes


def _download_kwargs(*, period: str, start: date | None, timeout: int) -> dict[str, Any]:
    download_kwargs: dict[str, Any] = {
        "interval": "1d",
        "auto_adjust": False,
        "progress": False,
        "threads": False,
        "timeout": max(3, int(timeout)),
    }
    if start is not None:
        download_kwargs["start"] = start.isoformat()
    else:
        download_kwargs["period"] = period
    return download_kwargs


def _bars_from_frame(normalized: pd.DataFrame) -> list[FetchedPriceBar]:
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

    return pd.DataFrame(index=frame.index)


def _safe_info(ticker: Any) -> dict:
    try:
        info = ticker.get_info()
    except Exception:
        try:
            info = ticker.info
        except Exception:
            info = {}
    return info if isinstance(info, dict) else {}


def _first_float(source: dict, *keys: str) -> float | None:
    for key in keys:
        value = _float_or_none(source.get(key))
        if value is not None:
            return value
    return None


def _normalize_percent(value: float | None) -> float | None:
    if value is None:
        return None
    # Yahoo/yfinance has returned both 0.42 and 0.0042 style values over time.
    return value * 100 if abs(value) <= 1 else value


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
