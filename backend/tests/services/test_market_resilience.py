from datetime import date
from types import SimpleNamespace

from app.services import market


def test_overview_does_not_compute_full_ampel(monkeypatch):
    monkeypatch.setattr(market.market_repository, "get_latest_market_snapshot", lambda: SimpleNamespace())
    monkeypatch.setattr(market, "_market_trend_ampel_for_ticker", lambda *a, **k: "trend")
    monkeypatch.setattr(market, "_build_market_overview_response", lambda ticker, snapshot, trend: trend)
    def unexpected(**kwargs):
        raise AssertionError("overview must not load the full ampel")
    monkeypatch.setattr(market, "get_market_ampel", unexpected)
    assert market.get_market_overview() == "trend"


def test_optional_source_failure_is_explicit():
    errors = []
    def fail():
        raise TimeoutError("source unavailable")
    assert market._optional_market_component("Volatilität", fail, [], errors) == []
    assert errors == ["Volatilität: Abruf fehlgeschlagen"]


def test_daily_confirmation_computes_calendar_boundary_once(monkeypatch):
    calls = []
    from app.services.market_calendar import completed_us_market_session
    def completed(now=None):
        calls.append(1)
        return completed_us_market_session(now)
    monkeypatch.setattr(market, "completed_us_market_session", completed)
    bars = [SimpleNamespace(date=date(2025, 1, 2), fetched_at=None) for _ in range(500)]
    assert len(market._confirmed_ampel_bars(bars)) == 500
    assert len(calls) == 1
