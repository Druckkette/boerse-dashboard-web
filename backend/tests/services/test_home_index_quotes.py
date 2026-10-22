from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.repositories.market import MarketClosePair
from app.services import home


@pytest.fixture
def clock(monkeypatch):
    now = datetime(2026, 10, 22, 18, tzinfo=UTC)
    monkeypatch.setattr(home, "datetime", SimpleNamespace(now=lambda tz: now))
    monkeypatch.setattr(home, "expected_us_market_session", lambda: SimpleNamespace(date=now.date(), phase="intraday"))
    monkeypatch.setattr(home, "completed_us_market_session", lambda: SimpleNamespace(date=date(2026, 10, 21)))
    monkeypatch.setattr(home, "daily_bar_is_final", lambda day, fetched: day < now.date() or fetched is not None and fetched.hour >= 20)
    return now


def bar(day, price, fetched):
    return MarketClosePair(ticker="^IXIC", date=day, close=price, fetched_at=fetched)


def test_current_quote_does_not_replace_the_confirmed_signal_close(clock):
    rows = [bar(date(2026, 10, 20), 100, clock), bar(date(2026, 10, 21), 102, clock), bar(clock.date(), 105, clock)]
    result = home._index_summary("^IXIC", "Nasdaq", rows)
    assert result["close"] == 102
    assert result["as_of"] == "2026-10-21"
    assert result["quote"]["price"] == 105
    assert result["quote"]["as_of"] == "2026-10-22"
    assert result["quote"]["kind"] == "intraday"
    assert result["quote"]["status"] == "available"
    assert result["quote"]["change_pct"] == 2.94


def test_old_intraday_observation_remains_visible_but_is_stale(clock):
    result = home._latest_index_quote([bar(clock.date(), 105, clock - timedelta(hours=1))])
    assert result["price"] == 105
    assert result["status"] == "stale"


def test_missing_previous_session_never_invents_a_daily_return(clock):
    result = home._latest_index_quote([bar(date(2026, 10, 20), 100, clock), bar(clock.date(), 105, clock)])
    assert result["change_pct"] is None
    assert result["status"] == "partial"


def test_future_provider_day_is_not_displayed(clock):
    result = home._latest_index_quote([bar(clock.date(), 105, clock), bar(clock.date() + timedelta(days=1), 999, clock)])
    assert result["price"] == 105


def test_after_close_intraday_value_is_never_labeled_confirmed(clock, monkeypatch):
    monkeypatch.setattr(home, "expected_us_market_session", lambda: SimpleNamespace(date=clock.date(), phase="closed"))
    result = home._latest_index_quote([bar(clock.date(), 105, clock)])
    assert result["kind"] == "unconfirmed_close"
    assert result["status"] == "stale"


def test_refetched_completed_day_is_current_without_intraday_age_limit(clock, monkeypatch):
    monkeypatch.setattr(home, "expected_us_market_session", lambda: SimpleNamespace(date=clock.date(), phase="closed"))
    monkeypatch.setattr(home, "daily_bar_is_final", lambda *a: True)
    result = home._latest_index_quote([bar(date(2026, 10, 21), 100, clock), bar(clock.date(), 105, clock - timedelta(hours=1))])
    assert result["kind"] == "close"
    assert result["status"] == "available"
