from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.db.models import CashFlow, ImportBatch, Instrument, IsinMapping, Position, PriceBar, Transaction
from app.db.session import SessionLocal
from app.domain.portfolio.trade_republic import TradeRepublicPosition, TradeRepublicTransactionRow
from app.schemas import PortfolioImportRow


@dataclass(frozen=True)
class PortfolioPositionRow:
    ticker: str
    name: str
    shares: float
    entry_price: float
    current_price: float
    currency: str
    buy_date: date | None
    pivot_tag: date | None = None
    stop_pct: float | None = None
    stop_price: float | None = None
    broker: str = ""
    account: str = ""
    note: str = ""
    current_price_source: str = ""


@dataclass(frozen=True)
class PortfolioPositionWrite:
    ticker: str
    name: str
    shares: float
    entry_price: float
    current_price: float | None
    currency: str
    buy_date: date | None
    pivot_tag: date | None
    stop_pct: float | None
    stop_price: float | None
    broker: str
    account: str
    note: str
    record_transaction: bool


@dataclass(frozen=True)
class PortfolioSellWrite:
    ticker: str
    shares: float
    price: float
    date: date
    currency: str
    fees: float
    tax: float
    note: str


@dataclass(frozen=True)
class PortfolioTransactionRow:
    id: str
    ticker: str
    date: date
    transaction_type: str
    shares: float
    price: float | None
    fees: float
    tax: float
    gross_amount: float | None
    net_amount: float | None
    currency: str
    broker: str
    external_id: str


@dataclass(frozen=True)
class PortfolioCashFlowWrite:
    date: date
    amount: float
    flow_type: str
    currency: str
    broker: str
    note: str


@dataclass(frozen=True)
class PortfolioCashFlowRow:
    id: str
    date: date
    amount: float
    flow_type: str
    currency: str
    broker: str
    note: str


@dataclass(frozen=True)
class PortfolioImportHistoryRow:
    id: str
    source: str
    file_name: str
    status: str
    rows_total: int
    rows_imported: int
    error_message: str
    created_at: datetime
    finished_at: datetime | None


@dataclass(frozen=True)
class TradeRepublicStoredTransactionRow:
    ticker: str
    date: date
    transaction_type: str
    shares: float
    price: float | None
    net_amount: float
    currency: str
    raw_json: dict
    isin: str = ""
    asset_class: str = ""
    name: str = ""


@dataclass(frozen=True)
class IsinMappingRow:
    isin: str
    ticker: str
    source: str


@dataclass(frozen=True)
class PortfolioImportResult:
    import_id: str
    rows_imported: int


@dataclass(frozen=True)
class TradeRepublicImportResult:
    import_id: str
    rows_imported: int
    transactions_imported: int


class PortfolioRepositoryUnavailable(RuntimeError):
    pass


def list_isin_mappings() -> dict[str, str]:
    try:
        with SessionLocal() as db:
            rows = db.scalars(select(IsinMapping).order_by(IsinMapping.isin.asc())).all()
            mappings: dict[str, str] = {}
            for row in rows:
                if row.isin and row.ticker:
                    mappings[row.isin.upper()] = row.ticker.upper()
            return mappings
    except SQLAlchemyError as exc:
        raise PortfolioRepositoryUnavailable(str(exc)) from exc


def list_isin_mapping_rows() -> list[IsinMappingRow]:
    try:
        with SessionLocal() as db:
            rows = db.scalars(select(IsinMapping).order_by(IsinMapping.isin.asc(), IsinMapping.source.asc())).all()
            return [
                IsinMappingRow(
                    isin=row.isin.upper(),
                    ticker=row.ticker.upper(),
                    source=row.source or "manual",
                )
                for row in rows
                if row.isin and row.ticker
            ]
    except SQLAlchemyError as exc:
        raise PortfolioRepositoryUnavailable(str(exc)) from exc


