from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from functools import lru_cache
from threading import RLock

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


# Yahoo exchange suffixes used by the cache. Unsuffixed US shares/ADRs and SPY
# use NYSE sessions; foreign listings use their own closing times and holidays.
_TICKER_CALENDARS = {"L": "XLON", "DE": "XETR", "F": "XFRA", "HK": "XHKG", "PA": "XPAR", "AS": "XAMS", "MI": "XMIL", "T": "XTKS", "TO": "XTSE", "AX": "XASX", "SW": "XSWX", "VI": "XWBO", "BR": "XBRU", "MC": "XMAD"}


def ticker_market_calendar_name(ticker: str) -> str:
    suffix = str(ticker or "").upper().rsplit(".", 1)[-1]
    return _TICKER_CALENDARS.get(suffix, "XNYS")


def _ticker_calendar(ticker: str):
    name = ticker_market_calendar_name(ticker)
    if name == "XNYS":
        return _xnys_calendar()
    with _calendar_lock:
        return _load_exchange_calendar(name)


@lru_cache(maxsize=16)
def _load_exchange_calendar(name: str):
    return xcals.get_calendar(name)


def common_market_sessions(ticker: str, benchmark: str, start: date, end: date) -> pd.DatetimeIndex:
    left = _ticker_calendar(ticker).sessions_in_range(pd.Timestamp(start), pd.Timestamp(end))
    right = _ticker_calendar(benchmark).sessions_in_range(pd.Timestamp(start), pd.Timestamp(end))
    return left.intersection(right)


def completed_ticker_market_session(ticker: str, now: datetime | None = None) -> ExpectedMarketSession:
    if ticker_market_calendar_name(ticker) == "XNYS":
        return completed_us_market_session() if now is None else completed_us_market_session(now)
    return completed_common_market_session(ticker, ticker, now)


def completed_common_market_session(ticker: str, benchmark: str, now: datetime | None = None) -> ExpectedMarketSession:
    if ticker_market_calendar_name(ticker) == ticker_market_calendar_name(benchmark) == "XNYS":
        return completed_us_market_session() if now is None else completed_us_market_session(now)
    current = _as_utc(now or datetime.now(UTC))
    left, right = _ticker_calendar(ticker), _ticker_calendar(benchmark)
    sessions = common_market_sessions(ticker, benchmark, (current - timedelta(days=14)).date(), current.date())
    for session in reversed(sessions):
        close_at = max(_as_utc(left.session_close(session).to_pydatetime()), _as_utc(right.session_close(session).to_pydatetime()))
        if close_at <= current:
            open_at = max(_as_utc(left.session_open(session).to_pydatetime()), _as_utc(right.session_open(session).to_pydatetime()))
            return ExpectedMarketSession(date=session.date(), phase="closed", open_at=open_at, close_at=close_at)
    raise ValueError(f"Keine gemeinsame abgeschlossene Börsensitzung für {ticker}/{benchmark}")


def last_ticker_market_session_of_week(day: date, ticker: str) -> date:
    monday = day - timedelta(days=day.weekday())
    sessions = _ticker_calendar(ticker).sessions_in_range(pd.Timestamp(monday), pd.Timestamp(monday + timedelta(days=4)))
    return sessions[-1].date() if len(sessions) else monday + timedelta(days=4)


def previous_ticker_market_session_date(ticker: str, day: date) -> date:
    if ticker_market_calendar_name(ticker) == "XNYS":
        return previous_us_market_session_date(day)
    sessions = _ticker_calendar(ticker).sessions_in_range(pd.Timestamp(day - timedelta(days=14)), pd.Timestamp(day - timedelta(days=1)))
    return sessions[-1].date()


def last_us_market_session_of_week(day: date) -> date:
    monday = day - timedelta(days=day.weekday())
    sessions = _xnys_calendar().sessions_in_range(pd.Timestamp(monday), pd.Timestamp(monday + timedelta(days=4)))
    return sessions[-1].date() if len(sessions) else monday + timedelta(days=4)


def completed_us_market_session(now: datetime | None = None) -> ExpectedMarketSession:
    current = expected_us_market_session(now)
    if current.phase != "intraday":
        return current
    return expected_us_market_session(current.open_at - timedelta(seconds=1))


def price_is_current(bar_date: date | None, fetched_at: datetime | None, *, now: datetime | None = None) -> bool:
    session = expected_us_market_session(now)
    if bar_date is None or bar_date != session.date or fetched_at is None:
        return False
    required_time = session.open_at if session.phase == "intraday" else session.close_at
    return required_time is not None and _as_utc(fetched_at) >= required_time


def daily_bar_is_final(bar_date: date, fetched_at: datetime | None, *, now: datetime | None = None, completed: ExpectedMarketSession | None = None, ticker: str = "") -> bool:
    completed = completed or completed_ticker_market_session(ticker, now)
    if bar_date > completed.date:
        return False
    if fetched_at is None:
        # Legacy history remains usable, but the newest session needs a verified fetch.
        return bar_date < completed.date
    if _as_utc(fetched_at).date() > bar_date:
        return True
    calendar = _ticker_calendar(ticker)
    session = pd.Timestamp(bar_date)
    if not calendar.is_session(session):
        return False
    return _as_utc(fetched_at) >= _as_utc(calendar.session_close(session).to_pydatetime())


_calendar_lock = RLock()


def _xnys_calendar():
    # functools caches results, but does not serialize concurrent cache misses.
    with _calendar_lock:
        return _load_xnys_calendar()


@lru_cache(maxsize=1)
def _load_xnys_calendar():
    return xcals.get_calendar("XNYS")


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
