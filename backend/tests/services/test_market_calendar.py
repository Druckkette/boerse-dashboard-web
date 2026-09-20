from __future__ import annotations

from datetime import UTC, date, datetime

from app.services.market_calendar import expected_us_market_session


def test_expected_session_is_current_while_nyse_is_open() -> None:
    result = expected_us_market_session(datetime(2026, 7, 31, 14, 0, tzinfo=UTC))

    assert result.date == date(2026, 7, 31)
    assert result.phase == "intraday"


def test_expected_session_is_latest_completed_on_weekend() -> None:
    result = expected_us_market_session(datetime(2026, 8, 1, 12, 0, tzinfo=UTC))

    assert result.date == date(2026, 7, 31)
    assert result.phase == "closed"


def test_concurrent_cold_requests_construct_calendar_once(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from time import sleep
    from app.services import market_calendar as calendar
    calendar._load_xnys_calendar.cache_clear()
    calls = []
    marker = object()
    def create(name):
        calls.append(name)
        sleep(.02)
        return marker
    monkeypatch.setattr(calendar.xcals, "get_calendar", create)
    barrier = Barrier(4)
    def get(_):
        barrier.wait()
        return calendar._xnys_calendar()
    try:
        with ThreadPoolExecutor(max_workers=4) as pool:
            assert list(pool.map(get, range(4))) == [marker] * 4
        assert calls == ["XNYS"]
    finally:
        calendar._load_xnys_calendar.cache_clear()


def test_api_warms_calendar_before_serving(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import create_app
    from app.services import market_calendar
    calls = []
    monkeypatch.setattr(market_calendar, "completed_us_market_session", lambda: calls.append("ready"))
    with TestClient(create_app()):
        assert calls == ["ready"]
