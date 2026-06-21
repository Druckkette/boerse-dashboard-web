from __future__ import annotations

from datetime import date

from app.data_sources.yfinance_client import FetchedPriceBar
from app.services import prices as prices_service


def test_incremental_batch_keeps_cached_symbols_incremental_when_missing_symbol_is_present(monkeypatch) -> None:
    latest_dates = {"AAA": date(2026, 6, 17), "BBB": None}
    fetch_calls: list[dict] = []

    monkeypatch.setattr(prices_service, "get_latest_price_bar_date", lambda ticker: latest_dates[ticker])
    monkeypatch.setattr(prices_service, "upsert_price_bars", lambda ticker, bars, **kwargs: len(list(bars)))

    def fake_fetch_batch(symbols: list[str], *, period: str, start: date | None = None, timeout: int = 15):
        fetch_calls.append({"symbols": symbols, "period": period, "start": start, "timeout": timeout})
        bar_date = start or date(2026, 1, 2)
        return {symbol: [_bar(bar_date)] for symbol in symbols}

    monkeypatch.setattr(prices_service, "fetch_daily_price_bars_batch", fake_fetch_batch)

    result = prices_service.refresh_price_cache_for_symbols(
        [
            prices_service.PriceRefreshSymbol(ticker="AAA", yahoo_symbol="AAA"),
            prices_service.PriceRefreshSymbol(ticker="BBB", yahoo_symbol="BBB"),
        ],
        range_key="6m",
        incremental=True,
        timeout=11,
        batch_size=50,
    )

    assert fetch_calls == [
        {"symbols": ["AAA"], "period": "1y", "start": date(2026, 6, 10), "timeout": 11},
        {"symbols": ["BBB"], "period": "1y", "start": None, "timeout": 11},
    ]
    assert result[0]["ticker"] == "AAA"
    assert result[0]["fetch_mode"] == "incremental"
    assert result[0]["incremental_start_date"] == "2026-06-10"
    assert result[1]["ticker"] == "BBB"
    assert result[1]["fetch_mode"] == "range"
    assert result[1]["incremental_start_date"] is None


def test_incremental_batch_groups_symbols_with_same_start_date(monkeypatch) -> None:
    latest_dates = {"AAA": date(2026, 6, 17), "MSFT": date(2026, 6, 17)}
    fetch_calls: list[dict] = []

    monkeypatch.setattr(prices_service, "get_latest_price_bar_date", lambda ticker: latest_dates[ticker])
    monkeypatch.setattr(prices_service, "upsert_price_bars", lambda ticker, bars, **kwargs: len(list(bars)))

    def fake_fetch_batch(symbols: list[str], *, period: str, start: date | None = None, timeout: int = 15):
        fetch_calls.append({"symbols": symbols, "period": period, "start": start})
        return {symbol: [_bar(start or date(2026, 1, 2))] for symbol in symbols}

    monkeypatch.setattr(prices_service, "fetch_daily_price_bars_batch", fake_fetch_batch)

    result = prices_service.refresh_price_cache_for_symbols(
        [
            prices_service.PriceRefreshSymbol(ticker="AAA", yahoo_symbol="AAA"),
            prices_service.PriceRefreshSymbol(ticker="MSFT", yahoo_symbol="MSFT"),
        ],
        range_key="6m",
        incremental=True,
        batch_size=50,
    )

    assert fetch_calls == [{"symbols": ["AAA", "MSFT"], "period": "1y", "start": date(2026, 6, 10)}]
    assert [item["fetch_mode"] for item in result] == ["incremental", "incremental"]


def _bar(bar_date: date) -> FetchedPriceBar:
    return FetchedPriceBar(
        date=bar_date,
        open=100.0,
        high=101.0,
        low=99.0,
        close=100.5,
        adj_close=100.5,
        volume=1_000_000,
    )
