"""The repair boundary must receive real history errors without global switches."""

from datetime import date
from types import SimpleNamespace

import pandas as pd
import pytest
import yfinance as yf
from yfinance.config import NestedConfig
from yfinance.exceptions import YFRateLimitError

from app.data_sources import yfinance_client as client


@pytest.fixture
def history(monkeypatch):
    frame = pd.DataFrame(
        {
            "Open": [24.5, 25.0],
            "High": [25.5, 26.5],
            "Low": [24.0, 24.5],
            "Close": [25.0, 26.0],
            "Adj Close": [24.8, 26.0],
            "Volume": [1000.0, 2000.0],
            "Stock Splits": [0.0, 4.0],
        },
        index=pd.to_datetime(["2026-06-11", "2026-06-12"]),
    )
    calls, events = [], []

    def ticker(symbol):
        def fetch(**kwargs):
            calls.append((symbol, kwargs))
            return frame.copy()

        return SimpleNamespace(history=fetch)

    monkeypatch.setattr(yf, "Ticker", ticker)
    monkeypatch.setattr(client, "record_provider_event", events.append)

    def no_download(*args, **kwargs):
        raise AssertionError("The strict boundary must not call yf.download")

    monkeypatch.setattr(yf, "download", no_download)
    return SimpleNamespace(frame=frame, calls=calls, events=events)


def test_strict_history_keeps_provider_prices_and_split_parser_semantics(history):
    bars = client.fetch_daily_price_bars_strict(
        " test ", start=date(2026, 6, 11), end=date(2026, 6, 13), timeout=1
    )
    assert bars == client._bars_from_frame(history.frame)
    assert [bar.close for bar in bars] == [25, 26]
    assert [bar.stock_split for bar in bars] == [0, 4]
    assert [bar.split_adjustment_factor for bar in bars] == [4, 1]
    assert history.calls == [
        (
            "TEST",
            {
                "interval": "1d",
                "auto_adjust": False,
                "actions": True,
                "timeout": 3,
                "start": "2026-06-11",
                "end": "2026-06-13",
                "back_adjust": False,
                "repair": False,
                "rounding": False,
                "keepna": True,
                "raise_errors": True,
            },
        )
    ]
    assert history.events == ["yahoo_requests"]


def test_strict_history_uses_period_when_no_start_is_given(history):
    client.fetch_daily_price_bars_strict("TEST", period="5y", timeout=8)
    kwargs = history.calls[0][1]
    assert kwargs["period"] == "5y" and kwargs["timeout"] == 8
    assert "start" not in kwargs and "end" not in kwargs


@pytest.mark.parametrize("error", [YFRateLimitError(), RuntimeError("provider failure")])
def test_history_exception_propagates_once_without_retry_or_fallback(history, monkeypatch, error):
    calls = []

    def fetch(**kwargs):
        calls.append(kwargs)
        raise error

    monkeypatch.setattr(yf, "Ticker", lambda symbol: SimpleNamespace(history=fetch))
    with pytest.raises(type(error)) as raised:
        client.fetch_daily_price_bars_strict("TEST")
    assert raised.value is error
    assert len(calls) == 1 and calls[0]["raise_errors"] is True
    assert history.events == ["yahoo_requests"]


def test_strict_history_does_not_mutate_shared_yfinance_configuration(history, monkeypatch):
    # Initialize before guarding writes, so even a temporary global switch fails.
    before = repr(yf.config)

    def reject_write(self, key, value):
        raise AssertionError(f"Global yfinance configuration changed: {key}")

    monkeypatch.setattr(NestedConfig, "__setattr__", reject_write)
    client.fetch_daily_price_bars_strict("TEST")
    assert repr(yf.config) == before


def test_blank_symbol_spends_no_request_budget(history):
    assert client.fetch_daily_price_bars_strict("  ") == []
    assert not history.calls and not history.events


def test_empty_history_remains_distinct_from_provider_failure(history):
    history.frame.drop(history.frame.index, inplace=True)
    assert client.fetch_daily_price_bars_strict("TEST") == []
    assert len(history.calls) == 1
