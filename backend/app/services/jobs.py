from __future__ import annotations

from celery.exceptions import CeleryError
from kombu.exceptions import KombuError

from app.repositories import jobs as job_repository
from app.schemas import Job, JobCreateRequest
from app.workers.celery_app import celery_app


class JobConflictError(RuntimeError):
    pass


LIGHTWEIGHT_JOB_QUEUES = {
    "position_atr_monitor": "monitor",
    "pushover_test": "monitor",
}
JOB_LIST_MAX_RESULT_ITEMS = 5
JOB_LIST_MAX_RESULT_STRING_LENGTH = 500
JOB_LIST_MAX_RESULT_DEPTH = 4
JOB_LIST_PRESERVED_LIST_KEYS = {"failed_tickers", "items", "tickers"}


def list_jobs(limit: int = 50) -> list[Job]:
    return [_job_list_summary(job) for job in job_repository.list_jobs(limit=limit)]


def _job_list_summary(job: Job) -> Job:
    compacted, truncated = _compact_result_value(job.result, preserve_list=True)
    result = compacted if isinstance(compacted, dict) else {}
    if truncated:
        result = {
            **result,
            "_summary": "Große Ergebnislisten wurden für die Übersicht gekürzt. Vollständige Details beim Aufklappen laden.",
        }
    return job.model_copy(update={"result": result})


def _compact_result_value(
    value: object,
    *,
    depth: int = 0,
    preserve_list: bool = False,
) -> tuple[object, bool]:
    if depth >= JOB_LIST_MAX_RESULT_DEPTH:
        return "Weitere verschachtelte Details gekürzt.", True
    if isinstance(value, dict):
        result: dict[str, object] = {}
        truncated = False
        for key, item in value.items():
            normalized_key = str(key)
            if isinstance(item, list) and normalized_key not in JOB_LIST_PRESERVED_LIST_KEYS:
                result[f"{normalized_key}_count"] = len(item)
                truncated = True
                continue
            compacted, item_truncated = _compact_result_value(
                item,
                depth=depth + 1,
                preserve_list=normalized_key in JOB_LIST_PRESERVED_LIST_KEYS,
            )
            result[normalized_key] = compacted
            truncated = truncated or item_truncated
        return result, truncated
    if isinstance(value, list):
        if not preserve_list:
            return {"count": len(value)}, bool(value)
        selected = value[:JOB_LIST_MAX_RESULT_ITEMS]
        result = []
        truncated = len(value) > len(selected)
        for item in selected:
            compacted, item_truncated = _compact_result_value(
                item,
                depth=depth + 1,
                preserve_list=True,
            )
            result.append(compacted)
            truncated = truncated or item_truncated
        return result, truncated
    if isinstance(value, str) and len(value) > JOB_LIST_MAX_RESULT_STRING_LENGTH:
        return value[:JOB_LIST_MAX_RESULT_STRING_LENGTH] + "...", True
    return value, False


def get_job(job_id: str) -> Job | None:
    return job_repository.get_job(job_id)


def start_job(payload: JobCreateRequest) -> Job:
    job_type = str(payload.type)
    active_heavy_jobs = [
        job
        for job in job_repository.list_active_jobs()
        if str(job.job_type) not in LIGHTWEIGHT_JOB_QUEUES
    ]
    if job_type not in LIGHTWEIGHT_JOB_QUEUES and active_heavy_jobs:
        raise JobConflictError("Ein Job läuft bereits. Auf der NAS ist parallele Schwerarbeit gesperrt.")

    job = job_repository.create_job(payload.type, payload.payload, requested_by=payload.requested_by)
    try:
        async_result = celery_app.send_task(
            job_type,
            args=[job.job_id, payload.payload],
            queue=LIGHTWEIGHT_JOB_QUEUES.get(job_type, "default"),
            ignore_result=True,
            expires=job_repository.QUEUED_JOB_EXPIRES_SECONDS,
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
            celery_app.control.revoke(job.celery_task_id, terminate=True, signal="SIGTERM")
        except (CeleryError, KombuError, OSError):
            pass

    cancelled = job_repository.mark_cancelled(job_id)
    return cancelled or job, True
