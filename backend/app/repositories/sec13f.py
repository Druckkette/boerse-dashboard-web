from __future__ import annotations

from dataclasses import dataclass
from contextlib import contextmanager
from datetime import date, datetime
from typing import Any

from sqlalchemy import select, func, delete
from sqlalchemy.exc import SQLAlchemyError

from app.db.models import AppSetting, Institutional13FTrend, Instrument, Sec13fCusipMapping
from app.db.session import SessionLocal, engine


@dataclass(frozen=True)
class Institutional13FTrendWrite:
    ticker: str
    cusip: str
    report_period: date
    filing_date: date | None
    shares: float | None
    market_value_usd: float | None
    shares_change_pct: float | None
    holders_count: int
    source_url: str
    raw_json: dict[str, Any]


@dataclass(frozen=True)
class Institutional13FTrendRow:
    ticker: str
    cusip: str
    manager_cik: str
    manager_name: str
    report_period: date
    filing_date: date | None
    shares: float | None
    market_value_usd: float | None
    shares_change_pct: float | None
    holders_count: int
    source_url: str
    raw_json: dict[str, Any]


@dataclass(frozen=True)
class Sec13FMappingRow:
    cusip: str
    ticker: str
    issuer_name: str
    source: str
    confidence: float | None
    metadata_json: dict[str, Any]
    updated_at: datetime | None


class Sec13FRepositoryUnavailable(RuntimeError):
    pass


@contextmanager
def refresh_lock():
    from sqlalchemy import text
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        acquired = connection.scalar(text("SELECT pg_try_advisory_lock(7341503, 13)"))
        if not acquired:
            raise RuntimeError("Ein 13F-Quellenabgleich läuft bereits; bitte später erneut versuchen.")
        try:
            yield
        finally:
            connection.execute(text("SELECT pg_advisory_unlock(7341503, 13)"))


def save_source_status(status: dict, preliminary: dict[str, dict], universe: list[str]) -> None:
    from sqlalchemy import delete
    from sqlalchemy.dialects.postgresql import insert
    try:
        with SessionLocal() as db:
            # A restatement can remove the last reported position in a stock.
            # Clear obsolete previews in this refresh's scope, never other stocks.
            obsolete = [f"sec13f_preliminary:{ticker}" for ticker in universe if ticker not in preliminary]
            for start in range(0, len(obsolete), 500):
                db.execute(delete(AppSetting).where(AppSetting.key.in_(obsolete[start:start + 500])))
            rows = [{"key": "sec13f_source_status", "value_json": status, "description": "EDGAR 13F source verification"}]
            rows.extend({"key": f"sec13f_preliminary:{ticker}", "value_json": value,
                         "description": "Incomplete 13F quarter; excluded from broad trend scores"}
                        for ticker, value in preliminary.items())
            for start in range(0, len(rows), 500):
                statement = insert(AppSetting).values(rows[start:start + 500])
                db.execute(statement.on_conflict_do_update(index_elements=["key"], set_={
                    "value_json": statement.excluded.value_json, "updated_at": func.now()}))
            db.commit()
    except SQLAlchemyError as exc:
        raise Sec13FRepositoryUnavailable(str(exc)) from exc


def source_status_for_ticker(ticker: str) -> tuple[dict, dict | None]:
    try:
        with SessionLocal() as db:
            status = db.get(AppSetting, "sec13f_source_status")
            early = db.get(AppSetting, f"sec13f_preliminary:{ticker}")
            source = dict(status.value_json) if status else {}
            preliminary = dict(early.value_json) if early else None
            if preliminary and preliminary["report_period"] <= source.get("baseline_report_period", ""):
                preliminary = None
            return source, preliminary
    except SQLAlchemyError as exc:
        raise Sec13FRepositoryUnavailable(str(exc)) from exc


def list_known_cusip_mappings(tickers: list[str]) -> dict[str, str]:
    """Reuse established security IDs only when exactly one active ticker owns it."""
    try:
        with SessionLocal() as db:
            rows = db.execute(select(Sec13fCusipMapping.cusip, func.min(Sec13fCusipMapping.ticker))
                .where(Sec13fCusipMapping.ticker.in_(tickers), Sec13fCusipMapping.confidence >= 1)
                .group_by(Sec13fCusipMapping.cusip)
                .having(func.count(func.distinct(Sec13fCusipMapping.ticker)) == 1)).all()
            return {cusip: ticker for cusip, ticker in rows if len(cusip) == 9 and cusip.isalnum()}
    except SQLAlchemyError as exc:
        raise Sec13FRepositoryUnavailable(str(exc)) from exc


