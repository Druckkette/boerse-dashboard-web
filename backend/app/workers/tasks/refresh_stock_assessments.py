from __future__ import annotations

from app.repositories import jobs as job_repository
from app.services.stocks import refresh_stock_assessment_snapshots
from app.workers.celery_app import celery_app
from app.workers.tasks.common import JobCancelled, raise_if_cancelled


@celery_app.task(bind=True, name="refresh_stock_assessments", soft_time_limit=1200, time_limit=1260)
def refresh_stock_assessments(self, job_id: str | None = None, payload: dict | None = None) -> dict:
    payload = payload or {}
    job = job_repository.get_job(job_id) if job_id else None
    if job is None:
        job = job_repository.create_job(
            "refresh_stock_assessments",
            payload,
            requested_by=str(payload.get("source") or "scheduler"),
        )
    limit = max(20, min(500, int(payload.get("limit") or 120)))
    job_repository.mark_running(job.job_id, step="Aktienranking vorbereiten")
    try:
        raise_if_cancelled(job.job_id)
        job_repository.update_progress(
            job.job_id,
            progress=15,
            step="Kandidaten laden",
            message=f"Die stärksten {limit} RS-Kandidaten werden im Worker bewertet.",
        )
        result = refresh_stock_assessment_snapshots(limit=limit, source_job_id=job.job_id)
        raise_if_cancelled(job.job_id)
        job_repository.mark_done(
            job.job_id,
            result=result,
            message=f"{result.get('records_written', 0)} Aktienbewertungen vorbereitet.",
        )
        return result
    except JobCancelled:
        job_repository.mark_cancelled(job.job_id)
        return {"ok": False, "cancelled": True, "job_type": "refresh_stock_assessments"}
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        job_repository.mark_failed(
            job.job_id,
            error_message=error,
            result={"ok": False, "job_type": "refresh_stock_assessments"},
        )
        raise
