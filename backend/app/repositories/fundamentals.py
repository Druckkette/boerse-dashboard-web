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


@dataclass(frozen=True)
class FundamentalRefreshState:
    ticker: str
    latest_date: date | None
    complete: bool
    missing_history_keys: list[str]


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


def get_latest_fundamentals_for_tickers(tickers: list[str]) -> dict[str, FundamentalSnapshotRow]:
    clean_tickers = list(dict.fromkeys(str(ticker).strip().upper() for ticker in tickers if str(ticker).strip()))
    if not clean_tickers:
        return {}

    try:
        with SessionLocal() as db:
            rows = db.scalars(
                select(FundamentalSnapshot)
                .where(FundamentalSnapshot.ticker.in_(clean_tickers))
                .order_by(
                    FundamentalSnapshot.ticker.asc(),
                    FundamentalSnapshot.as_of.desc(),
                    FundamentalSnapshot.updated_at.desc(),
                )
            ).all()
            latest: dict[str, FundamentalSnapshotRow] = {}
            for row in rows:
                ticker = str(row.ticker or "").upper()
                if ticker and ticker not in latest:
                    latest[ticker] = _to_row(row)
            return latest
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


def latest_fundamental_refresh_states(tickers: list[str]) -> dict[str, FundamentalRefreshState]:
    clean_tickers = list(dict.fromkeys(str(ticker).strip().upper() for ticker in tickers if str(ticker).strip()))
    if not clean_tickers:
        return {}

    try:
        with SessionLocal() as db:
            rows = db.scalars(
                select(FundamentalSnapshot)
                .where(FundamentalSnapshot.ticker.in_(clean_tickers))
                .order_by(
                    FundamentalSnapshot.ticker.asc(),
                    FundamentalSnapshot.as_of.desc(),
                    FundamentalSnapshot.updated_at.desc(),
                )
            ).all()
            latest_by_ticker: dict[str, FundamentalSnapshot] = {}
            for row in rows:
                ticker = str(row.ticker or "").upper()
                if ticker and ticker not in latest_by_ticker:
                    latest_by_ticker[ticker] = row
            return {
                ticker: _refresh_state_from_snapshot(ticker, latest_by_ticker.get(ticker))
                for ticker in clean_tickers
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


def _refresh_state_from_snapshot(
    ticker: str,
    row: FundamentalSnapshot | None,
) -> FundamentalRefreshState:
    if row is None:
        return FundamentalRefreshState(ticker=ticker, latest_date=None, complete=False, missing_history_keys=["snapshot"])
    missing = _missing_required_history_keys(row.metadata_json or {})
    return FundamentalRefreshState(
        ticker=ticker,
        latest_date=row.as_of,
        complete=not missing,
        missing_history_keys=missing,
    )


def _missing_required_history_keys(metadata: dict) -> list[str]:
    required = [
        "eps_quarter_history",
        "annual_eps_history",
        "revenue_quarter_history",
        "annual_revenue_history",
    ]
    return [key for key in required if _usable_history_count(_metadata_history(metadata, key)) < 3]


def _metadata_history(metadata: dict, key: str) -> list:
    candidates = [
        metadata.get(key),
        (metadata.get("enrichment") or {}).get(key) if isinstance(metadata.get("enrichment"), dict) else None,
    ]
    fallback_by_key = {
        "eps_quarter_history": "eps_growth",
        "annual_eps_history": "annual_eps_growth",
        "revenue_quarter_history": "revenue_growth",
        "annual_revenue_history": "annual_revenue_growth",
    }
    fallback = fallback_by_key.get(key)
    if fallback:
        candidates.extend(
            [
                metadata.get(fallback),
                (metadata.get("enrichment") or {}).get(fallback)
                if isinstance(metadata.get("enrichment"), dict)
                else None,
            ]
        )
    for candidate in candidates:
        if isinstance(candidate, list) and candidate:
            return candidate
    return []


def _usable_history_count(history: list) -> int:
    count = 0
    for item in history[:3]:
        if not isinstance(item, dict):
            continue
        current = _first_present(
            item,
            "eps_current_quarter",
            "eps_current_year",
            "revenue_current_quarter",
            "revenue_current_year",
            "current",
        )
        previous = _first_present(
            item,
            "eps_same_quarter_last_year",
            "eps_previous_year",
            "revenue_same_quarter_last_year",
            "revenue_previous_year",
            "previous",
            "prior",
        )
        growth = _first_present(
            item,
            "eps_growth_yoy_pct",
            "revenue_growth_yoy_pct",
            "growth_pct",
        )
        if growth is not None or (current is not None and previous is not None):
            count += 1
    return count


def _first_present(item: dict, *keys: str) -> object | None:
    for key in keys:
        value = item.get(key)
        if value not in (None, ""):
            return value
    return None
