from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import and_, asc, desc, func, or_, select
from sqlalchemy.exc import SQLAlchemyError

from app.db.models import (
    BreadthDaily,
    DailyStockOpportunity,
    FundamentalSnapshot,
    Instrument,
    JournalContextVersion,
    MarketSnapshot,
    PriceBar,
    RsRating,
    TradeJournalEntry,
    TradeJournalNoteRevision,
    Transaction,
)
from app.db.session import SessionLocal


class TradeJournalRepositoryUnavailable(RuntimeError):
    pass


def list_entries(
    ticker: str | None = None,
    *,
    query: str | None = None,
    entry_type: str | None = None,
    status: str | None = None,
    source: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = 50,
    offset: int = 0,
    sort: str = "newest",
) -> tuple[list[TradeJournalEntry], int]:
    try:
        with SessionLocal() as db:
            filters = []
            if ticker:
                filters.append(TradeJournalEntry.ticker == ticker.upper())
            if query:
                pattern = f"%{query.strip()}%"
                filters.append(or_(
                    TradeJournalEntry.ticker.ilike(pattern),
                    Instrument.name.ilike(pattern),
                    Instrument.isin.ilike(pattern),
                ))
            if entry_type:
                filters.append(TradeJournalEntry.entry_type == entry_type)
            if status:
                filters.append(TradeJournalEntry.status == status)
            if source == "broker":
                filters.append(TradeJournalEntry.source_transaction_id.is_not(None))
            elif source == "manual":
                filters.append(TradeJournalEntry.source_transaction_id.is_(None))
            if date_from:
                filters.append(TradeJournalEntry.trade_date >= date_from)
            if date_to:
                filters.append(TradeJournalEntry.trade_date <= date_to)

            base = (
                select(TradeJournalEntry)
                .outerjoin(Transaction, Transaction.id == TradeJournalEntry.source_transaction_id)
                .outerjoin(
                    Instrument,
                    or_(
                        Instrument.id == Transaction.instrument_id,
                        and_(Transaction.instrument_id.is_(None), Instrument.ticker == TradeJournalEntry.ticker),
                    ),
                )
            )
            if filters:
                base = base.where(*filters)
            total = int(db.scalar(select(func.count()).select_from(base.subquery())) or 0)
            ordering = (
                (asc(TradeJournalEntry.trade_date), asc(TradeJournalEntry.created_at))
                if sort == "oldest"
                else (desc(TradeJournalEntry.trade_date), desc(TradeJournalEntry.created_at))
            )
            statement = base.order_by(*ordering).offset(max(0, offset)).limit(max(1, min(200, limit)))
            rows = list(db.scalars(statement).unique().all())
            return rows, total
    except SQLAlchemyError as exc:
        raise TradeJournalRepositoryUnavailable(str(exc)) from exc


def list_trade_entries(
    *, query: str | None = None, date_from: date | None = None, date_to: date | None = None
) -> list[TradeJournalEntry]:
    """Return all filtered executions for server-side trade aggregation."""
    rows, _ = list_entries(query=query, date_from=date_from, date_to=date_to, limit=200, offset=0)
    if len(rows) < 200:
        return rows
    result = rows
    offset = 200
    while True:
        batch, _ = list_entries(
            query=query, date_from=date_from, date_to=date_to, limit=200, offset=offset
        )
        result.extend(batch)
        if len(batch) < 200:
            return result
        offset += 200


def get_entry(entry_id: str) -> TradeJournalEntry | None:
    try:
        with SessionLocal() as db:
            return db.get(TradeJournalEntry, entry_id)
    except SQLAlchemyError as exc:
        raise TradeJournalRepositoryUnavailable(str(exc)) from exc


def related_entries(row: TradeJournalEntry) -> list[TradeJournalEntry]:
    if not row.trade_group_id:
        return [row]
    try:
        with SessionLocal() as db:
            return list(db.scalars(select(TradeJournalEntry).where(
                TradeJournalEntry.trade_group_id == row.trade_group_id,
                TradeJournalEntry.ticker == row.ticker,
            ).order_by(TradeJournalEntry.trade_date, TradeJournalEntry.created_at)).all())
    except SQLAlchemyError as exc:
        raise TradeJournalRepositoryUnavailable(str(exc)) from exc


def historical_price_bars(ticker: str, *, start_date: date, end_date: date) -> list[PriceBar]:
    """Read a bounded, deterministic daily history without fetching live quotes."""
    try:
        with SessionLocal() as db:
            return list(db.scalars(
                select(PriceBar).join(Instrument, Instrument.id == PriceBar.instrument_id)
                .where(Instrument.ticker == ticker, PriceBar.date >= start_date,
                       PriceBar.date <= end_date, PriceBar.close.is_not(None))
                .order_by(PriceBar.date, PriceBar.fetched_at.desc().nullslast(), PriceBar.source, PriceBar.id)
            ).all())
    except SQLAlchemyError as exc:
        raise TradeJournalRepositoryUnavailable(str(exc)) from exc


