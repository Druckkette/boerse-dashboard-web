from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from functools import lru_cache

import exchange_calendars as xcals
import pandas as pd


@dataclass(frozen=True)
class ExpectedMarketSession:
    date: date
    phase: str
    open_at: datetime | None = None
    close_at: datetime | None = None


def expected_us_market_session(now: datetime | None = None) -> ExpectedMarketSession:
    """Return the newest NYSE session whose data should be available now.

    During an open session the current date is expected. Before the opening bell,
    on weekends and on exchange holidays the latest completed session is expected.
    """

    current = _as_utc(now or datetime.now(UTC))
    calendar = _xnys_calendar()
    start = pd.Timestamp((current - timedelta(days=14)).date())
    end = pd.Timestamp((current + timedelta(days=1)).date())
    sessions = calendar.sessions_in_range(start, end)
    latest_completed: ExpectedMarketSession | None = None

    for session in sessions:
        session_open = _as_utc(calendar.session_open(session).to_pydatetime())
        session_close = _as_utc(calendar.session_close(session).to_pydatetime())
        session_date = session.date()
        if session_open <= current < session_close:
            return ExpectedMarketSession(
                date=session_date,
                phase="intraday",
                open_at=session_open,
                close_at=session_close,
            )
        if session_close <= current:
            latest_completed = ExpectedMarketSession(
                date=session_date,
                phase="closed",
                open_at=session_open,
                close_at=session_close,
            )

    if latest_completed is not None:
        return latest_completed

    # The range above always contains a prior session in normal operation. Keep
    # a deterministic fallback so readiness endpoints never fail on calendar data.
    fallback = current.date()
    while fallback.weekday() >= 5:
        fallback -= timedelta(days=1)
    return ExpectedMarketSession(date=fallback, phase="fallback")


def previous_us_market_session_date(session_date: date) -> date:
    """Return the exchange session immediately before ``session_date``."""

    calendar = _xnys_calendar()
    session = pd.Timestamp(session_date)
    try:
        return calendar.previous_session(session).date()
    except (KeyError, ValueError):
        sessions = calendar.sessions_in_range(
            pd.Timestamp(session_date - timedelta(days=10)),
            pd.Timestamp(session_date - timedelta(days=1)),
        )
        if len(sessions):
            return sessions[-1].date()

    fallback = session_date - timedelta(days=1)
    while fallback.weekday() >= 5:
        fallback -= timedelta(days=1)
    return fallback


@lru_cache(maxsize=1)
def _xnys_calendar():
    return xcals.get_calendar("XNYS")


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
