from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from app.db.models import FundamentalSnapshot, Instrument
from app.db.session import SessionLocal


@dataclass(frozen=True)
class FundamentalSnapshotWrite:
    ticker: str
    as_of: date
    source: str = "manual"
    fiscal_period: str = ""
    quarterly_eps_growth_pct: float | None = None
    annual_eps_growth_pct: float | None = None
    quarterly_revenue_growth_pct: float | None = None
    annual_revenue_growth_pct: float | None = None
    roe_pct: float | None = None
    profit_margin_pct: float | None = None
    trailing_eps: float | None = None
    quarterly_eps_accelerating: bool | None = None
    quarterly_revenue_accelerating: bool | None = None
    institutional_holders: int | None = None
    institutional_ownership_pct: float | None = None
    next_earnings_date: date | None = None
    beta: float | None = None
    metadata_json: dict | None = None


@dataclass(frozen=True)
class FundamentalSnapshotRow:
    ticker: str
    as_of: date
    source: str
    fiscal_period: str
    quarterly_eps_growth_pct: float | None
    annual_eps_growth_pct: float | None
    quarterly_revenue_growth_pct: float | None
    annual_revenue_growth_pct: float | None
    roe_pct: float | None
    profit_margin_pct: float | None
    trailing_eps: float | None
    quarterly_eps_accelerating: bool | None
    quarterly_revenue_accelerating: bool | None
    institutional_holders: int | None
    institutional_ownership_pct: float | None
    next_earnings_date: date | None
    beta: float | None
    metadata_json: dict


class FundamentalsRepositoryUnavailable(RuntimeError):
    pass


def get_latest_fundamentals(ticker: str) -> FundamentalSnapshotRow | None:
    clean = ticker.strip().upper()
    if not clean:
        return None

    try:
        with SessionLocal() as db:
            row = db.scalars(
                select(FundamentalSnapshot)
                .where(FundamentalSnapshot.ticker == clean)
                .order_by(FundamentalSnapshot.as_of.desc(), FundamentalSnapshot.updated_at.desc())
                .limit(1)
            ).first()
            return _to_row(row) if row else None
    except SQLAlchemyError as exc:
        raise FundamentalsRepositoryUnavailable(str(exc)) from exc


def latest_fundamental_dates(tickers: list[str]) -> dict[str, date]:
    clean_tickers = list(dict.fromkeys(str(ticker).strip().upper() for ticker in tickers if str(ticker).strip()))
    if not clean_tickers:
        return {}

    try:
        with SessionLocal() as db:
            rows = db.execute(
                select(FundamentalSnapshot.ticker, func.max(FundamentalSnapshot.as_of))
                .where(FundamentalSnapshot.ticker.in_(clean_tickers))
                .group_by(FundamentalSnapshot.ticker)
            ).all()
            return {
                str(ticker).upper(): value
                for ticker, value in rows
                if ticker and value is not None
            }
    except SQLAlchemyError as exc:
        raise FundamentalsRepositoryUnavailable(str(exc)) from exc


def upsert_fundamentals(payload: FundamentalSnapshotWrite) -> FundamentalSnapshotRow:
    clean = payload.ticker.strip().upper()
    if not clean:
        raise ValueError("ticker must not be empty")

    try:
        with SessionLocal() as db:
            instrument = db.scalars(select(Instrument).where(Instrument.ticker == clean)).first()
            if instrument is None:
                instrument = Instrument(ticker=clean, yahoo_symbol=clean, name=clean, currency="USD")
                db.add(instrument)
                db.flush()

            row = db.scalars(
                select(FundamentalSnapshot).where(
                    FundamentalSnapshot.instrument_id == instrument.id,
                    FundamentalSnapshot.as_of == payload.as_of,
                    FundamentalSnapshot.source == payload.source,
                )
            ).first()
            if row is None:
                row = FundamentalSnapshot(
                    instrument_id=instrument.id,
                    ticker=clean,
                    as_of=payload.as_of,
                    source=payload.source,
                )
                db.add(row)

            row.ticker = clean
            row.fiscal_period = payload.fiscal_period
            row.quarterly_eps_growth_pct = payload.quarterly_eps_growth_pct
            row.annual_eps_growth_pct = payload.annual_eps_growth_pct
            row.quarterly_revenue_growth_pct = payload.quarterly_revenue_growth_pct
            row.annual_revenue_growth_pct = payload.annual_revenue_growth_pct
            row.roe_pct = payload.roe_pct
            row.profit_margin_pct = payload.profit_margin_pct
            row.trailing_eps = payload.trailing_eps
            row.quarterly_eps_accelerating = payload.quarterly_eps_accelerating
            row.quarterly_revenue_accelerating = payload.quarterly_revenue_accelerating
            row.institutional_holders = payload.institutional_holders
            row.institutional_ownership_pct = payload.institutional_ownership_pct
            row.next_earnings_date = payload.next_earnings_date
            row.beta = payload.beta
            row.metadata_json = payload.metadata_json or {}

            db.commit()
            db.refresh(row)
            return _to_row(row)
    except SQLAlchemyError as exc:
        raise FundamentalsRepositoryUnavailable(str(exc)) from exc


def _to_row(row: FundamentalSnapshot) -> FundamentalSnapshotRow:
    return FundamentalSnapshotRow(
        ticker=row.ticker,
        as_of=row.as_of,
        source=row.source,
        fiscal_period=row.fiscal_period,
        quarterly_eps_growth_pct=row.quarterly_eps_growth_pct,
        annual_eps_growth_pct=row.annual_eps_growth_pct,
        quarterly_revenue_growth_pct=row.quarterly_revenue_growth_pct,
        annual_revenue_growth_pct=row.annual_revenue_growth_pct,
        roe_pct=row.roe_pct,
        profit_margin_pct=row.profit_margin_pct,
        trailing_eps=row.trailing_eps,
        quarterly_eps_accelerating=row.quarterly_eps_accelerating,
        quarterly_revenue_accelerating=row.quarterly_revenue_accelerating,
        institutional_holders=row.institutional_holders,
        institutional_ownership_pct=row.institutional_ownership_pct,
        next_earnings_date=row.next_earnings_date,
        beta=row.beta,
        metadata_json=row.metadata_json or {},
    )