def upsert_isin_mappings(mappings: dict[str, str], *, source: str = "manual") -> list[IsinMappingRow]:
    try:
        with SessionLocal() as db:
            for isin, ticker in mappings.items():
                clean_isin = str(isin or "").upper().strip()
                clean_ticker = str(ticker or "").upper().strip()
                if not clean_isin or not clean_ticker:
                    continue
                instrument = _get_or_create_instrument(db, ticker=clean_ticker, name=clean_ticker, currency="EUR")
                row = db.scalars(
                    select(IsinMapping).where(
                        IsinMapping.isin == clean_isin,
                        IsinMapping.source == source,
                    )
                ).first()
                if row is None:
                    row = IsinMapping(
                        isin=clean_isin,
                        ticker=clean_ticker,
                        instrument_id=instrument.id,
                        source=source,
                        confidence=1.0,
                        metadata_json={},
                    )
                    db.add(row)
                else:
                    row.ticker = clean_ticker
                    row.instrument_id = instrument.id
                    row.confidence = 1.0
            db.commit()
            return list_isin_mapping_rows()
    except SQLAlchemyError as exc:
        raise PortfolioRepositoryUnavailable(str(exc)) from exc


def list_open_positions() -> list[PortfolioPositionRow]:
    try:
        with SessionLocal() as db:
            positions = db.scalars(
                select(Position).where(Position.is_open.is_(True)).order_by(Position.ticker.asc())
            ).all()
            rows: list[PortfolioPositionRow] = []
            for position in positions:
                instrument = None
                if position.instrument_id:
                    instrument = db.get(Instrument, position.instrument_id)
                if instrument is None:
                    instrument = db.scalars(select(Instrument).where(Instrument.ticker == position.ticker)).first()

                latest_price = None
                if instrument is not None:
                    latest_price = db.scalars(
                        select(PriceBar.close)
                        .where(PriceBar.instrument_id == instrument.id, PriceBar.close.is_not(None))
                        .order_by(PriceBar.date.desc())
                        .limit(1)
                    ).first()
                current_price_source = "price_cache" if latest_price is not None else "position_entry"

                rows.append(
                    PortfolioPositionRow(
                        ticker=position.ticker,
                        name=(instrument.name if instrument and instrument.name else position.ticker),
                        shares=float(position.shares),
                        entry_price=float(position.buy_price),
                        current_price=float(latest_price or position.buy_price),
                        currency=position.currency or "EUR",
                        buy_date=position.buy_date,
                        pivot_tag=position.pivot_tag,
                        stop_pct=position.stop_pct,
                        stop_price=_position_stop_price(position),
                        broker=position.broker or "",
                        account=position.account or "",
                        note=position.note or "",
                        current_price_source=current_price_source,
                    )
                )
            return rows
    except SQLAlchemyError as exc:
        raise PortfolioRepositoryUnavailable(str(exc)) from exc


def upsert_position(write: PortfolioPositionWrite) -> PortfolioPositionRow:
    clean = write.ticker.strip().upper()
    if not clean:
        raise PortfolioRepositoryUnavailable("Ticker must not be empty")

    try:
        with SessionLocal() as db:
            instrument = _get_or_create_instrument(
                db,
                ticker=clean,
                name=write.name or clean,
                currency=write.currency,
            )
            position = db.scalars(
                select(Position).where(Position.ticker == clean, Position.is_open.is_(True)).limit(1)
            ).first()
            previous_shares = float(position.shares) if position is not None else 0.0
            if position is None:
                position = Position(
                    instrument_id=instrument.id,
                    ticker=clean,
                    shares=write.shares,
                    buy_price=write.entry_price,
                    buy_date=write.buy_date,
                    pivot_tag=write.pivot_tag,
                    stop_pct=write.stop_pct,
                    stop_price=write.stop_price,
                    currency=write.currency,
                    broker=write.broker,
                    account=write.account,
                    note=write.note,
                )
                db.add(position)
                db.flush()
            else:
                position.instrument_id = instrument.id
                position.shares = write.shares
                position.buy_price = write.entry_price
                position.buy_date = write.buy_date
                position.pivot_tag = write.pivot_tag
                position.stop_pct = write.stop_pct
                if write.stop_price is not None:
                    position.stop_price = write.stop_price
                position.currency = write.currency
                position.broker = write.broker
                position.account = write.account
                position.note = write.note

            if write.current_price is not None and write.current_price > 0:
                _upsert_import_price_bar(db, instrument.id, write.current_price)

            delta_shares = max(float(write.shares) - previous_shares, 0.0)
            if write.record_transaction and delta_shares > 0:
                _add_transaction(
                    db,
                    position=position,
                    instrument=instrument,
                    transaction_type="buy",
                    transaction_date=write.buy_date or date.today(),
                    shares=delta_shares,
                    price=write.entry_price,
                    fees=0.0,
                    tax=0.0,
                    currency=write.currency,
                    note=write.note,
                )

            db.commit()
            return _position_to_row(db, position)
    except SQLAlchemyError as exc:
        raise PortfolioRepositoryUnavailable(str(exc)) from exc


