from __future__ import annotations

from datetime import date

import pytest

from app.data_sources import earnings_client


class _Response:
    def __init__(self, status_code: int, payload, text: str = "") -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self):
        return self._payload


def test_fmp_earnings_calendar_uses_stable_endpoint_and_date_window(monkeypatch) -> None:
    captured = {}

    def fake_get(url, *, params, timeout):
        captured.update({"url": url, "params": params, "timeout": timeout})
        return _Response(
            200,
            [
                {
                    "symbol": "NVDA",
                    "date": "2026-08-20",
                    "time": "amc",
                    "epsEstimated": 1.23,
                    "revenueEstimated": 50_000_000_000,
                }
            ],
        )

    monkeypatch.setattr(earnings_client.requests, "get", fake_get)
    rows = earnings_client.fetch_fmp_earnings_calendar(
        api_key="test-key",
        start_date=date(2026, 7, 31),
        end_date=date(2026, 11, 30),
    )

    assert captured["url"] == "https://financialmodelingprep.com/stable/earnings-calendar"
    assert captured["params"] == {
        "from": "2026-07-31",
        "to": "2026-11-30",
        "apikey": "test-key",
    }
    assert rows[0].ticker == "NVDA"
    assert rows[0].event_date == date(2026, 8, 20)


def test_fmp_earnings_calendar_preserves_error_body(monkeypatch) -> None:
    monkeypatch.setattr(
        earnings_client.requests,
        "get",
        lambda *args, **kwargs: _Response(403, {}, "plan does not permit this endpoint"),
    )

    with pytest.raises(RuntimeError, match="plan does not permit"):
        earnings_client.fetch_fmp_earnings_calendar(
            api_key="test-key",
            start_date=date(2026, 7, 31),
            end_date=date(2026, 8, 31),
        )
