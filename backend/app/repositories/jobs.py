from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.models import Job as JobModel
from app.db.session import SessionLocal
from app.schemas import Job, JobType


TERMINAL_JOB_STATUSES: set[str] = {"done", "failed", "skipped", "cancelled"}
ACTIVE_JOB_STATUSES: set[str] = {"queued", "running"}
SUPPORTED_JOB_TYPES: set[str] = {
    "smart_refresh_market_data",
    "bootstrap_market_data",
    "refresh_prices",
    "refresh_breadth",
    "refresh_relative_strength",
    "refresh_fundamentals",
    "refresh_stock_detail",
    "refresh_sec13f",
    "refresh_universe",
    "position_atr_monitor",
    "pushover_test",
    "yahoo_symbol_diagnostics",
    "yahoo_symbol_rescue",
}

_MEMORY_JOBS: dict[str, Job] = {}
QUEUED_JOB_STALE_AFTER = timedelta(minutes=30)
RUNNING_JOB_STALE_AFTER = timedelta(minutes=90)
QUEUED_JOB_EXPIRES_SECONDS = int(QUEUED_JOB_STALE_AFTER.total_seconds())
SCHEDULED_MONITOR_HISTORY_LIMIT = 20
SCHEDULED_MONITOR_JOB_TYPE = "position_atr_monitor"
SCHEDULER_REQUESTED_BY = "scheduler"


def create_job(
    job_type: JobType | str,
    payload: dict | None = None,
    *,
    requested_by: str = "api",
) -> Job:
    if str(job_type) == SCHEDULED_MONITOR_JOB_TYPE and requested_by == SCHEDULER_REQUESTED_BY:
        prune_terminal_job_history(
            job_type=SCHEDULED_MONITOR_JOB_TYPE,
            requested_by=SCHEDULER_REQUESTED_BY,
            keep=SCHEDULED_MONITOR_HISTORY_LIMIT,
        )
    now = _utcnow()
    job = Job(
        job_id=f"job_{job_type}_{uuid4().hex[:12]}",
        job_type=str(job_type),
        status="queued",
        progress=0,
        current_step="Queued",
        message="Job wurde angenommen.",
        requested_by=requested_by,
        payload=payload or {},
        created_at=now,
        requested_at=now,
        heartbeat_at=now,
        result={},
    )
    return _with_db(lambda db: _create_job_db(db, job), fallback=lambda: _store_memory(job))


def list_jobs(limit: int = 50) -> list[Job]:
    reconcile_stale_jobs()
    return _with_db(lambda db: _list_jobs_db(db, limit), fallback=lambda: _list_jobs_memory(limit))


def list_active_jobs() -> list[Job]:
    reconcile_stale_jobs()
    return _with_db(_list_active_jobs_db, fallback=_list_active_jobs_memory)


def get_job(job_id: str) -> Job | None:
    return _with_db(lambda db: _get_job_db(db, job_id), fallback=lambda: _MEMORY_JOBS.get(job_id))


def set_celery_task_id(job_id: str, celery_task_id: str) -> Job | None:
    return update_job(job_id, celery_task_id=celery_task_id)


def mark_running(job_id: str, *, step: str = "Gestartet") -> Job | None:
    return update_job(
        job_id,
        status="running",
        progress=5,
        current_step=step,
        message="Worker hat den Job gestartet.",
        started_at=_utcnow(),
        error_message="",
    )


def update_progress(
    job_id: str,
    *,
    progress: int,
    step: str,
    message: str = "",
    result: dict | None = None,
) -> Job | None:
    values: dict = {
        "status": "running",
        "progress": max(0, min(100, progress)),
        "current_step": step,
    }
    if message:
        values["message"] = message
    if result is not None:
        values["result_json"] = result
    return update_job(job_id, **values)


def mark_done(job_id: str, *, result: dict | None = None, message: str = "Abgeschlossen") -> Job | None:
    return update_job(
        job_id,
        status="done",
        progress=100,
        current_step="Abgeschlossen",
        message=message,
        result_json=result or {},
        finished_at=_utcnow(),
        error_message="",
    )


def mark_failed(job_id: str, *, error_message: str, result: dict | None = None) -> Job | None:
    return update_job(
        job_id,
        status="failed",
        current_step="Fehlgeschlagen",
        message="Job ist fehlgeschlagen.",
        error_message=error_message,
        result_json=result or {},
        finished_at=_utcnow(),
    )


def mark_cancelled(job_id: str, *, message: str = "Job wurde abgebrochen.") -> Job | None:
    return update_job(
        job_id,
        status="cancelled",
        current_step="Abgebrochen",
        message=message,
        finished_at=_utcnow(),
    )


def mark_skipped(job_id: str, *, message: str, result: dict | None = None) -> Job | None:
    return update_job(
        job_id,
        status="skipped",
        progress=100,
        current_step="Übersprungen",
        message=message,
        result_json=result or {},
        finished_at=_utcnow(),
    )


