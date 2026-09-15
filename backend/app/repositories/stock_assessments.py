from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy import exists, func, or_, select, text
from sqlalchemy.exc import SQLAlchemyError

from app.db.models import StockAssessmentSnapshot, AppSetting, Instrument, PriceBar
from app.services.market_calendar import expected_us_market_session
from app.db.session import SessionLocal
from app.schemas import StockScreeningFilters


@dataclass(frozen=True)
class StockAssessmentSnapshotWrite:
    ticker: str
    name: str
    as_of: date
    overall_score: int
    technical_score: float
    item_json: dict


@dataclass(frozen=True)
class StockAssessmentSnapshotRow:
    ticker: str
    name: str
    as_of: date
    overall_score: int
    technical_score: float
    generated_at: datetime
    source_job_id: str
    item_json: dict


class StockAssessmentRepositoryUnavailable(RuntimeError):
    pass


def input_revisions(tickers: list[str] | None = None) -> dict[str, str]:
    """Hash small dependency records in Postgres, never transfer OHLC history for reuse checks."""
    query = text("""
        WITH latest_rs_dates AS (
            SELECT source, max(date) AS date
            FROM rs_ratings
            GROUP BY source
        ), latest_rs_rows AS (
            SELECT rr.instrument_id, rr.source, md5(to_jsonb(rr)::text) AS row_hash
            FROM rs_ratings rr
            JOIN latest_rs_dates latest
              ON latest.source = rr.source AND latest.date = rr.date
        ), rs AS (
            SELECT instrument_id, string_agg(row_hash, '|' ORDER BY source) AS revision
            FROM latest_rs_rows GROUP BY instrument_id
        ), fundamentals AS (
            SELECT DISTINCT ON (instrument_id)
                instrument_id, md5(to_jsonb(ff)::text) AS revision
            FROM fundamental_snapshots ff
            ORDER BY instrument_id, as_of DESC, updated_at DESC
        ), holders AS (
            SELECT DISTINCT ON (ticker)
                ticker, md5(to_jsonb(hh)::text) AS revision
            FROM institutional_13f_trends hh
            ORDER BY ticker, report_period DESC, id DESC
        ), earnings AS (
            SELECT ticker, md5(string_agg(to_jsonb(ee)::text, '|' ORDER BY event_date, source)) AS revision
            FROM earnings_events ee WHERE event_date >= CURRENT_DATE GROUP BY ticker
        ), benchmark AS (
            SELECT metadata_json->>'price_revision' AS revision FROM instruments WHERE ticker = 'SPY'
        )
        SELECT i.ticker, md5(concat_ws('|', i.metadata_json->>'price_revision',
            rs.revision, fundamentals.revision, holders.revision, earnings.revision,
            (SELECT revision FROM benchmark),
            (SELECT value_json->>'rs_rating_source' FROM app_settings WHERE key = 'runtime'))) AS revision
        FROM instruments i
        LEFT JOIN rs ON rs.instrument_id = i.id
        LEFT JOIN fundamentals ON fundamentals.instrument_id = i.id
        LEFT JOIN holders ON holders.ticker = i.ticker
        LEFT JOIN earnings ON earnings.ticker = i.ticker
        WHERE i.metadata_json->>'price_revision' IS NOT NULL
    """ + (" AND i.ticker = ANY(:tickers)" if tickers is not None else ""))
    try:
        with SessionLocal() as db:
            return dict(db.execute(query, {"tickers": tickers} if tickers is not None else {}).all())
    except SQLAlchemyError as exc:
        raise StockAssessmentRepositoryUnavailable(str(exc)) from exc


def replace_snapshots(rows: list[StockAssessmentSnapshotWrite], *, source_job_id: str = "", replace_all: bool = True) -> int:
    generated_at = datetime.now(UTC)
    try:
        with SessionLocal() as db:
            query = select(StockAssessmentSnapshot)
            if not replace_all:
                query = query.where(StockAssessmentSnapshot.ticker.in_([row.ticker for row in rows]))
            existing = {row.ticker: row for row in db.scalars(query).all()}
            published = {row.ticker for row in rows}
            for ticker, row in existing.items():
                if replace_all and ticker not in published:
                    db.delete(row)
            summary = rows[0].item_json.get("_screening", {}) if rows else {}
            summary_row = db.get(AppSetting, "stock_screening_summary")
            if summary_row is None and replace_all:
                db.add(AppSetting(key="stock_screening_summary", value_json=summary, description="Atomic screening run summary"))
            elif replace_all:
                summary_row.value_json = summary
            for item in rows:
                data = {key: value for key, value in item.item_json.items() if key != "_screening"}
                previous = existing.get(item.ticker)
                if previous is not None:
                    if previous.item_json != data:
                        previous.name = item.name
                        previous.as_of = item.as_of
                        previous.overall_score = item.overall_score
                        previous.technical_score = item.technical_score
                        previous.generated_at = generated_at
                        previous.source_job_id = source_job_id
                        previous.item_json = data
                    continue
                db.add(
                    StockAssessmentSnapshot(
                        ticker=item.ticker,
                        name=item.name,
                        as_of=item.as_of,
                        overall_score=item.overall_score,
                        technical_score=item.technical_score,
                        generated_at=generated_at,
                        source_job_id=source_job_id,
                        item_json=data,
                    )
                )
            db.commit()
            return len(rows)
    except SQLAlchemyError as exc:
        raise StockAssessmentRepositoryUnavailable(str(exc)) from exc