def update_position_stop_price(ticker: str, stop_price: float | None) -> PortfolioPositionRow:
    clean = ticker.strip().upper()
    if not clean:
        raise PortfolioRepositoryUnavailable("Ticker must not be empty")
    try:
        with SessionLocal() as db:
            position = db.scalars(
                select(Position).where(Position.ticker == clean, Position.is_open.is_(True)).limit(1)
            ).first()
            if position is None:
                raise PortfolioRepositoryUnavailable(f"Offene Position {clean} wurde nicht gefunden.")
            position.stop_price = stop_price
            db.commit()
            return _position_to_row(db, position)
    except SQLAlchemyError as exc:
        raise PortfolioRepositoryUnavailable(str(exc)) from exc


def close_position(ticker: str) -> bool:
    clean = ticker.strip().upper()
    try:
        with SessionLocal() as db:
            position = db.scalars(
                select(Position).where(Position.ticker == clean, Position.is_open.is_(True)).limit(1)
            ).first()
            if position is None:
                return False
            position.is_open = False
            position.closed_at = datetime.now(UTC)
            db.commit()
            return True
    except SQLAlchemyError as exc:
        raise PortfolioRepositoryUnavailable(str(exc)) from exc


def sell_position(write: PortfolioSellWrite) -> tuple[PortfolioPositionRow | None, PortfolioTransactionRow]:
    clean = write.ticker.strip().upper()
    try:
        with SessionLocal() as db:
            position = db.scalars(
                select(Position).where(Position.ticker == clean, Position.is_open.is_(True)).limit(1)
            ).first()
            if position is None:
                raise PortfolioRepositoryUnavailable(f"Offene Position {clean} nicht gefunden")
            if write.shares > float(position.shares):
                raise PortfolioRepositoryUnavailable("Verkaufsmenge ist größer als die offene Position")

            instrument = db.get(Instrument, position.instrument_id) if position.instrument_id else None
            if instrument is None:
                instrument = _get_or_create_instrument(
                    db,
                    ticker=clean,
                    name=clean,
                    currency=write.currency,
                )
                position.instrument_id = instrument.id

            transaction = _add_transaction(
                db,
                position=position,
                instrument=instrument,
                transaction_type="sell",
                transaction_date=write.date,
                shares=write.shares,
                price=write.price,
                fees=write.fees,
                tax=write.tax,
                currency=write.currency,
                note=write.note,
            )
            remaining = max(float(position.shares) - write.shares, 0.0)
            if remaining <= 1e-9:
                position.shares = 0
                position.is_open = False
                position.closed_at = datetime.now(UTC)
                remaining_row = None
            else:
                position.shares = remaining
                remaining_row = None
            db.flush()
            if position.is_open:
                remaining_row = _position_to_row(db, position)
            transaction_row = _transaction_to_row(transaction)
            db.commit()
            return remaining_row, transaction_row
    except SQLAlchemyError as exc:
        raise PortfolioRepositoryUnavailable(str(exc)) from exc


def list_transactions(*, limit: int = 250) -> list[PortfolioTransactionRow]:
    try:
        with SessionLocal() as db:
            rows = db.scalars(
                select(Transaction)
                .order_by(Transaction.date.desc(), Transaction.created_at.desc())
                .limit(max(1, min(1000, limit)))
            ).all()
            return [_transaction_to_row(row) for row in rows]
    except SQLAlchemyError as exc:
        raise PortfolioRepositoryUnavailable(str(exc)) from exc


