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