def list_snapshots(*, limit: int = 60) -> list[StockAssessmentSnapshotRow]:
    try:
        with SessionLocal() as db:
            rows = db.scalars(
                select(StockAssessmentSnapshot)
                .order_by(
                    StockAssessmentSnapshot.overall_score.desc(),
                    StockAssessmentSnapshot.technical_score.desc(),
                    StockAssessmentSnapshot.ticker.asc(),
                )
                .limit(max(1, min(500, limit)))
            ).all()
            return [_to_row(row) for row in rows]
    except SQLAlchemyError as exc:
        raise StockAssessmentRepositoryUnavailable(str(exc)) from exc


def count_snapshots() -> int:
    try:
        with SessionLocal() as db:
            return int(db.scalar(select(func.count()).select_from(StockAssessmentSnapshot)) or 0)
    except SQLAlchemyError as exc:
        raise StockAssessmentRepositoryUnavailable(str(exc)) from exc


def list_all_snapshots(tickers: list[str] | None = None) -> list[StockAssessmentSnapshotRow]:
    try:
        with SessionLocal() as db:
            query = select(StockAssessmentSnapshot)
            if tickers is not None:
                query = query.where(StockAssessmentSnapshot.ticker.in_(tickers))
            rows = db.scalars(query.order_by(
                StockAssessmentSnapshot.overall_score.desc(),
                StockAssessmentSnapshot.technical_score.desc(),
                StockAssessmentSnapshot.ticker.asc(),
            )).all()
            return [_to_row(row) for row in rows]
    except SQLAlchemyError as exc:
        raise StockAssessmentRepositoryUnavailable(str(exc)) from exc


def query_screening(filters: StockScreeningFilters, *, expected_date: date, export: bool = False) -> dict:
    model = StockAssessmentSnapshot
    data = model.item_json
    session = expected_us_market_session()
    boundary = session.open_at if session.phase == "intraday" else session.close_at
    current_price = exists(select(PriceBar.id).join(Instrument, Instrument.id == PriceBar.instrument_id).where(
        Instrument.ticker == model.ticker, PriceBar.date >= expected_date,
        PriceBar.fetched_at >= boundary, PriceBar.close.is_not(None),
    ).correlate(model))
    conditions = [
        model.overall_score >= filters.min_score,
        data["warnings_count"].as_integer() <= filters.max_warnings,
    ]
    if filters.min_rs:
        conditions.append(data["rs_rating"].as_integer() >= filters.min_rs)
    if filters.min_fundamental:
        conditions.extend([
            data["fundamentals_available"].as_boolean().is_(True),
            data["fundamental_score"].as_float() >= filters.min_fundamental,
        ])
    if filters.complete_only:
        conditions.append(current_price)
        conditions.append(data["dependencies_current"].as_boolean().is_(True))
        conditions.extend([model.as_of >= expected_date, data["rs_rating"].as_integer().is_not(None)])
        conditions.extend(data[key].as_boolean().is_(True) for key in (
            "fundamentals_available", "rs_line_available", "institutional_available",
        ))
    if filters.search.strip():
        conditions.append(or_(
            model.ticker.icontains(filters.search.strip(), autoescape=True),
            model.name.icontains(filters.search.strip(), autoescape=True),
        ))
    for label in filters.required:
        conditions.append(data["checks"].contains([{"label": label, "passed": True}]))
    score = getattr(model, filters.sort) if filters.sort in {"overall_score", "technical_score"} else data[filters.sort].as_float()
    try:
        with SessionLocal() as db:
            first = db.scalar(select(model).limit(1))
            summary_row = db.get(AppSetting, "stock_screening_summary")
            summary = dict(summary_row.value_json) if summary_row else dict(first.item_json.get("_screening", {})) if first else {}
            criteria = summary.pop("criteria", [])
            summary["stale_count"] = db.scalar(select(func.count()).select_from(model).where(or_(model.as_of < expected_date, ~current_price))) or 0
            total = db.scalar(select(func.count()).select_from(model).where(*conditions)) or 0
            query = select(model, current_price.label("price_current")).where(*conditions).order_by(
                score.desc().nullslast(), model.overall_score.desc(), model.ticker.asc(),
            )
            if not export:
                query = query.offset(filters.page * 50).limit(50)
            rows = db.execute(query).all()
            return {
                "summary": summary, "criteria": criteria, "total_count": total,
                "rows": [
                    {**{key: value for key, value in row.item_json.items() if not key.startswith("_")},
                     "prices_stale": row.as_of < expected_date or not price_current}
                    for row, price_current in rows
                ],
            }
    except SQLAlchemyError as exc:
        raise StockAssessmentRepositoryUnavailable(str(exc)) from exc


def latest_generated_at() -> datetime | None:
    try:
        with SessionLocal() as db:
            return db.scalar(select(func.max(StockAssessmentSnapshot.generated_at)))
    except SQLAlchemyError as exc:
        raise StockAssessmentRepositoryUnavailable(str(exc)) from exc


def _to_row(row: StockAssessmentSnapshot) -> StockAssessmentSnapshotRow:
    return StockAssessmentSnapshotRow(
        ticker=row.ticker,
        name=row.name,
        as_of=row.as_of,
        overall_score=row.overall_score,
        technical_score=row.technical_score,
        generated_at=row.generated_at,
        source_job_id=row.source_job_id,
        item_json=row.item_json or {},
    )
