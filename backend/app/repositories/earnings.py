from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy import delete, func, select
from sqlalchemy.exc import SQLAlchemyError

from app.db.models import EarningsEvent
from app.db.session import SessionLocal
from app.data_sources.source_priority import source_rank


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


def next_earnings_dates(tickers: list[str]) -> dict[str, date]:
    if not tickers:
        return {}
    try:
        with SessionLocal() as db:
            rows = db.execute(
                select(EarningsEvent.ticker, EarningsEvent.event_date, EarningsEvent.source)
                .where(EarningsEvent.ticker.in_(tickers), EarningsEvent.event_date >= date.today())
            ).all()
            result = {}
            for ticker, event_date, source in sorted(rows, key=lambda row: (
                source_rank("earnings_date", row[2]), row[1])):
                result.setdefault(ticker, event_date)
            return result
    except SQLAlchemyError as exc:
        raise EarningsRepositoryUnavailable(str(exc)) from exc


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
    replace_sources: tuple[str, ...] | None = None,
) -> int:
    deduplicated = {
        (item.ticker.strip().upper(), item.event_date, item.source): item
        for item in rows
        if item.ticker.strip()
    }
    try:
        with SessionLocal() as db:
            sources = replace_sources or (source,)
            db.execute(
                delete(EarningsEvent).where(
                    EarningsEvent.source.in_(sources),
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
    event = next_earnings_event(ticker, from_date=from_date)
    return event[0] if event else None


def next_earnings_event(ticker: str, *, from_date: date | None = None,
                        include_fmp: bool = True) -> tuple[date, str] | None:
    clean = ticker.strip().upper()
    if not clean:
        return None
    try:
        with SessionLocal() as db:
            rows = db.execute(
                select(EarningsEvent.event_date, EarningsEvent.source).where(
                    EarningsEvent.ticker == clean,
                    EarningsEvent.event_date >= (from_date or date.today()),
                )
            ).all()
            if not include_fmp:
                rows = [row for row in rows if row[1] != "fmp"]
            best = min(rows, key=lambda row: (source_rank("earnings_date", row[1]), row[0])) if rows else None
            return (best[0], best[1]) if best else None
    except SQLAlchemyError as exc:
        raise EarningsRepositoryUnavailable(str(exc)) from exc


def latest_calendar_fetch() -> datetime | None:
    try:
        with SessionLocal() as db:
            return db.scalar(select(func.max(EarningsEvent.fetched_at)))
    except SQLAlchemyError as exc:
        raise EarningsRepositoryUnavailable(str(exc)) from exc
