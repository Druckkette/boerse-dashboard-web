from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.db.models import BreadthDaily, Instrument, MarketSnapshot, PriceBar
from app.db.session import SessionLocal


@dataclass(frozen=True)
class MarketPricePoint:
    ticker: str
    date: date
    close: float


@dataclass(frozen=True)
class MarketOhlcvPoint:
    ticker: str
    date: date
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class BreadthDailyWrite:
    universe: str
    date: date
    advancers: int
    decliners: int
    ad_line: float | None
    mcclellan: float | None
    pct_above_20sma: float | None
    pct_above_50sma: float | None
    pct_above_200sma: float | None
    new_highs: int
    new_lows: int
    metadata_json: dict


@dataclass(frozen=True)
class MarketSnapshotWrite:
    date: date
    ampel_phase: str
    warning_count: int
    breadth_mode: str
    volatility_regime: str
    metrics_json: dict


class MarketRepositoryUnavailable(RuntimeError):
    pass


def load_cached_prices(tickers: Iterable[str], *, start_date: date) -> dict[str, list[MarketPricePoint]]:
    clean_tickers = list(dict.fromkeys(ticker.strip().upper() for ticker in tickers if ticker.strip()))
    if not clean_tickers:
        return {}

    try:
        with SessionLocal() as db:
            rows = db.execute(
                select(Instrument.ticker, PriceBar.date, PriceBar.close)
                .join(PriceBar, PriceBar.instrument_id == Instrument.id)
                .where(
                    Instrument.ticker.in_(clean_tickers),
                    PriceBar.date >= start_date,
                    PriceBar.close.is_not(None),
                )
                .order_by(Instrument.ticker.asc(), PriceBar.date.asc())
            ).all()
    except SQLAlchemyError as exc:
        raise MarketRepositoryUnavailable(str(exc)) from exc

    series: dict[str, list[MarketPricePoint]] = {ticker: [] for ticker in clean_tickers}
    for ticker, bar_date, close in rows:
        if close is None:
            continue
        series.setdefault(str(ticker), []).append(
            MarketPricePoint(ticker=str(ticker), date=bar_date, close=float(close))
        )
    return {ticker: points for ticker, points in series.items() if points}


def load_cached_ohlcv(ticker: str, *, start_date: date) -> list[MarketOhlcvPoint]:
    clean = ticker.strip().upper()
    if not clean:
        return []

    try:
        with SessionLocal() as db:
            rows = db.execute(
                select(
                    Instrument.ticker,
                    PriceBar.date,
                    PriceBar.open,
                    PriceBar.high,
                    PriceBar.low,
                    PriceBar.close,
                    PriceBar.volume,
                )
                .join(PriceBar, PriceBar.instrument_id == Instrument.id)
                .where(
                    Instrument.ticker == clean,
                    PriceBar.date >= start_date,
                    PriceBar.close.is_not(None),
                )
                .order_by(PriceBar.date.asc())
            ).all()
    except SQLAlchemyError as exc:
        raise MarketRepositoryUnavailable(str(exc)) from exc

    points: list[MarketOhlcvPoint] = []
    for row_ticker, bar_date, open_, high, low, close, volume in rows:
        close_value = float(close)
        points.append(
            MarketOhlcvPoint(
                ticker=str(row_ticker),
                date=bar_date,
                open=float(open_ if open_ is not None else close_value),
                high=float(high if high is not None else close_value),
                low=float(low if low is not None else close_value),
                close=close_value,
                volume=float(volume or 0),
            )
        )
    return points


def upsert_breadth_daily(points: Iterable[BreadthDailyWrite]) -> int:
    incoming = list(points)
    if not incoming:
        return 0

    try:
        with SessionLocal() as db:
            written = 0
            for point in incoming:
                row = db.scalars(
                    select(BreadthDaily).where(
                        BreadthDaily.universe == point.universe,
                        BreadthDaily.date == point.date,
                    )
                ).first()
                if row is None:
                    row = BreadthDaily(universe=point.universe, date=point.date)
                    db.add(row)
                row.advancers = point.advancers
                row.decliners = point.decliners
                row.ad_line = point.ad_line
                row.mcclellan = point.mcclellan
                row.pct_above_20sma = point.pct_above_20sma
                row.pct_above_50sma = point.pct_above_50sma
                row.pct_above_200sma = point.pct_above_200sma
                row.new_highs = point.new_highs
                row.new_lows = point.new_lows
                row.metadata_json = point.metadata_json
                written += 1
            db.commit()
            return written
    except SQLAlchemyError as exc:
        raise MarketRepositoryUnavailable(str(exc)) from exc


def upsert_market_snapshot(snapshot: MarketSnapshotWrite) -> None:
    try:
        with SessionLocal() as db:
            row = db.scalars(select(MarketSnapshot).where(MarketSnapshot.date == snapshot.date)).first()
            if row is None:
                row = MarketSnapshot(date=snapshot.date, ampel_phase=snapshot.ampel_phase)
                db.add(row)
            row.ampel_phase = snapshot.ampel_phase
            row.warning_count = snapshot.warning_count
            row.breadth_mode = snapshot.breadth_mode
            row.volatility_regime = snapshot.volatility_regime
            row.metrics_json = snapshot.metrics_json
            db.commit()
    except SQLAlchemyError as exc:
        raise MarketRepositoryUnavailable(str(exc)) from exc


def list_breadth_daily(universe: str | None = None, *, limit: int = 160) -> list[BreadthDaily]:
    try:
        with SessionLocal() as db:
            query = select(BreadthDaily)
            if universe:
                query = query.where(BreadthDaily.universe == universe)
            rows = db.scalars(query.order_by(BreadthDaily.date.desc()).limit(max(1, min(500, limit)))).all()
            return list(reversed(rows))
    except SQLAlchemyError as exc:
        raise MarketRepositoryUnavailable(str(exc)) from exc


def get_latest_market_snapshot() -> MarketSnapshot | None:
    try:
        with SessionLocal() as db:
            return db.scalars(select(MarketSnapshot).order_by(MarketSnapshot.date.desc()).limit(1)).first()
    except SQLAlchemyError as exc:
        raise MarketRepositoryUnavailable(str(exc)) from exc
