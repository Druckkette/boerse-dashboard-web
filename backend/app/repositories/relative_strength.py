from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from app.db.models import Instrument, RsRating
from app.db.session import SessionLocal


@dataclass(frozen=True)
class RsRatingWrite:
    ticker: str
    date: date
    rating: int
    score: float
    percentile: float
    method: str
    source: str
    universe_size: int
    metadata_json: dict


@dataclass(frozen=True)
class RsRatingRow:
    ticker: str
    name: str
    date: date
    rating: int | None
    score: float | None
    percentile: float | None
    method: str
    source: str
    universe_size: int
    metadata_json: dict


class RelativeStrengthRepositoryUnavailable(RuntimeError):
    pass


def upsert_rs_ratings(rows: list[RsRatingWrite]) -> int:
    incoming = [row for row in rows if row.ticker.strip()]
    if not incoming:
        return 0

    try:
        with SessionLocal() as db:
            tickers = list(dict.fromkeys(row.ticker.strip().upper() for row in incoming))
            instruments = db.scalars(select(Instrument).where(Instrument.ticker.in_(tickers))).all()
            by_ticker = {instrument.ticker.upper(): instrument for instrument in instruments}

            for ticker in tickers:
                if ticker in by_ticker:
                    continue
                instrument = Instrument(ticker=ticker, yahoo_symbol=ticker, name=ticker, currency="USD")
                db.add(instrument)
                db.flush()
                by_ticker[ticker] = instrument

            written = 0
            for item in incoming:
                ticker = item.ticker.strip().upper()
                instrument = by_ticker[ticker]
                row = db.scalars(
                    select(RsRating).where(
                        RsRating.instrument_id == instrument.id,
                        RsRating.date == item.date,
                        RsRating.source == item.source,
                    )
                ).first()
                if row is None:
                    row = RsRating(
                        instrument_id=instrument.id,
                        date=item.date,
                        source=item.source,
                    )
                    db.add(row)
                row.rating = item.rating
                row.score = item.score
                row.percentile = item.percentile
                row.method = item.method
                row.universe_size = item.universe_size
                row.metadata_json = item.metadata_json
                written += 1

            db.commit()
            return written
    except SQLAlchemyError as exc:
        raise RelativeStrengthRepositoryUnavailable(str(exc)) from exc


def list_latest_rs_ratings(*, limit: int = 100, source: str | None = None) -> list[RsRatingRow]:
    try:
        with SessionLocal() as db:
            latest_query = select(func.max(RsRating.date))
            if source:
                latest_query = latest_query.where(RsRating.source == source)
            latest_date = db.scalar(latest_query)
            if latest_date is None:
                return []

            query = (
                select(RsRating, Instrument)
                .join(Instrument, Instrument.id == RsRating.instrument_id)
                .where(RsRating.date == latest_date)
            )
            if source:
                query = query.where(RsRating.source == source)
            rows = db.execute(
                query.order_by(RsRating.rating.desc().nullslast(), RsRating.score.desc().nullslast()).limit(
                    max(1, min(500, limit))
                )
            ).all()
            return [_row_to_dataclass(rating, instrument) for rating, instrument in rows]
    except SQLAlchemyError as exc:
        raise RelativeStrengthRepositoryUnavailable(str(exc)) from exc


def count_latest_rs_ratings(*, source: str | None = None) -> int:
    try:
        with SessionLocal() as db:
            latest_query = select(func.max(RsRating.date))
            if source:
                latest_query = latest_query.where(RsRating.source == source)
            latest_date = db.scalar(latest_query)
            if latest_date is None:
                return 0

            count_query = select(func.count()).select_from(RsRating).where(RsRating.date == latest_date)
            if source:
                count_query = count_query.where(RsRating.source == source)
            return int(db.scalar(count_query) or 0)
    except SQLAlchemyError as exc:
        raise RelativeStrengthRepositoryUnavailable(str(exc)) from exc


def get_latest_rs_rating(ticker: str, *, source: str | None = None) -> RsRatingRow | None:
    clean = ticker.strip().upper()
    if not clean:
        return None

    try:
        with SessionLocal() as db:
            query = (
                select(RsRating, Instrument)
                .join(Instrument, Instrument.id == RsRating.instrument_id)
                .where(Instrument.ticker == clean)
            )
            if source:
                query = query.where(RsRating.source == source)
            row = db.execute(query.order_by(RsRating.date.desc()).limit(1)).first()
            if row is None:
                return None
            rating, instrument = row
            return _row_to_dataclass(rating, instrument)
    except SQLAlchemyError as exc:
        raise RelativeStrengthRepositoryUnavailable(str(exc)) from exc


def get_latest_rs_ratings_for_tickers(
    tickers: list[str],
    *,
    source: str | None = None,
) -> dict[str, RsRatingRow]:
    clean_tickers = list(dict.fromkeys(str(ticker).strip().upper() for ticker in tickers if str(ticker).strip()))
    if not clean_tickers:
        return {}

    try:
        with SessionLocal() as db:
            query = (
                select(RsRating, Instrument)
                .join(Instrument, Instrument.id == RsRating.instrument_id)
                .where(Instrument.ticker.in_(clean_tickers))
                .order_by(Instrument.ticker.asc(), RsRating.date.desc())
            )
            if source:
                query = query.where(RsRating.source == source)
            rows = db.execute(query).all()
            latest: dict[str, RsRatingRow] = {}
            for rating, instrument in rows:
                ticker = str(instrument.ticker or "").upper()
                if ticker and ticker not in latest:
                    latest[ticker] = _row_to_dataclass(rating, instrument)
            return latest
    except SQLAlchemyError as exc:
        raise RelativeStrengthRepositoryUnavailable(str(exc)) from exc


def _row_to_dataclass(row: RsRating, instrument: Instrument) -> RsRatingRow:
    return RsRatingRow(
        ticker=instrument.ticker,
        name=instrument.name or instrument.ticker,
        date=row.date,
        rating=row.rating,
        score=row.score,
        percentile=row.percentile,
        method=row.method or "",
        source=row.source or "",
        universe_size=row.universe_size,
        metadata_json=row.metadata_json or {},
    )
