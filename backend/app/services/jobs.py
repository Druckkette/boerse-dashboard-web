from __future__ import annotations

from celery.exceptions import CeleryError
from kombu.exceptions import KombuError

from app.repositories import jobs as job_repository
from app.schemas import Job, JobCreateRequest
from app.workers.celery_app import celery_app


class JobConflictError(RuntimeError):
    pass


def list_jobs(limit: int = 50) -> list[Job]:
    return job_repository.list_jobs(limit=limit)


def get_job(job_id: str) -> Job | None:
    return job_repository.get_job(job_id)


def start_job(payload: JobCreateRequest) -> Job:
    if job_repository.active_job_exists():
        raise JobConflictError("Ein Job läuft bereits. Auf der NAS ist parallele Schwerarbeit gesperrt.")

    job = job_repository.create_job(payload.type, payload.payload, requested_by=payload.requested_by)
    try:
        async_result = celery_app.send_task(
            str(payload.type),
            args=[job.job_id, payload.payload],
            queue="default",
            ignore_result=True,
        )
    except (CeleryError, KombuError, OSError, RuntimeError) as exc:
        failed = job_repository.mark_failed(
            job.job_id,
            error_message=f"Job konnte nicht an Redis/Celery übergeben werden: {exc}",
        )
        return failed or job

    updated = job_repository.set_celery_task_id(job.job_id, async_result.id)
    return updated or job


def cancel_job(job_id: str) -> tuple[Job | None, bool]:
    job = job_repository.get_job(job_id)
    if job is None:
        return None, False
    if job.status in job_repository.TERMINAL_JOB_STATUSES:
        return job, False

    if job.celery_task_id:
        try:
            celery_app.control.revoke(job.celery_task_id, terminate=False)
        except (CeleryError, KombuError, OSError):
            pass

    cancelled = job_repository.mark_cancelled(job_id)
    return cancelled or job, True
