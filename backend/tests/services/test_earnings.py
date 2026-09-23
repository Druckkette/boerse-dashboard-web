from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace

from app.data_sources.earnings_client import EarningsCalendarEntry
from app.services import earnings


def test_refresh_earnings_calendar_uses_nasdaq_without_fmp(monkeypatch) -> None:
    captured = {}

    def fail_fmp(**kwargs):
        raise RuntimeError("FMP Earnings-Kalender: HTTP 429 (Limit Reach)")

    def fetch_nasdaq(**kwargs):
        captured["nasdaq_window"] = (kwargs["start_date"], kwargs["end_date"])
        return [
            EarningsCalendarEntry(
                ticker="AAPL",
                event_date=date(2026, 8, 6),
                fiscal_date_ending=date(2026, 6, 30),
                time="time-after-hours",
                eps_estimated=1.88,
                eps_actual=None,
                revenue_estimated=None,
                revenue_actual=None,
                source="nasdaq",
                raw={"symbol": "AAPL"},
            )
        ]

    def replace(rows, **kwargs):
        captured["rows"] = rows
        captured["replace"] = kwargs
        return len(rows)

    monkeypatch.setattr(earnings, "fetch_fmp_earnings_calendar", fail_fmp)
    monkeypatch.setattr(earnings, "fetch_nasdaq_earnings_calendar", fetch_nasdaq)
    monkeypatch.setattr(earnings.earnings_repository, "replace_earnings_window", replace)

    result = earnings.refresh_earnings_calendar(
        api_key="limited-key",
        start_date=date(2026, 7, 27),
        end_date=date(2026, 12, 1),
    )

    assert result["ok"] is True
    assert result["source"] == "nasdaq"
    assert "fallback_reason" not in result
    assert result["records_written"] == 1
    assert captured["nasdaq_window"] == (
        date(2026, 7, 27),
        min(date(2026, 12, 1), date.today() + timedelta(days=35)),
    )
    assert captured["replace"]["replace_sources"] == ("nasdaq",)
    assert captured["rows"][0].source == "nasdaq"


def test_nasdaq_missing_uses_yahoo_before_fmp(monkeypatch) -> None:
    from app.repositories import portfolio
    from app.services import workspace

    monkeypatch.setattr(earnings, "fetch_nasdaq_earnings_calendar", lambda **kwargs: [])
    monkeypatch.setattr(portfolio, "list_open_positions", lambda: [SimpleNamespace(ticker="AAPL")])
    monkeypatch.setattr(workspace, "get_workspace_state", lambda: SimpleNamespace(watchlist=[], recent_tickers=[]))
    monkeypatch.setattr(earnings, "fetch_fmp_earnings_calendar", lambda **kwargs: (_ for _ in ()).throw(AssertionError("FMP called")))
    monkeypatch.setattr(earnings, "fetch_yfinance_earnings_calendar", lambda **kwargs: [
        EarningsCalendarEntry("AAPL", date.today() + timedelta(days=5), None, "", None, None,
                              None, None, "yfinance", {})])
    monkeypatch.setattr(earnings.earnings_repository, "replace_earnings_window", lambda rows, **kwargs: len(rows))
    result = earnings.refresh_earnings_calendar(api_key="key")
    assert result["source"] == "yfinance"
    assert result["records_written"] == 1
