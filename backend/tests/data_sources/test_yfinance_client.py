from __future__ import annotations

from datetime import date

import pandas as pd

from app.data_sources.yfinance_client import fetch_daily_price_bars


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
