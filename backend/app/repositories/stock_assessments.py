from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy import delete, func, or_, select
from sqlalchemy.exc import SQLAlchemyError

from app.db.models import StockAssessmentSnapshot
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


def replace_snapshots(rows: list[StockAssessmentSnapshotWrite], *, source_job_id: str = "") -> int:
    generated_at = datetime.now(UTC)
    try:
        with SessionLocal() as db:
            db.execute(delete(StockAssessmentSnapshot))
            for item in rows:
                db.add(
                    StockAssessmentSnapshot(
                        ticker=item.ticker,
                        name=item.name,
                        as_of=item.as_of,
                        overall_score=item.overall_score,
                        technical_score=item.technical_score,
                        generated_at=generated_at,
                        source_job_id=source_job_id,
                        item_json=item.item_json,
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


def list_all_snapshots() -> list[StockAssessmentSnapshotRow]:
    try:
        with SessionLocal() as db:
            rows = db.scalars(select(StockAssessmentSnapshot).order_by(
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
            summary = dict(first.item_json.get("_screening", {})) if first else {}
            criteria = summary.pop("criteria", [])
            summary["stale_count"] = db.scalar(select(func.count()).select_from(model).where(model.as_of < expected_date)) or 0
            total = db.scalar(select(func.count()).select_from(model).where(*conditions)) or 0
            query = select(model).where(*conditions).order_by(
                score.desc().nullslast(), model.overall_score.desc(), model.ticker.asc(),
            )
            if not export:
                query = query.offset(filters.page * 50).limit(50)
            rows = db.scalars(query).all()
            return {
                "summary": summary, "criteria": criteria, "total_count": total,
                "rows": [
                    {**{key: value for key, value in row.item_json.items() if not key.startswith("_")},
                     "prices_stale": row.as_of < expected_date}
                    for row in rows
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
