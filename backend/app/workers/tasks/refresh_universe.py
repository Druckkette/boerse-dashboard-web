from __future__ import annotations

from app.repositories import jobs as job_repository
from app.services.universes import refresh_us_common_stock_universe
from app.workers.celery_app import celery_app
from app.workers.tasks.common import JobCancelled, raise_if_cancelled


@celery_app.task(bind=True, name="refresh_universe")
def refresh_universe(self, job_id: str | None = None, payload: dict | None = None) -> dict:
    payload = payload or {}
    job = job_repository.get_job(job_id) if job_id else None
    if job is None:
        job = job_repository.create_job("refresh_universe", payload, requested_by=str(payload.get("source") or "api"))

    job_repository.mark_running(job.job_id, step="Universe Refresh startet")
    try:
        raise_if_cancelled(job.job_id)
        job_repository.update_progress(
            job.job_id,
            progress=25,
            step="Nasdaq Trader laden",
            message="nasdaqlisted.txt und otherlisted.txt werden im Worker geladen.",
            result={"job_type": "refresh_universe"},
        )
        result = refresh_us_common_stock_universe()
        raise_if_cancelled(job.job_id)
        job_repository.update_progress(
            job.job_id,
            progress=90,
            step="Universe speichern",
            message=f"{result.get('member_count', 0)} Ticker gespeichert.",
            result=result,
        )
        job_repository.mark_done(job.job_id, result=result, message="Aktienuniversum aktualisiert.")
        return result
    except JobCancelled:
        job_repository.mark_cancelled(job.job_id)
        return {"ok": False, "cancelled": True, "job_type": "refresh_universe"}
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        job_repository.mark_failed(job.job_id, error_message=error, result={"ok": False, "job_type": "refresh_universe"})
        raise
