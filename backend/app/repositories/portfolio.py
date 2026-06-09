from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.db.models import ImportBatch, Instrument, Position, PriceBar
from app.db.session import SessionLocal
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
    broker: str
    account: str


@dataclass(frozen=True)
class PortfolioImportResult:
    import_id: str
    rows_imported: int


class PortfolioRepositoryUnavailable(RuntimeError):
    pass


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

                rows.append(
                    PortfolioPositionRow(
                        ticker=position.ticker,
                        name=(instrument.name if instrument and instrument.name else position.ticker),
                        shares=float(position.shares),
                        entry_price=float(position.buy_price),
                        current_price=float(latest_price or position.buy_price),
                        currency=position.currency or "EUR",
                        buy_date=position.buy_date,
                        broker=position.broker or "",
                        account=position.account or "",
                    )
                )
            return rows
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


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    return None


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