def list_symbol_names(tickers: list[str]) -> list[tuple[str, str]]:
    """Listing names are additional aliases; they never override SEC collisions."""
    try:
        with SessionLocal() as db:
            return list(db.execute(select(Instrument.ticker, Instrument.name)
                                   .where(Instrument.ticker.in_(tickers), Instrument.name != "")).all())
    except SQLAlchemyError as exc:
        raise Sec13FRepositoryUnavailable(str(exc)) from exc


def upsert_aggregate_trends(rows: list[Institutional13FTrendWrite]) -> int:
    incoming = [row for row in rows if row.ticker and row.report_period]
    if not incoming:
        return 0
    try:
        with SessionLocal() as db:
            written = 0
            for item in incoming:
                ticker = item.ticker.strip().upper()
                instrument = db.scalars(select(Instrument).where(Instrument.ticker == ticker)).first()
                if instrument is None:
                    instrument = Instrument(ticker=ticker, yahoo_symbol=ticker, name=ticker, currency="USD")
                    db.add(instrument)
                    db.flush()

                cusip = _safe_cusip(item.cusip, ticker)
                mapping = db.scalars(select(Sec13fCusipMapping).where(Sec13fCusipMapping.cusip == cusip)).first()
                if mapping is None:
                    mapping = Sec13fCusipMapping(
                        cusip=cusip,
                        ticker=ticker,
                        instrument_id=instrument.id,
                        issuer_name=instrument.name or ticker,
                        source="sec13f_aggregate",
                        confidence=1.0 if item.cusip else 0.5,
                    )
                    db.add(mapping)

                # A repaired representative CUSIP must not leave an obsolete
                # aggregate for the same ticker and quarter shadowing this one.
                # Obsolete CUSIP rows have not been loaded into this session.
                # Avoid evaluating every previous dirty aggregate for each
                # delete; that turns a full-universe import into quadratic work.
                db.execute(delete(Institutional13FTrend).where(
                    Institutional13FTrend.ticker == ticker,
                    Institutional13FTrend.manager_cik == "AGGREGATE",
                    Institutional13FTrend.report_period == item.report_period,
                    Institutional13FTrend.cusip != cusip,
                ).execution_options(synchronize_session=False))

                row = db.scalars(
                    select(Institutional13FTrend).where(
                        Institutional13FTrend.cusip == cusip,
                        Institutional13FTrend.manager_cik == "AGGREGATE",
                        Institutional13FTrend.report_period == item.report_period,
                    )
                ).first()
                if row is None:
                    row = Institutional13FTrend(
                        instrument_id=instrument.id,
                        ticker=ticker,
                        cusip=cusip,
                        manager_cik="AGGREGATE",
                        manager_name="All 13F holders",
                        report_period=item.report_period,
                    )
                    db.add(row)
                row.instrument_id = instrument.id
                row.ticker = ticker
                row.filing_date = item.filing_date
                row.shares = item.shares
                row.market_value_usd = item.market_value_usd
                row.shares_change_pct = item.shares_change_pct
                row.holders_count = item.holders_count
                row.source_url = item.source_url
                row.raw_json = item.raw_json
                written += 1
            db.commit()
            return written
    except SQLAlchemyError as exc:
        raise Sec13FRepositoryUnavailable(str(exc)) from exc


def get_latest_trend_for_ticker(ticker: str) -> Institutional13FTrendRow | None:
    clean = ticker.strip().upper()
    if not clean:
        return None
    try:
        with SessionLocal() as db:
            row = db.scalars(
                select(Institutional13FTrend)
                .where(Institutional13FTrend.ticker == clean,
                       Institutional13FTrend.manager_cik == "AGGREGATE")
                .order_by(Institutional13FTrend.report_period.desc())
                .limit(1)
            ).first()
            return _to_row(row) if row else None
    except SQLAlchemyError as exc:
        raise Sec13FRepositoryUnavailable(str(exc)) from exc


def get_latest_trends_for_tickers(tickers: list[str]) -> dict[str, Institutional13FTrendRow]:
    clean_tickers = list(dict.fromkeys(str(ticker).strip().upper() for ticker in tickers if str(ticker).strip()))
    if not clean_tickers:
        return {}
    try:
        with SessionLocal() as db:
            rows = db.scalars(
                select(Institutional13FTrend)
                .where(
                    Institutional13FTrend.ticker.in_(clean_tickers),
                    Institutional13FTrend.manager_cik == "AGGREGATE",
                )
                .order_by(
                    Institutional13FTrend.ticker.asc(),
                    Institutional13FTrend.report_period.desc(),
                )
                .distinct(Institutional13FTrend.ticker)
            ).all()
            latest: dict[str, Institutional13FTrendRow] = {}
            for row in rows:
                ticker = str(row.ticker or "").upper()
                if ticker and ticker not in latest:
                    latest[ticker] = _to_row(row)
            return latest
    except SQLAlchemyError as exc:
        raise Sec13FRepositoryUnavailable(str(exc)) from exc


