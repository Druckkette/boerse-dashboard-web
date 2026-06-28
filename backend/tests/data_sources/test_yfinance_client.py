from __future__ import annotations

from datetime import date

import pandas as pd

from app.data_sources.yfinance_client import fetch_after_hours_quotes, fetch_daily_price_bars, fetch_daily_price_bars_batch


def test_fetch_daily_price_bars_passes_explicit_timeout(monkeypatch) -> None:
    import yfinance as yf

    seen: dict[str, object] = {}

    def fake_download(symbol: str, **kwargs):
        seen["symbol"] = symbol
        seen.update(kwargs)
        return pd.DataFrame(
            [
                {
                    "Open": 100.0,
                    "High": 102.0,
                    "Low": 99.0,
                    "Close": 101.0,
                    "Adj Close": 101.0,
                    "Volume": 1_000_000,
                }
            ],
            index=[pd.Timestamp(date(2026, 6, 19))],
        )

    monkeypatch.setattr(yf, "download", fake_download)

    bars = fetch_daily_price_bars("AAPL", period="1mo", timeout=7)

    assert len(bars) == 1
    assert seen["symbol"] == "AAPL"
    assert seen["timeout"] == 7
    assert seen["threads"] is False


def test_fetch_daily_price_bars_batch_splits_multi_ticker_frame(monkeypatch) -> None:
    import yfinance as yf

    seen: dict[str, object] = {}
    columns = pd.MultiIndex.from_tuples(
        [
            ("Open", "AAPL"),
            ("High", "AAPL"),
            ("Low", "AAPL"),
            ("Close", "AAPL"),
            ("Adj Close", "AAPL"),
            ("Volume", "AAPL"),
            ("Open", "MSFT"),
            ("High", "MSFT"),
            ("Low", "MSFT"),
            ("Close", "MSFT"),
            ("Adj Close", "MSFT"),
            ("Volume", "MSFT"),
        ]
    )
    frame = pd.DataFrame(
        [[100.0, 102.0, 99.0, 101.0, 101.0, 1_000_000, 200.0, 205.0, 198.0, 204.0, 204.0, 2_000_000]],
        columns=columns,
        index=[pd.Timestamp(date(2026, 6, 19))],
    )

    def fake_download(symbols: list[str], **kwargs):
        seen["symbols"] = symbols
        seen.update(kwargs)
        return frame

    monkeypatch.setattr(yf, "download", fake_download)

    result = fetch_daily_price_bars_batch(["AAPL", "MSFT"], period="1mo", timeout=9)

    assert seen["symbols"] == ["AAPL", "MSFT"]
    assert seen["timeout"] == 9
    assert result["AAPL"][0].close == 101.0
    assert result["MSFT"][0].close == 204.0


def test_fetch_daily_price_bars_batch_does_not_reuse_other_symbol_data(monkeypatch) -> None:
    import yfinance as yf

    columns = pd.MultiIndex.from_tuples(
        [
            ("Open", "AAPL"),
            ("High", "AAPL"),
            ("Low", "AAPL"),
            ("Close", "AAPL"),
            ("Adj Close", "AAPL"),
            ("Volume", "AAPL"),
        ]
    )
    frame = pd.DataFrame(
        [[100.0, 102.0, 99.0, 101.0, 101.0, 1_000_000]],
        columns=columns,
        index=[pd.Timestamp(date(2026, 6, 19))],
    )

    monkeypatch.setattr(yf, "download", lambda symbols, **kwargs: frame)

    result = fetch_daily_price_bars_batch(["AAPL", "MSFT"], period="1mo", timeout=9)

    assert result["AAPL"][0].close == 101.0
    assert result["MSFT"] == []


def test_fetch_after_hours_quotes_uses_post_market_price(monkeypatch) -> None:
    import yfinance as yf

    class FakeTicker:
        def __init__(self, symbol: str) -> None:
            self.symbol = symbol

        def get_info(self) -> dict:
            return {
                "regularMarketPrice": 100.0,
                "postMarketPrice": 102.5,
                "currency": "USD",
                "marketState": "POST",
            }

    monkeypatch.setattr(yf, "Ticker", FakeTicker)

    quotes = fetch_after_hours_quotes(["AAPL"])

    quote = quotes["AAPL"]
    assert quote.regular_price == 100.0
    assert quote.after_hours_price == 102.5
    assert quote.after_hours_change == 2.5
    assert quote.after_hours_change_pct == 2.5
    assert quote.market_state == "POST"