def execution_metadata(source_transaction_id: str | None, ticker: str) -> dict:
    try:
        with SessionLocal() as db:
            transaction = db.get(Transaction, source_transaction_id) if source_transaction_id else None
            instrument = None
            if transaction is not None and transaction.instrument_id:
                instrument = db.get(Instrument, transaction.instrument_id)
            if instrument is None:
                instrument = db.scalar(select(Instrument).where(Instrument.ticker == ticker).limit(1))
            raw = transaction.raw_json or {} if transaction is not None else {}
            return {
                "instrument_name": instrument.name if instrument else str(raw.get("name") or ""),
                "isin": instrument.isin if instrument else str(raw.get("isin") or raw.get("symbol") or ""),
                "execution_at": str(raw.get("event_ts") or raw.get("datetime") or "") or None,
                "fees": float(transaction.fees) if transaction is not None else None,
                "tax": float(transaction.tax) if transaction is not None else None,
                "gross_amount": transaction.gross_amount if transaction is not None else None,
                "net_amount": transaction.net_amount if transaction is not None else None,
            }
    except SQLAlchemyError as exc:
        raise TradeJournalRepositoryUnavailable(str(exc)) from exc


def latest_contexts(entry_id: str) -> dict[str, JournalContextVersion]:
    try:
        with SessionLocal() as db:
            rows = list(db.scalars(
                select(JournalContextVersion)
                .where(JournalContextVersion.journal_entry_id == entry_id)
                .order_by(desc(JournalContextVersion.generated_at))
            ).all())
            result: dict[str, JournalContextVersion] = {}
            for row in rows:
                result.setdefault(row.block_type, row)
            return result
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


def latest_closed_buy_entry(ticker: str) -> TradeJournalEntry | None:
    try:
        with SessionLocal() as db:
            statement = (
                select(TradeJournalEntry)
                .where(
                    TradeJournalEntry.ticker == ticker.upper(),
                    TradeJournalEntry.entry_type == "buy",
                    TradeJournalEntry.status == "closed",
                )
                .order_by(desc(TradeJournalEntry.trade_date), desc(TradeJournalEntry.created_at))
                .limit(1)
            )
            return db.scalars(statement).first()
    except SQLAlchemyError as exc:
        raise TradeJournalRepositoryUnavailable(str(exc)) from exc


def latest_sell_for_buy_entry(buy_entry_id: str) -> TradeJournalEntry | None:
    try:
        with SessionLocal() as db:
            statement = (
                select(TradeJournalEntry)
                .where(
                    TradeJournalEntry.entry_type == "sell",
                    TradeJournalEntry.linked_entry_id == buy_entry_id,
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


def update_notes(entry_id: str, values: dict) -> TradeJournalEntry | None:
    """Persist the note edit and its immutable revision in one transaction."""
    try:
        with SessionLocal() as db:
            entry = db.get(TradeJournalEntry, entry_id)
            if entry is None:
                return None
            revision = int(db.scalar(
                select(func.coalesce(func.max(TradeJournalNoteRevision.revision), 0)).where(
                    TradeJournalNoteRevision.journal_entry_id == entry_id
                )
            ) or 0) + 1
            for key, value in values.items():
                setattr(entry, key, value)
            entry.updated_at = datetime.now(UTC)
            db.add(TradeJournalNoteRevision(
                journal_entry_id=entry_id,
                revision=revision,
                content_json={
                    "basis_text": entry.basis_text or "",
                    "alternative_entry": bool(entry.alternative_entry),
                    "alternative_entry_text": entry.alternative_entry_text or "",
                    "primary_reasons": entry.primary_reasons or "",
                    "sell_reason": entry.sell_reason or "",
                    "questionnaire": entry.questionnaire_json or {},
                    "chart_images": entry.chart_images_json or {},
                },
            ))
            db.commit()
            db.refresh(entry)
            return entry
    except SQLAlchemyError as exc:
        raise TradeJournalRepositoryUnavailable(str(exc)) from exc


def close_entry(entry_id: str) -> TradeJournalEntry | None:
    entry = get_entry(entry_id)
    if entry is not None and entry.source_transaction_id:
        raise ValueError("Broker-Ausfuehrungen werden ausschliesslich aus dem Ledger geschlossen.")
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


def coverage_summary() -> list[dict]:
    specs = [
        ("Kursdaten", PriceBar, PriceBar.date),
        ("RS-Ratings", RsRating, RsRating.date),
        ("Fundamentaldaten", FundamentalSnapshot, FundamentalSnapshot.as_of),
        ("Markt-Snapshots", MarketSnapshot, MarketSnapshot.date),
        ("Marktbreite", BreadthDaily, BreadthDaily.date),
        ("Tagesbewertungen", DailyStockOpportunity, DailyStockOpportunity.as_of),
    ]
    try:
        with SessionLocal() as db:
            result = []
            for name, model, date_column in specs:
                minimum, maximum, rows = db.execute(
                    select(func.min(date_column), func.max(date_column), func.count()).select_from(model)
                ).one()
                result.append({
                    "name": name,
                    "minimum": minimum.isoformat() if minimum else None,
                    "maximum": maximum.isoformat() if maximum else None,
                    "rows": int(rows or 0),
                    "status": "available" if rows else "missing",
                })
            return result
    except SQLAlchemyError as exc:
        raise TradeJournalRepositoryUnavailable(str(exc)) from exc
