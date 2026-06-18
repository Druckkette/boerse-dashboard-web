from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from app.data_sources.yfinance_client import fetch_daily_price_bars
from app.repositories import prices as prices_repository
from app.repositories.prices import PriceBarWrite, PriceRepositoryUnavailable


EUR_USD_TICKER = "EURUSD=X"
EUR_USD_FALLBACK_RATE = 1.08
FX_CACHE_TTL_SECONDS = 3600


@dataclass(frozen=True)
class FxRate:
    pair: str
    rate: float
    as_of: date
    source: str


_cached_eur_usd: tuple[datetime, FxRate] | None = None


def get_eur_usd_rate(*, force_refresh: bool = False) -> FxRate:
    global _cached_eur_usd
    now = datetime.now(UTC)
    if not force_refresh and _cached_eur_usd is not None:
        cached_at, cached_rate = _cached_eur_usd
        if (now - cached_at).total_seconds() <= FX_CACHE_TTL_SECONDS:
            return cached_rate

    rate = _latest_cached_eur_usd_rate()
    if rate is None:
        rate = _fetch_eur_usd_rate()
    if rate is None:
        rate = FxRate(pair="EUR/USD", rate=EUR_USD_FALLBACK_RATE, as_of=date.today(), source="fallback")

    _cached_eur_usd = (now, rate)
    return rate


def eur_to_usd(value: float | None, *, rate: FxRate | None = None) -> float | None:
    if value is None:
        return None
    clean = float(value)
    return clean * float((rate or get_eur_usd_rate()).rate)


def _latest_cached_eur_usd_rate() -> FxRate | None:
    start_date = date.today() - timedelta(days=14)
    try:
        rows = prices_repository.list_price_bars(EUR_USD_TICKER, start_date=start_date)
    except PriceRepositoryUnavailable:
        rows = []
    for row in reversed(rows):
        if row.close is not None and float(row.close) > 0:
            return FxRate(pair="EUR/USD", rate=float(row.close), as_of=row.date, source="price_cache")
    return None


def _fetch_eur_usd_rate() -> FxRate | None:
    try:
        bars = fetch_daily_price_bars(EUR_USD_TICKER, period="5d")
    except Exception:
        return None
    if not bars:
        return None

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
        for bar in bars
    ]
    try:
        prices_repository.upsert_price_bars(EUR_USD_TICKER, writes, yahoo_symbol=EUR_USD_TICKER)
    except PriceRepositoryUnavailable:
        pass

    latest = bars[-1]
    if latest.close <= 0:
        return None
    return FxRate(pair="EUR/USD", rate=float(latest.close), as_of=latest.date, source="yfinance")
