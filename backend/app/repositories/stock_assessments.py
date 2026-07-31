from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy import delete, func, select
from sqlalchemy.exc import SQLAlchemyError

from app.db.models import StockAssessmentSnapshot
from app.db.session import SessionLocal


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
