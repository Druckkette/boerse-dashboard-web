from __future__ import annotations

from datetime import UTC, date, datetime, time

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from app.db.models import BreadthDaily, PriceBar, RsRating
from app.db.session import SessionLocal
from app.repositories import jobs as job_repository
from app.schemas import FreshnessResponse, ServiceFreshness


def get_freshness() -> FreshnessResponse:
    now = datetime.now(UTC)
    services = _cache_freshness(now)
    services.append(_job_freshness(now, "sell_ranking", "position_atr_monitor", max_lag_minutes=120))
    return FreshnessResponse(generated_at=now, services=services)


def _cache_freshness(now: datetime) -> list[ServiceFreshness]:
    try:
        with SessionLocal() as db:
            latest_price = db.scalar(select(func.max(PriceBar.date)).where(PriceBar.close.is_not(None)))
            latest_breadth = db.scalar(select(func.max(BreadthDaily.date)))
            latest_rs = db.scalar(select(func.max(RsRating.date)))
    except SQLAlchemyError:
        return [
            _missing("prices"),
            _missing("market_breadth"),
            _missing("relative_strength"),
        ]

    return [
        _date_freshness(now, "prices", latest_price, max_lag_days=5),
        _date_freshness(now, "market_breadth", latest_breadth, max_lag_days=5),
        _date_freshness(now, "relative_strength", latest_rs, max_lag_days=7),
    ]


def _job_freshness(
    now: datetime,
    service_name: str,
    job_type: str,
    *,
    max_lag_minutes: int,
) -> ServiceFreshness:
    latest_job = next(
        (
            job
            for job in job_repository.list_jobs(limit=80)
            if job.job_type == job_type and job.status in {"done", "skipped", "failed", "cancelled"}
        ),
        None,
    )
    if latest_job is None or latest_job.finished_at is None:
        return _missing(service_name)

    finished_at = _as_utc(latest_job.finished_at)
    lag_minutes = _lag_minutes(now, finished_at)
    status = "fresh" if latest_job.status in {"done", "skipped"} and lag_minutes <= max_lag_minutes else "stale"
    return ServiceFreshness(
        name=service_name,
        status=status,
        as_of=finished_at.isoformat(),
        lag_minutes=lag_minutes,
    )


def _date_freshness(
    now: datetime,
    service_name: str,
    latest_date: date | None,
    *,
    max_lag_days: int,
) -> ServiceFreshness:
    if latest_date is None:
        return _missing(service_name)
    as_of_dt = datetime.combine(latest_date, time.min, tzinfo=UTC)
    lag_minutes = _lag_minutes(now, as_of_dt)
    return ServiceFreshness(
        name=service_name,
        status="fresh" if lag_minutes <= max_lag_days * 24 * 60 else "stale",
        as_of=latest_date.isoformat(),
        lag_minutes=lag_minutes,
    )


def _missing(service_name: str) -> ServiceFreshness:
    return ServiceFreshness(name=service_name, status="missing", as_of="", lag_minutes=0)


def _lag_minutes(now: datetime, then: datetime) -> int:
    return max(0, int((now - then).total_seconds() // 60))


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
