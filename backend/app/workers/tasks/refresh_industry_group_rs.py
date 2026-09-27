from __future__ import annotations

from app.repositories import jobs as job_repository
from app.services.industry_group_rs import refresh_industry_group_rs
from app.workers.celery_app import celery_app
from app.workers.tasks.common import JobCancelled, raise_if_cancelled


@celery_app.task(bind=True, name="refresh_industry_group_rs", soft_time_limit=3600, time_limit=3660)
def refresh_industry_group_rs_task(self, job_id: str | None = None, payload: dict | None = None) -> dict:
    payload = payload or {}
    job = job_repository.get_job(job_id) if job_id else None
    if job is None:
        job = job_repository.create_job(
            "refresh_industry_group_rs",
            payload,
            requested_by=str(payload.get("source") or "scheduler"),
        )
    job_repository.mark_running(job.job_id, step="Industry Group RS vorbereiten")
    try:
        raise_if_cancelled(job.job_id)
        job_repository.update_progress(
            job.job_id,
            progress=10,
            step="Gruppen und Kursdaten laden",
            message="Industry-Group-Mitglieder, Price Cache und Benchmark werden geladen.",
        )
        result = refresh_industry_group_rs(
            benchmark_ticker=str(payload.get("benchmark_ticker") or "SPY"),
            backfill_sessions=(
                int(payload["backfill_sessions"])
                if payload.get("backfill_sessions") is not None
                else None
            ),
        )
        raise_if_cancelled(job.job_id)
        job_repository.mark_done(
            job.job_id,
            result=result,
            message=(
                f"{result.get('groups_ranked', 0)} Industry Groups gerankt; "
                f"{result.get('small_groups', 0)} kleine Vergleichsgruppen."
            ),
        )
        return result
    except JobCancelled:
        job_repository.mark_cancelled(job.job_id)
        return {"ok": False, "cancelled": True, "job_type": "refresh_industry_group_rs"}
    except Exception as exc:
        job_repository.mark_failed(
            job.job_id,
            error_message=f"{type(exc).__name__}: {exc}",
            result={"ok": False, "job_type": "refresh_industry_group_rs"},
        )
        raise