def list_trade_republic_transactions() -> list[TradeRepublicStoredTransactionRow]:
    try:
        with SessionLocal() as db:
            rows = db.scalars(
                select(Transaction)
                .where(Transaction.raw_json["source"].as_string() == "trade_republic_transactions")
                .order_by(Transaction.date.asc(), Transaction.created_at.asc())
            ).all()
            return [
                TradeRepublicStoredTransactionRow(
                    ticker=row.ticker or "",
                    date=row.date,
                    transaction_type=row.transaction_type or "",
                    shares=float(row.shares or 0.0),
                    price=float(row.price) if row.price is not None else None,
                    net_amount=float(row.net_amount or 0.0),
                    currency=row.currency or "EUR",
                    raw_json=dict(row.raw_json or {}),
                    isin=str((row.raw_json or {}).get("isin") or "").upper().strip(),
                    asset_class=str((row.raw_json or {}).get("asset_class") or "").upper().strip(),
                    name=str((row.raw_json or {}).get("name") or ""),
                )
                for row in rows
            ]
    except SQLAlchemyError as exc:
        raise PortfolioRepositoryUnavailable(str(exc)) from exc


def add_cash_flow(write: PortfolioCashFlowWrite) -> PortfolioCashFlowRow:
    try:
        with SessionLocal() as db:
            row = CashFlow(
                date=write.date,
                amount=write.amount,
                flow_type=write.flow_type,
                currency=write.currency,
                broker=write.broker,
                note=write.note,
            )
            db.add(row)
            db.commit()
            db.refresh(row)
            return _cash_flow_to_row(row)
    except SQLAlchemyError as exc:
        raise PortfolioRepositoryUnavailable(str(exc)) from exc


def list_cash_flows(*, limit: int = 250) -> list[PortfolioCashFlowRow]:
    try:
        with SessionLocal() as db:
            rows = db.scalars(
                select(CashFlow)
                .order_by(CashFlow.date.desc(), CashFlow.created_at.desc())
                .limit(max(1, min(1000, limit)))
            ).all()
            return [_cash_flow_to_row(row) for row in rows]
    except SQLAlchemyError as exc:
        raise PortfolioRepositoryUnavailable(str(exc)) from exc


def get_cash_balance() -> float:
    try:
        with SessionLocal() as db:
            cash_flows = db.scalars(select(CashFlow)).all()
            transactions = db.scalars(select(Transaction)).all()
            balance = 0.0
            for flow in cash_flows:
                amount = float(flow.amount or 0)
                if flow.flow_type == "withdrawal":
                    balance -= amount
                else:
                    balance += amount
            for tx in transactions:
                net = float(tx.net_amount or 0)
                if (tx.raw_json or {}).get("source") == "trade_republic_transactions":
                    balance += net
                elif tx.transaction_type == "buy":
                    balance -= abs(net)
                elif tx.transaction_type == "sell":
                    balance += abs(net)
            return round(balance, 2)
    except SQLAlchemyError as exc:
        raise PortfolioRepositoryUnavailable(str(exc)) from exc


def list_import_history(*, limit: int = 100) -> list[PortfolioImportHistoryRow]:
    try:
        with SessionLocal() as db:
            rows = db.scalars(
                select(ImportBatch)
                .order_by(ImportBatch.created_at.desc())
                .limit(max(1, min(500, limit)))
            ).all()
            return [
                PortfolioImportHistoryRow(
                    id=row.id,
                    source=row.source,
                    file_name=row.file_name,
                    status=row.status,
                    rows_total=row.rows_total,
                    rows_imported=row.rows_imported,
                    error_message=row.error_message or "",
                    created_at=row.created_at,
                    finished_at=row.finished_at,
                )
                for row in rows
            ]
    except SQLAlchemyError as exc:
        raise PortfolioRepositoryUnavailable(str(exc)) from exc