def list_latest_trends(*, limit: int = 100) -> list[Institutional13FTrendRow]:
    try:
        with SessionLocal() as db:
            rows = db.scalars(
                select(Institutional13FTrend)
                .where(Institutional13FTrend.manager_cik == "AGGREGATE")
                .order_by(Institutional13FTrend.report_period.desc(), Institutional13FTrend.market_value_usd.desc())
                .limit(max(1, min(500, limit)))
            ).all()
            return [_to_row(row) for row in rows]
    except SQLAlchemyError as exc:
        raise Sec13FRepositoryUnavailable(str(exc)) from exc


def list_cusip_mappings(*, limit: int = 500) -> list[Sec13FMappingRow]:
    try:
        with SessionLocal() as db:
            rows = db.scalars(
                select(Sec13fCusipMapping)
                .order_by(Sec13fCusipMapping.updated_at.desc(), Sec13fCusipMapping.ticker.asc())
                .limit(max(1, min(1000, limit)))
            ).all()
            return [_mapping_to_row(row) for row in rows]
    except SQLAlchemyError as exc:
        raise Sec13FRepositoryUnavailable(str(exc)) from exc


def list_manual_cusip_overrides() -> dict[str, str]:
    try:
        with SessionLocal() as db:
            rows = db.scalars(
                select(Sec13fCusipMapping).where(Sec13fCusipMapping.source == "manual")
            ).all()
            return {
                row.cusip.upper(): row.ticker.upper()
                for row in rows
                if row.cusip and row.ticker
            }
    except SQLAlchemyError as exc:
        raise Sec13FRepositoryUnavailable(str(exc)) from exc


def upsert_manual_cusip_mapping(
    *,
    cusip: str,
    ticker: str,
    issuer_name: str = "",
) -> Sec13FMappingRow:
    clean_cusip = _normalize_cusip(cusip)
    clean_ticker = ticker.strip().upper()
    if not clean_cusip or not clean_ticker:
        raise ValueError("CUSIP and ticker are required.")

    try:
        with SessionLocal() as db:
            instrument = db.scalars(select(Instrument).where(Instrument.ticker == clean_ticker)).first()
            if instrument is None:
                instrument = Instrument(
                    ticker=clean_ticker,
                    yahoo_symbol=clean_ticker,
                    name=clean_ticker,
                    currency="USD",
                )
                db.add(instrument)
                db.flush()

            row = db.scalars(
                select(Sec13fCusipMapping).where(
                    Sec13fCusipMapping.cusip == clean_cusip,
                    Sec13fCusipMapping.ticker == clean_ticker,
                )
            ).first()
            if row is None:
                row = Sec13fCusipMapping(
                    cusip=clean_cusip,
                    ticker=clean_ticker,
                    instrument_id=instrument.id,
                    issuer_name=issuer_name or instrument.name or clean_ticker,
                    source="manual",
                    confidence=1.0,
                    metadata_json={"manual": True},
                )
                db.add(row)
            else:
                row.instrument_id = instrument.id
                row.ticker = clean_ticker
                row.issuer_name = issuer_name or row.issuer_name or instrument.name or clean_ticker
                row.source = "manual"
                row.confidence = 1.0
                row.metadata_json = {**(row.metadata_json or {}), "manual": True}
            db.commit()
            db.refresh(row)
            return _mapping_to_row(row)
    except SQLAlchemyError as exc:
        raise Sec13FRepositoryUnavailable(str(exc)) from exc


def _to_row(row: Institutional13FTrend) -> Institutional13FTrendRow:
    return Institutional13FTrendRow(
        ticker=row.ticker,
        cusip=row.cusip,
        manager_cik=row.manager_cik,
        manager_name=row.manager_name,
        report_period=row.report_period,
        filing_date=row.filing_date,
        shares=row.shares,
        market_value_usd=row.market_value_usd,
        shares_change_pct=row.shares_change_pct,
        holders_count=row.holders_count,
        source_url=row.source_url,
        raw_json=row.raw_json or {},
    )


def _mapping_to_row(row: Sec13fCusipMapping) -> Sec13FMappingRow:
    return Sec13FMappingRow(
        cusip=row.cusip,
        ticker=row.ticker,
        issuer_name=row.issuer_name,
        source=row.source,
        confidence=row.confidence,
        metadata_json=row.metadata_json or {},
        updated_at=row.updated_at,
    )


def _safe_cusip(raw: str, ticker: str) -> str:
    clean = "".join(char for char in str(raw or "").upper() if char.isalnum())
    if len(clean) == 9:
        return clean
    return f"{ticker[:12]}AGG"[:16]


def _normalize_cusip(raw: str) -> str:
    clean = "".join(char for char in str(raw or "").upper() if char.isalnum())
    return clean if len(clean) == 9 else ""
