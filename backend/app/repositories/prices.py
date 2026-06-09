from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.db.models import Instrument, PriceBar
from app.db.session import SessionLocal


@dataclass(frozen=True)
class PriceBarWrite:
    date: date
    open: float | None
    high: float | None
    low: float | None
    close: float
    adj_close: float | None
    volume: float | None


class PriceRepositoryUnavailable(RuntimeError):
    pass


def list_price_bars(ticker: str, *, start_date: date | None = None) -> list[PriceBar]:
    clean = ticker.strip().upper()
    try:
        with SessionLocal() as db:
            instrument = db.scalars(select(Instrument).where(Instrument.ticker == clean)).first()
            if instrument is None:
                return []

            query = select(PriceBar).where(PriceBar.instrument_id == instrument.id)
            if start_date is not None:
                query = query.where(PriceBar.date >= start_date)
            rows = db.scalars(query.order_by(PriceBar.date.asc())).all()
            return list(rows)
    except SQLAlchemyError as exc:
        raise PriceRepositoryUnavailable(str(exc)) from exc


def upsert_price_bars(
    ticker: str,
    bars: Iterable[PriceBarWrite],
    *,
    source: str = "yfinance",
    yahoo_symbol: str | None = None,
) -> int:
    clean = ticker.strip().upper()
    incoming = list(bars)
    if not clean or not incoming:
        return 0

    try:
        with SessionLocal() as db:
            instrument = db.scalars(select(Instrument).where(Instrument.ticker == clean)).first()
            if instrument is None:
                instrument = Instrument(
                    ticker=clean,
                    yahoo_symbol=yahoo_symbol or clean,
                    name=clean,
                    currency="USD",
                )
                db.add(instrument)
                db.flush()

            existing_rows = db.scalars(
                select(PriceBar).where(
                    PriceBar.instrument_id == instrument.id,
                    PriceBar.source == source,
                    PriceBar.date.in_([bar.date for bar in incoming]),
                )
            ).all()
            existing = {row.date: row for row in existing_rows}
            written = 0

            for bar in incoming:
                row = existing.get(bar.date)
                if row is None:
                    row = PriceBar(
                        instrument_id=instrument.id,
                        date=bar.date,
                        source=source,
                        open=bar.open,
                        high=bar.high,
                        low=bar.low,
                        close=bar.close,
                        adj_close=bar.adj_close,
                        volume=bar.volume,
                    )
                    db.add(row)
                else:
                    row.open = bar.open
                    row.high = bar.high
                    row.low = bar.low
                    row.close = bar.close
                    row.adj_close = bar.adj_close
                    row.volume = bar.volume
                written += 1

            db.commit()
            return written
    except SQLAlchemyError as exc:
        raise PriceRepositoryUnavailable(str(exc)) from exc