def upsert_imported_positions(
    rows: list[PortfolioImportRow],
    *,
    source: str,
    file_name: str,
    replace_open_positions: bool,
) -> PortfolioImportResult:
    if not rows:
        return PortfolioImportResult(import_id="", rows_imported=0)

    imported_tickers = {row.ticker.upper() for row in rows}
    try:
        with SessionLocal() as db:
            import_batch = ImportBatch(
                source=source,
                file_name=file_name,
                status="running",
                rows_total=len(rows),
                rows_imported=0,
                metadata_json={"replace_open_positions": replace_open_positions},
            )
            db.add(import_batch)
            db.flush()

            if replace_open_positions:
                stale_positions = db.scalars(
                    select(Position).where(
                        Position.is_open.is_(True),
                        Position.ticker.not_in(imported_tickers),
                    )
                ).all()
                for position in stale_positions:
                    position.is_open = False
                    position.closed_at = datetime.now(UTC)

            imported_count = 0
            for row in rows:
                ticker = row.ticker.upper()
                instrument = db.scalars(select(Instrument).where(Instrument.ticker == ticker)).first()
                if instrument is None:
                    instrument = Instrument(
                        ticker=ticker,
                        yahoo_symbol=ticker,
                        name=row.name or ticker,
                        currency=row.currency,
                    )
                    db.add(instrument)
                    db.flush()
                else:
                    instrument.name = row.name or instrument.name or ticker
                    instrument.currency = row.currency or instrument.currency

                position = db.scalars(
                    select(Position).where(Position.ticker == ticker, Position.is_open.is_(True)).limit(1)
                ).first()
                if position is None:
                    position = Position(
                        instrument_id=instrument.id,
                        ticker=ticker,
                        shares=row.shares,
                        buy_price=row.entry_price,
                        buy_date=_parse_date(row.buy_date),
                        currency=row.currency,
                        broker=row.broker,
                        account=row.account,
                        note=row.note,
                    )
                    db.add(position)
                else:
                    position.instrument_id = instrument.id
                    position.shares = row.shares
                    position.buy_price = row.entry_price
                    position.buy_date = _parse_date(row.buy_date)
                    position.currency = row.currency
                    position.broker = row.broker
                    position.account = row.account
                    position.note = row.note
                if row.current_price is not None and row.current_price > 0:
                    _upsert_import_price_bar(db, instrument.id, row.current_price)
                imported_count += 1

            import_batch.status = "done"
            import_batch.rows_imported = imported_count
            import_batch.finished_at = datetime.now(UTC)
            db.commit()
            return PortfolioImportResult(import_id=import_batch.id, rows_imported=imported_count)
    except SQLAlchemyError as exc:
        raise PortfolioRepositoryUnavailable(str(exc)) from exc


