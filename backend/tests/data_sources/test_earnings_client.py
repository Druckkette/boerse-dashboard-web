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


class _Session:
    def __init__(self, responses: dict[str, _Response]) -> None:
        self.responses = responses
        self.headers = {}
        self.calls = []

    def get(self, url, *, params, timeout):
        self.calls.append({"url": url, "params": params, "timeout": timeout})
        return self.responses[params["date"]]


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
    assert rows[0].source == "fmp"


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


def test_nasdaq_earnings_calendar_parses_weekdays_and_skips_weekend() -> None:
    session = _Session(
        {
            "2026-07-31": _Response(
                200,
                {
                    "data": {
                        "rows": [
                            {
                                "symbol": "AAPL",
                                "time": "time-after-hours",
                                "fiscalQuarterEnding": "Jun/2026",
                                "epsForecast": "$1.88",
                            }
                        ]
                    }
                },
            ),
            "2026-08-03": _Response(200, {"data": {"rows": []}}),
        }
    )

    rows = earnings_client.fetch_nasdaq_earnings_calendar(
        start_date=date(2026, 7, 31),
        end_date=date(2026, 8, 3),
        session=session,
    )

    assert [call["params"]["date"] for call in session.calls] == [
        "2026-07-31",
        "2026-08-03",
    ]
    assert rows[0].ticker == "AAPL"
    assert rows[0].event_date == date(2026, 7, 31)
    assert rows[0].fiscal_date_ending == date(2026, 6, 30)
    assert rows[0].eps_estimated == 1.88
    assert rows[0].time == "amc"
    assert rows[0].source == "nasdaq"


def test_nasdaq_earnings_calendar_reports_provider_error() -> None:
    session = _Session(
        {
            "2026-07-31": _Response(403, {}, "request blocked"),
        }
    )

    with pytest.raises(RuntimeError, match="HTTP 403.*request blocked"):
        earnings_client.fetch_nasdaq_earnings_calendar(
            start_date=date(2026, 7, 31),
            end_date=date(2026, 7, 31),
            session=session,
        )
