from __future__ import annotations

from app.repositories import jobs as job_repository
from app.services.earnings import refresh_earnings_calendar as refresh_calendar
from app.services.settings import get_runtime_config_value
from app.workers.celery_app import celery_app
from app.workers.tasks.common import JobCancelled, raise_if_cancelled


@celery_app.task(bind=True, name="refresh_earnings_calendar")
def refresh_earnings_calendar(self, job_id: str | None = None, payload: dict | None = None) -> dict:
    payload = payload or {}
    job = job_repository.get_job(job_id) if job_id else None
    if job is None:
        job = job_repository.create_job(
            "refresh_earnings_calendar",
            payload,
            requested_by=str(payload.get("source") or "scheduler"),
        )
    job_repository.mark_running(job.job_id, step="Earnings-Kalender laden")
    try:
        raise_if_cancelled(job.job_id)
        api_key = get_runtime_config_value("FMP_API_KEY")
        result = refresh_calendar(api_key=api_key)
        job_repository.mark_done(
            job.job_id,
            result=result,
            message=f"Earnings-Kalender aktualisiert: {result['records_written']} Termine.",
        )
        return result
    except JobCancelled:
        job_repository.mark_cancelled(job.job_id)
        return {"ok": False, "cancelled": True}
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        job_repository.mark_failed(job.job_id, error_message=error, result={"ok": False})
        raise
