from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import and_, asc, desc, func, or_, select, text
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
    include_metadata: bool = True,
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
                    Transaction.raw_json["name"].astext.ilike(pattern),
                    Transaction.raw_json["isin"].astext.ilike(pattern),
                ))
            if entry_type:
                filters.append(TradeJournalEntry.entry_type == entry_type)
            if status:
                filters.append(TradeJournalEntry.status == status)
            if source == "broker":
                filters.append(TradeJournalEntry.source_transaction_id.is_not(None))
            elif source in {"manual", "unlinked"}:
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
            _attach_summary_dependencies(db, rows, include_metadata=include_metadata)
            return rows, total
    except SQLAlchemyError as exc:
        raise TradeJournalRepositoryUnavailable(str(exc)) from exc


def _attach_summary_dependencies(db, rows, *, include_metadata=True):
    if not rows:
        return
    ids = [row.id for row in rows]
    contexts = db.scalars(select(JournalContextVersion).where(
        JournalContextVersion.journal_entry_id.in_(ids)
    ).distinct(JournalContextVersion.journal_entry_id, JournalContextVersion.block_type).order_by(
        JournalContextVersion.journal_entry_id, JournalContextVersion.block_type,
        JournalContextVersion.generated_at.desc(), JournalContextVersion.id.desc()
    )).all()
    by_entry = {}
    for context in contexts:
        by_entry.setdefault(context.journal_entry_id, {})[context.block_type] = context
    for row in rows:
        row._latest_contexts = by_entry.get(row.id, {})
    if not include_metadata:
        return
    linked_ids = {row.linked_entry_id for row in rows if row.linked_entry_id and not row.source_transaction_id}
    linked_buys = {row.id: row for row in db.scalars(select(TradeJournalEntry).where(TradeJournalEntry.id.in_(linked_ids))).all()} if linked_ids else {}
    for row in rows:
        row._linked_buy = linked_buys.get(row.linked_entry_id)
    tx_ids = [row.source_transaction_id for row in rows if row.source_transaction_id]
    transactions = {tx.id: tx for tx in db.scalars(select(Transaction).where(Transaction.id.in_(tx_ids))).all()} if tx_ids else {}
    tickers = {row.ticker for row in rows}
    instrument_ids = {tx.instrument_id for tx in transactions.values() if tx.instrument_id}
    instruments = list(db.scalars(select(Instrument).where(or_(Instrument.ticker.in_(tickers), Instrument.id.in_(instrument_ids)))).all())
    by_id = {item.id: item for item in instruments}
    by_ticker = {item.ticker: item for item in instruments}
    for row in rows:
        tx = transactions.get(row.source_transaction_id)
        instrument = (by_id.get(tx.instrument_id) if tx else None) or by_ticker.get(row.ticker)
        raw = tx.raw_json or {} if tx else {}
        row._execution_metadata = {
            "instrument_name": instrument.name if instrument else str(raw.get("name") or ""),
            "isin": instrument.isin if instrument else str(raw.get("isin") or raw.get("symbol") or ""),
            "execution_at": str(raw.get("event_ts") or raw.get("datetime") or "") or None,
            "fees": float(tx.fees) if tx else None, "tax": float(tx.tax) if tx else None,
            "gross_amount": tx.gross_amount if tx else None, "net_amount": tx.net_amount if tx else None,
        }


def list_trade_entries(
    *, query: str | None = None, date_from: date | None = None, date_to: date | None = None
) -> list[TradeJournalEntry]:
    """Return all filtered executions for server-side trade aggregation."""
    rows, _ = list_entries(query=query, date_from=date_from, date_to=date_to, limit=200, offset=0, include_metadata=False)
    if len(rows) < 200:
        return rows
    result = rows
    offset = 200
    while True:
        batch, _ = list_entries(
            query=query, date_from=date_from, date_to=date_to, limit=200, offset=offset, include_metadata=False
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
            _validate_manual_sale(db, values)
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
            if not entry.source_transaction_id and entry.entry_type == "buy":
                db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": f"journal-buy:{entry.id}"})
                db.refresh(entry)
                linked_sales = list(db.scalars(select(TradeJournalEntry).where(TradeJournalEntry.entry_type == "sell", TradeJournalEntry.linked_entry_id == entry.id)).all())
                if linked_sales and (float(values.get("shares", entry.shares) or 0) + 1e-8 < sum(float(sale.shares or 0) for sale in linked_sales) or values.get("ticker", entry.ticker) != entry.ticker or values.get("currency", entry.currency) != entry.currency or values.get("trade_date", entry.trade_date) > min(sale.trade_date for sale in linked_sales)):
                    raise ValueError("Kaufänderung widerspricht bereits dokumentierten Teilverkäufen.")
            if not entry.source_transaction_id:
                _validate_manual_sale(db, {"entry_type": entry.entry_type, "linked_entry_id": entry.linked_entry_id, **values}, exclude_id=entry_id)
            for key, value in values.items():
                setattr(entry, key, value)
            entry.updated_at = datetime.now(UTC)
            db.commit()
            db.refresh(entry)
            return entry
    except SQLAlchemyError as exc:
        raise TradeJournalRepositoryUnavailable(str(exc)) from exc


def _validate_manual_sale(db, values, *, exclude_id=None):
    if values.get("entry_type") != "sell" or not values.get("linked_entry_id"):
        return
    buy_id = values["linked_entry_id"]
    db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": f"journal-buy:{buy_id}"})
    buy = db.get(TradeJournalEntry, buy_id)
    if buy is None or buy.entry_type != "buy" or buy.ticker != values.get("ticker"):
        raise ValueError("Verknüpfter Kauf passt nicht zum Verkauf.")
    if buy.source_transaction_id:
        raise ValueError("Brokerkäufe über die importierten Ausführungen dokumentieren; keine manuellen Verkäufe daran anhängen.")
    if buy.currency != values.get("currency") or values.get("trade_date", buy.trade_date) < buy.trade_date:
        raise ValueError("Währung oder Datum des Verkaufs passt nicht zum Kauf.")
    used = db.scalar(select(func.coalesce(func.sum(TradeJournalEntry.shares), 0)).where(
        TradeJournalEntry.entry_type == "sell", TradeJournalEntry.linked_entry_id == buy_id,
        TradeJournalEntry.id != exclude_id if exclude_id else True,
    )) or 0
    if float(used) + float(values.get("shares") or 0) > float(buy.shares or 0) + 1e-8:
        raise ValueError("Die Teilverkäufe überschreiten die verknüpfte Kaufmenge.")


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
