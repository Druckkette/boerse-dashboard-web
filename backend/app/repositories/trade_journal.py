from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import desc, select
from sqlalchemy.exc import SQLAlchemyError

from app.db.models import TradeJournalEntry
from app.db.session import SessionLocal


class TradeJournalRepositoryUnavailable(RuntimeError):
    pass


def list_entries(ticker: str | None = None, *, limit: int = 250) -> list[TradeJournalEntry]:
    try:
        with SessionLocal() as db:
            statement = select(TradeJournalEntry).order_by(
                desc(TradeJournalEntry.trade_date),
                desc(TradeJournalEntry.created_at),
            )
            if ticker:
                statement = statement.where(TradeJournalEntry.ticker == ticker.upper())
            return list(db.scalars(statement.limit(max(1, min(1000, limit)))).all())
    except SQLAlchemyError as exc:
        raise TradeJournalRepositoryUnavailable(str(exc)) from exc


def get_entry(entry_id: str) -> TradeJournalEntry | None:
    try:
        with SessionLocal() as db:
            return db.get(TradeJournalEntry, entry_id)
    except SQLAlchemyError as exc:
        raise TradeJournalRepositoryUnavailable(str(exc)) from exc


def latest_open_buy_entry(ticker: str) -> TradeJournalEntry | None:
    try:
        with SessionLocal() as db:
            statement = (
                select(TradeJournalEntry)
                .where(
                    TradeJournalEntry.ticker == ticker.upper(),
                    TradeJournalEntry.entry_type == "buy",
                    TradeJournalEntry.status == "open",
                )
                .order_by(desc(TradeJournalEntry.trade_date), desc(TradeJournalEntry.created_at))
                .limit(1)
            )
            return db.scalars(statement).first()
    except SQLAlchemyError as exc:
        raise TradeJournalRepositoryUnavailable(str(exc)) from exc


def create_entry(values: dict) -> TradeJournalEntry:
    try:
        with SessionLocal() as db:
            entry = TradeJournalEntry(**values)
            db.add(entry)
            db.commit()
            db.refresh(entry)
            return entry
    except SQLAlchemyError as exc:
        raise TradeJournalRepositoryUnavailable(str(exc)) from exc


def update_entry(entry_id: str, values: dict) -> TradeJournalEntry | None:
    try:
        with SessionLocal() as db:
            entry = db.get(TradeJournalEntry, entry_id)
            if entry is None:
                return None
            for key, value in values.items():
                setattr(entry, key, value)
            entry.updated_at = datetime.now(UTC)
            db.commit()
            db.refresh(entry)
            return entry
    except SQLAlchemyError as exc:
        raise TradeJournalRepositoryUnavailable(str(exc)) from exc


def close_entry(entry_id: str) -> TradeJournalEntry | None:
    return update_entry(entry_id, {"status": "closed"})


def close_related_entries(entry_ids: list[str]) -> None:
    clean_ids = [entry_id for entry_id in entry_ids if entry_id]
    if not clean_ids:
        return
    try:
        with SessionLocal() as db:
            entries = list(db.scalars(select(TradeJournalEntry).where(TradeJournalEntry.id.in_(clean_ids))).all())
            for entry in entries:
                entry.status = "closed"
                entry.updated_at = datetime.now(UTC)
            db.commit()
    except SQLAlchemyError as exc:
        raise TradeJournalRepositoryUnavailable(str(exc)) from exc


def count_entries_since(start_date: date) -> int:
    try:
        with SessionLocal() as db:
            statement = select(TradeJournalEntry).where(TradeJournalEntry.trade_date >= start_date)
            return len(list(db.scalars(statement).all()))
    except SQLAlchemyError as exc:
        raise TradeJournalRepositoryUnavailable(str(exc)) from exc