def import_trade_republic_transactions(
    *,
    transactions: list[TradeRepublicTransactionRow],
    positions: list[TradeRepublicPosition],
    mappings: dict[str, str],
    file_name: str,
    replace_open_positions: bool,
) -> TradeRepublicImportResult:
    try:
        with SessionLocal() as db:
            import_batch = ImportBatch(
                source="trade_republic_transactions",
                file_name=file_name,
                status="running",
                rows_total=len(transactions),
                rows_imported=0,
                metadata_json={"replace_open_positions": replace_open_positions},
            )
            db.add(import_batch)
            db.flush()

            for isin, ticker in mappings.items():
                clean_isin = str(isin or "").upper().strip()
                clean_ticker = str(ticker or "").upper().strip()
                if not clean_isin or not clean_ticker:
                    continue
                instrument = _get_or_create_instrument(db, ticker=clean_ticker, name=clean_ticker, currency="EUR")
                row = db.scalars(
                    select(IsinMapping).where(
                        IsinMapping.isin == clean_isin,
                        IsinMapping.source == "trade_republic",
                    )
                ).first()
                if row is None:
                    row = IsinMapping(
                        isin=clean_isin,
                        ticker=clean_ticker,
                        instrument_id=instrument.id,
                        source="trade_republic",
                        confidence=1.0,
                        metadata_json={},
                    )
                    db.add(row)
                else:
                    row.ticker = clean_ticker
                    row.instrument_id = instrument.id
                    row.confidence = 1.0

            if replace_open_positions:
                for position in db.scalars(select(Position).where(Position.is_open.is_(True))).all():
                    position.is_open = False
                    position.closed_at = datetime.now(UTC)

            positions_by_isin = {item.isin: item for item in positions}
            position_by_ticker: dict[str, Position] = {}
            imported_positions = 0
            for item in positions:
                instrument = _get_or_create_instrument(
                    db,
                    ticker=item.ticker,
                    name=item.name or item.ticker,
                    currency=item.currency or "EUR",
                )
                position = db.scalars(
                    select(Position).where(Position.ticker == item.ticker, Position.is_open.is_(True)).limit(1)
                ).first()
                if position is None:
                    position = Position(
                        instrument_id=instrument.id,
                        ticker=item.ticker,
                        shares=item.shares,
                        buy_price=item.avg_buy_price,
                        buy_date=_parse_date(item.first_buy_date),
                        currency=item.currency or "EUR",
                        broker="Trade Republic",
                        account="Trade Republic",
                        note=f"TR-Transaktionsimport / ISIN {item.isin}",
                    )
                    db.add(position)
                    db.flush()
                else:
                    position.instrument_id = instrument.id
                    position.shares = item.shares
                    position.buy_price = item.avg_buy_price
                    position.buy_date = _parse_date(item.first_buy_date)
                    position.currency = item.currency or position.currency
                    position.broker = "Trade Republic"
                    position.account = "Trade Republic"
                    position.note = f"TR-Transaktionsimport / ISIN {item.isin}"
                position_by_ticker[item.ticker] = position
                imported_positions += 1

            existing_external_ids = {
                item
                for item in db.scalars(
                    select(Transaction.external_id).where(
                        Transaction.external_id.in_([row.external_id for row in transactions])
                    )
                ).all()
                if item
            }
            transactions_imported = 0
            for row in transactions:
                ticker = mappings.get(row.isin, "") if row.isin else ""
                position = position_by_ticker.get(ticker)
                instrument = None
                if ticker:
                    name = positions_by_isin.get(row.isin).name if row.isin in positions_by_isin else row.name or ticker
                    instrument = _get_or_create_instrument(db, ticker=ticker, name=name, currency=row.currency or "EUR")
                existing = None
                if row.external_id in existing_external_ids:
                    existing = db.scalars(
                        select(Transaction).where(Transaction.external_id == row.external_id).limit(1)
                    ).first()
                target = existing or Transaction()
                target.position_id = position.id if position is not None else None
                target.instrument_id = instrument.id if instrument is not None else None
                target.ticker = ticker
                target.date = row.date.date()
                target.transaction_type = row.transaction_type.lower()
                target.shares = abs(float(row.shares or 0.0))
                target.price = float(row.price or 0.0) if row.price else None
                target.fees = float(row.fee or 0.0)
                target.tax = float(row.tax or 0.0)
                target.gross_amount = float(row.amount or 0.0)
                target.net_amount = float(row.cash_delta)
                target.currency = row.currency or "EUR"
                target.broker = "Trade Republic"
                target.external_id = row.external_id
                target.import_id = import_batch.id
                target.raw_json = {
                    **row.raw,
                    "source": "trade_republic_transactions",
                    "isin": row.isin,
                    "cash_delta": row.cash_delta,
                }
                if existing is None:
                    db.add(target)
                    transactions_imported += 1

            import_batch.status = "done"
            import_batch.rows_imported = imported_positions
            import_batch.finished_at = datetime.now(UTC)
            db.commit()
            return TradeRepublicImportResult(
                import_id=import_batch.id,
                rows_imported=imported_positions,
                transactions_imported=transactions_imported,
            )
    except SQLAlchemyError as exc:
        raise PortfolioRepositoryUnavailable(str(exc)) from exc


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    return None


def _get_or_create_instrument(db, *, ticker: str, name: str, currency: str) -> Instrument:
    instrument = db.scalars(select(Instrument).where(Instrument.ticker == ticker)).first()
    if instrument is None:
        instrument = Instrument(
            ticker=ticker,
            yahoo_symbol=ticker,
            name=name or ticker,
            currency=currency or "EUR",
        )
        db.add(instrument)
        db.flush()
    else:
        instrument.name = name or instrument.name or ticker
        instrument.currency = currency or instrument.currency
    return instrument


