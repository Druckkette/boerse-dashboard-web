from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy import delete, func, select
from sqlalchemy.exc import SQLAlchemyError

from app.db.models import EarningsEvent
from app.db.session import SessionLocal


@dataclass(frozen=True)
class EarningsEventWrite:
    ticker: str
    event_date: date
    fiscal_date_ending: date | None = None
    time: str = ""
    eps_estimated: float | None = None
    eps_actual: float | None = None
    revenue_estimated: float | None = None
    revenue_actual: float | None = None
    source: str = "fmp"
    raw_json: dict | None = None


class EarningsRepositoryUnavailable(RuntimeError):
    pass


def upsert_earnings_events(rows: list[EarningsEventWrite]) -> int:
    if not rows:
        return 0
    try:
        with SessionLocal() as db:
            now = datetime.now(UTC)
            for item in rows:
                ticker = item.ticker.strip().upper()
                row = db.scalar(
                    select(EarningsEvent).where(
                        EarningsEvent.ticker == ticker,
                        EarningsEvent.event_date == item.event_date,
                        EarningsEvent.source == item.source,
                    )
                )
                if row is None:
                    row = EarningsEvent(
                        ticker=ticker,
                        event_date=item.event_date,
                        source=item.source,
                    )
                    db.add(row)
                row.fiscal_date_ending = item.fiscal_date_ending
                row.time = item.time
                row.eps_estimated = item.eps_estimated
                row.eps_actual = item.eps_actual
                row.revenue_estimated = item.revenue_estimated
                row.revenue_actual = item.revenue_actual
                row.raw_json = item.raw_json or {}
                row.fetched_at = now
            db.commit()
            return len(rows)
    except SQLAlchemyError as exc:
        raise EarningsRepositoryUnavailable(str(exc)) from exc


def replace_earnings_window(
    rows: list[EarningsEventWrite],
    *,
    start_date: date,
    end_date: date,
    source: str = "fmp",
) -> int:
    deduplicated = {
        (item.ticker.strip().upper(), item.event_date, item.source): item
        for item in rows
        if item.ticker.strip()
    }
    try:
        with SessionLocal() as db:
            db.execute(
                delete(EarningsEvent).where(
                    EarningsEvent.source == source,
                    EarningsEvent.event_date >= start_date,
                    EarningsEvent.event_date <= end_date,
                )
            )
            now = datetime.now(UTC)
            for (ticker, _, _), item in deduplicated.items():
                db.add(
                    EarningsEvent(
                        ticker=ticker,
                        event_date=item.event_date,
                        fiscal_date_ending=item.fiscal_date_ending,
                        time=item.time,
                        eps_estimated=item.eps_estimated,
                        eps_actual=item.eps_actual,
                        revenue_estimated=item.revenue_estimated,
                        revenue_actual=item.revenue_actual,
                        source=item.source,
                        raw_json=item.raw_json or {},
                        fetched_at=now,
                    )
                )
            db.commit()
            return len(deduplicated)
    except SQLAlchemyError as exc:
        raise EarningsRepositoryUnavailable(str(exc)) from exc


def priority_tickers_for_fundamentals(
    *,
    start_date: date,
    end_date: date,
    limit: int = 1000,
) -> list[str]:
    try:
        with SessionLocal() as db:
            return list(
                db.scalars(
                    select(EarningsEvent.ticker)
                    .where(
                        EarningsEvent.event_date >= start_date,
                        EarningsEvent.event_date <= end_date,
                    )
                    .order_by(EarningsEvent.event_date.asc(), EarningsEvent.ticker.asc())
                    .limit(max(1, min(limit, 10000)))
                ).all()
            )
    except SQLAlchemyError as exc:
        raise EarningsRepositoryUnavailable(str(exc)) from exc


def next_earnings_date(ticker: str, *, from_date: date | None = None) -> date | None:
    clean = ticker.strip().upper()
    if not clean:
        return None
    try:
        with SessionLocal() as db:
            return db.scalar(
                select(func.min(EarningsEvent.event_date)).where(
                    EarningsEvent.ticker == clean,
                    EarningsEvent.event_date >= (from_date or date.today()),
                )
            )
    except SQLAlchemyError as exc:
        raise EarningsRepositoryUnavailable(str(exc)) from exc


def latest_calendar_fetch() -> datetime | None:
    try:
        with SessionLocal() as db:
            return db.scalar(select(func.max(EarningsEvent.fetched_at)))
    except SQLAlchemyError as exc:
        raise EarningsRepositoryUnavailable(str(exc)) from exc