def is_cancelled(job_id: str) -> bool:
    job = get_job(job_id)
    return bool(job and job.status == "cancelled")


def active_job_exists() -> bool:
    reconcile_stale_jobs()
    return _with_db(_active_job_exists_db, fallback=_active_job_exists_memory)


def reconcile_stale_jobs() -> int:
    return _with_db(_reconcile_stale_jobs_db, fallback=_reconcile_stale_jobs_memory)


def prune_terminal_job_history(*, job_type: str, requested_by: str, keep: int = 20) -> int:
    normalized_keep = max(1, int(keep))
    return _with_db(
        lambda db: _prune_terminal_job_history_db(
            db,
            job_type=job_type,
            requested_by=requested_by,
            keep=normalized_keep,
        ),
        fallback=lambda: _prune_terminal_job_history_memory(
            job_type=job_type,
            requested_by=requested_by,
            keep=normalized_keep,
        ),
    )


def clear_memory_jobs() -> None:
    _MEMORY_JOBS.clear()


def update_job(job_id: str, **values) -> Job | None:
    values["heartbeat_at"] = _utcnow()
    return _with_db(
        lambda db: _update_job_db(db, job_id, values),
        fallback=lambda: _update_job_memory(job_id, values),
    )


def _create_job_db(db: Session, job: Job) -> Job:
    row = JobModel(
        job_id=job.job_id,
        celery_task_id=job.celery_task_id,
        job_type=job.job_type,
        status=job.status,
        progress=job.progress,
        current_step=job.current_step,
        message=job.message,
        error_message=job.error_message,
        requested_by=job.requested_by,
        payload_json=job.payload,
        result_json=job.result,
        created_at=job.created_at,
        requested_at=job.requested_at,
        started_at=job.started_at,
        heartbeat_at=job.heartbeat_at,
        finished_at=job.finished_at,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _row_to_schema(row)


def _list_jobs_db(db: Session, limit: int) -> list[Job]:
    normalized_limit = max(1, min(200, limit))
    active_rows = db.scalars(
        select(JobModel).where(JobModel.status.in_(ACTIVE_JOB_STATUSES)).order_by(JobModel.created_at.desc())
    ).all()
    recent_rows = db.scalars(
        select(JobModel)
        .where(
            (JobModel.job_type != SCHEDULED_MONITOR_JOB_TYPE)
            | (JobModel.requested_by != SCHEDULER_REQUESTED_BY)
        )
        .order_by(JobModel.created_at.desc())
        .limit(normalized_limit)
    ).all()
    return _merge_active_and_recent(
        [_row_to_schema(row) for row in active_rows],
        [_row_to_schema(row) for row in recent_rows],
    )


def _list_active_jobs_db(db: Session) -> list[Job]:
    rows = db.scalars(
        select(JobModel).where(JobModel.status.in_(ACTIVE_JOB_STATUSES)).order_by(JobModel.created_at.desc())
    ).all()
    return [_row_to_schema(row) for row in rows]


def _get_job_db(db: Session, job_id: str) -> Job | None:
    row = db.scalars(select(JobModel).where(JobModel.job_id == job_id)).first()
    return _row_to_schema(row) if row else None


def _update_job_db(db: Session, job_id: str, values: dict) -> Job | None:
    row = db.scalars(select(JobModel).where(JobModel.job_id == job_id)).first()
    if row is None:
        return None
    for key, value in values.items():
        model_key = "result_json" if key == "result" else key
        if hasattr(row, model_key):
            setattr(row, model_key, value)
    db.commit()
    db.refresh(row)
    return _row_to_schema(row)


def _active_job_exists_db(db: Session) -> bool:
    row = db.scalars(select(JobModel.id).where(JobModel.status.in_(ACTIVE_JOB_STATUSES))).first()
    return row is not None


def _reconcile_stale_jobs_db(db: Session) -> int:
    now = _utcnow()
    rows = db.scalars(select(JobModel).where(JobModel.status.in_(ACTIVE_JOB_STATUSES))).all()
    reconciled = 0
    for row in rows:
        reference = row.heartbeat_at or row.started_at or row.requested_at or row.created_at
        if reference is None or not _job_is_stale(row.status, reference, now):
            continue
        row.status = "failed"
        row.current_step = "Verwaisten Job beendet"
        row.message = "Der Job hatte keinen Worker-Heartbeat mehr und wurde automatisch freigegeben."
        row.error_message = (
            "Worker-Heartbeat abgelaufen. Der Prozess wurde vermutlich neu gestartet oder der Auftrag ging verloren."
        )
        row.finished_at = now
        row.heartbeat_at = now
        reconciled += 1
    if reconciled:
        db.commit()
    return reconciled


def _prune_terminal_job_history_db(
    db: Session,
    *,
    job_type: str,
    requested_by: str,
    keep: int,
) -> int:
    obsolete_ids = list(
        db.scalars(
            select(JobModel.id)
            .where(
                JobModel.job_type == job_type,
                JobModel.requested_by == requested_by,
                JobModel.status.in_(TERMINAL_JOB_STATUSES),
            )
            .order_by(JobModel.created_at.desc())
            .offset(keep)
        ).all()
    )
    if not obsolete_ids:
        return 0
    db.execute(delete(JobModel).where(JobModel.id.in_(obsolete_ids)))
    db.commit()
    return len(obsolete_ids)


def _store_memory(job: Job) -> Job:
    _MEMORY_JOBS[job.job_id] = job
    return job


def _list_jobs_memory(limit: int) -> list[Job]:
    normalized_limit = max(1, min(200, limit))
    jobs = sorted(_MEMORY_JOBS.values(), key=lambda job: job.created_at, reverse=True)
    active_jobs = [job for job in jobs if job.status in ACTIVE_JOB_STATUSES]
    recent_jobs = [
        job
        for job in jobs
        if not (
            job.job_type == SCHEDULED_MONITOR_JOB_TYPE
            and job.requested_by == SCHEDULER_REQUESTED_BY
        )
    ][:normalized_limit]
    return _merge_active_and_recent(active_jobs, recent_jobs)


def _list_active_jobs_memory() -> list[Job]:
    return sorted(
        (job for job in _MEMORY_JOBS.values() if job.status in ACTIVE_JOB_STATUSES),
        key=lambda job: job.created_at,
        reverse=True,
    )


def _merge_active_and_recent(active_jobs: list[Job], recent_jobs: list[Job]) -> list[Job]:
    merged: list[Job] = []
    seen: set[str] = set()
    for job in [*active_jobs, *recent_jobs]:
        if job.job_id in seen:
            continue
        merged.append(job)
        seen.add(job.job_id)
    return merged


def _update_job_memory(job_id: str, values: dict) -> Job | None:
    job = _MEMORY_JOBS.get(job_id)
    if job is None:
        return None
    patch = {}
    for key, value in values.items():
        schema_key = "result" if key == "result_json" else key
        patch[schema_key] = value
    updated = job.model_copy(update=patch)
    _MEMORY_JOBS[job_id] = updated
    return updated


def _active_job_exists_memory() -> bool:
    return any(job.status in ACTIVE_JOB_STATUSES for job in _MEMORY_JOBS.values())


def _reconcile_stale_jobs_memory() -> int:
    now = _utcnow()
    reconciled = 0
    for job_id, job in list(_MEMORY_JOBS.items()):
        if job.status not in ACTIVE_JOB_STATUSES:
            continue
        reference = job.heartbeat_at or job.started_at or job.requested_at or job.created_at
        if not _job_is_stale(job.status, reference, now):
            continue
        _MEMORY_JOBS[job_id] = job.model_copy(
            update={
                "status": "failed",
                "current_step": "Verwaisten Job beendet",
                "message": "Der Job hatte keinen Worker-Heartbeat mehr und wurde automatisch freigegeben.",
                "error_message": (
                    "Worker-Heartbeat abgelaufen. Der Prozess wurde vermutlich neu gestartet "
                    "oder der Auftrag ging verloren."
                ),
                "finished_at": now,
                "heartbeat_at": now,
            }
        )
        reconciled += 1
    return reconciled


def _prune_terminal_job_history_memory(*, job_type: str, requested_by: str, keep: int) -> int:
    matches = sorted(
        (
            job
            for job in _MEMORY_JOBS.values()
            if job.job_type == job_type
            and job.requested_by == requested_by
            and job.status in TERMINAL_JOB_STATUSES
        ),
        key=lambda job: job.created_at,
        reverse=True,
    )
    obsolete = matches[keep:]
    for job in obsolete:
        _MEMORY_JOBS.pop(job.job_id, None)
    return len(obsolete)


def _row_to_schema(row: JobModel) -> Job:
    return Job(
        job_id=row.job_id,
        celery_task_id=row.celery_task_id or "",
        job_type=row.job_type,
        status=row.status,
        progress=row.progress,
        current_step=row.current_step,
        message=row.message or "",
        error_message=row.error_message or "",
        requested_by=row.requested_by,
        payload=row.payload_json or {},
        created_at=row.created_at or row.requested_at or _utcnow(),
        requested_at=row.requested_at or row.created_at or _utcnow(),
        started_at=row.started_at,
        heartbeat_at=row.heartbeat_at or row.started_at or row.requested_at or row.created_at or _utcnow(),
        finished_at=row.finished_at,
        result=row.result_json or {},
    )


def _with_db(callback, fallback):
    try:
        with SessionLocal() as db:
            return callback(db)
    except SQLAlchemyError:
        return fallback()


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _job_is_stale(status: str, reference: datetime, now: datetime) -> bool:
    normalized_reference = reference if reference.tzinfo is not None else reference.replace(tzinfo=UTC)
    threshold = QUEUED_JOB_STALE_AFTER if status == "queued" else RUNNING_JOB_STALE_AFTER
    return normalized_reference < now - threshold