def _position_to_row(db, position: Position) -> PortfolioPositionRow:
    instrument = db.get(Instrument, position.instrument_id) if position.instrument_id else None
    latest_price = None
    if instrument is not None:
        latest_price = db.scalars(
            select(PriceBar.close)
            .where(PriceBar.instrument_id == instrument.id, PriceBar.close.is_not(None))
            .order_by(PriceBar.date.desc())
            .limit(1)
        ).first()
    current_price_source = "price_cache" if latest_price is not None else "position_entry"
    return PortfolioPositionRow(
        ticker=position.ticker,
        name=(instrument.name if instrument and instrument.name else position.ticker),
        shares=float(position.shares),
        entry_price=float(position.buy_price),
        current_price=float(latest_price or position.buy_price),
        currency=position.currency or "EUR",
        buy_date=position.buy_date,
        pivot_tag=position.pivot_tag,
        stop_pct=position.stop_pct,
        stop_price=_position_stop_price(position),
        broker=position.broker or "",
        account=position.account or "",
        note=position.note or "",
        current_price_source=current_price_source,
    )


def _position_stop_price(position: Position) -> float | None:
    if position.stop_price is not None:
        return float(position.stop_price)
    if position.stop_pct is None or position.buy_price is None:
        return None
    return float(position.buy_price) * (1 - float(position.stop_pct) / 100)


def _add_transaction(
    db,
    *,
    position: Position,
    instrument: Instrument,
    transaction_type: str,
    transaction_date: date,
    shares: float,
    price: float,
    fees: float,
    tax: float,
    currency: str,
    note: str,
) -> Transaction:
    gross = float(shares) * float(price)
    if transaction_type == "buy":
        net = gross + float(fees or 0) + float(tax or 0)
    elif transaction_type == "sell":
        net = gross - float(fees or 0) - float(tax or 0)
    else:
        net = gross
    transaction = Transaction(
        position_id=position.id,
        instrument_id=instrument.id,
        ticker=position.ticker,
        date=transaction_date,
        transaction_type=transaction_type,
        shares=float(shares),
        price=float(price),
        fees=float(fees or 0),
        tax=float(tax or 0),
        gross_amount=gross,
        net_amount=net,
        currency=currency,
        broker=position.broker or "",
        raw_json={"note": note} if note else {},
    )
    db.add(transaction)
    db.flush()
    return transaction


def _transaction_to_row(row: Transaction) -> PortfolioTransactionRow:
    return PortfolioTransactionRow(
        id=row.id,
        ticker=row.ticker,
        date=row.date,
        transaction_type=row.transaction_type,
        shares=float(row.shares or 0),
        price=float(row.price) if row.price is not None else None,
        fees=float(row.fees or 0),
        tax=float(row.tax or 0),
        gross_amount=float(row.gross_amount) if row.gross_amount is not None else None,
        net_amount=float(row.net_amount) if row.net_amount is not None else None,
        currency=row.currency or "EUR",
        broker=row.broker or "",
        external_id=row.external_id or "",
    )


def _cash_flow_to_row(row: CashFlow) -> PortfolioCashFlowRow:
    return PortfolioCashFlowRow(
        id=row.id,
        date=row.date,
        amount=float(row.amount),
        flow_type=row.flow_type,
        currency=row.currency,
        broker=row.broker or "",
        note=row.note or "",
    )


def _upsert_import_price_bar(db, instrument_id: str, close: float) -> None:
    today = date.today()
    row = db.scalars(
        select(PriceBar).where(
            PriceBar.instrument_id == instrument_id,
            PriceBar.date == today,
            PriceBar.source == "portfolio_import",
        )
    ).first()
    if row is None:
        row = PriceBar(
            instrument_id=instrument_id,
            date=today,
            source="portfolio_import",
            open=close,
            high=close,
            low=close,
            close=close,
            adj_close=close,
            volume=None,
        )
        db.add(row)
    else:
        row.open = close
        row.high = close
        row.low = close
        row.close = close
        row.adj_close = close
