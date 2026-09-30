from __future__ import annotations

from app.repositories import jobs as job_repository
from app.services.trade_journal_backfill import backfill_trade_journal_contexts as run_backfill
from app.workers.celery_app import celery_app
from app.workers.tasks.common import JobCancelled, raise_if_cancelled


@celery_app.task(
    bind=True,
    name="backfill_trade_journal_contexts",
    soft_time_limit=3500,
    time_limit=3600,
)
def backfill_trade_journal_contexts(self, job_id: str | None = None, payload: dict | None = None) -> dict:
    payload = payload or {}
    job = job_repository.get_job(job_id) if job_id else None
    if job is None:
        job = job_repository.create_job(
            "backfill_trade_journal_contexts",
            payload,
            requested_by=str(payload.get("source") or "api"),
        )
    job_repository.mark_running(job.job_id, step="Historische Kontexte vorbereiten")
    try:
        raise_if_cancelled(job.job_id)
        job_repository.update_progress(
            job.job_id,
            progress=10,
            step="Journal und Datenabdeckung lesen",
            message="Originalsnapshots bleiben unverändert; neue Kontexte werden versioniert ergänzt.",
        )
        result = run_backfill(
            entry_ids=[str(value) for value in payload.get("entry_ids", []) if value],
            limit=int(payload.get("limit") or 5000),
        )
        raise_if_cancelled(job.job_id)
        job_repository.mark_done(
            job.job_id,
            result=result,
            message=f"{result['versions_written']} Kontextversionen ergänzt, {result['unchanged']} unverändert.",
        )
        return result
    except JobCancelled:
        job_repository.mark_cancelled(job.job_id)
        return {"ok": False, "cancelled": True, "job_type": "backfill_trade_journal_contexts"}
    except Exception as exc:
        job_repository.mark_failed(
            job.job_id,
            error_message=f"{type(exc).__name__}: {exc}",
            result={"ok": False, "job_type": "backfill_trade_journal_contexts"},
        )
        raise
