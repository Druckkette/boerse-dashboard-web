from __future__ import annotations

from app.repositories import jobs as job_repository
from app.services.industry_groups import rebuild_industry_groups, refresh_industry_group_memberships
from app.workers.celery_app import celery_app
from app.workers.tasks.common import JobCancelled, raise_if_cancelled


def _run(job_type: str, fn, job_id: str | None, payload: dict | None) -> dict:
    payload = payload or {}
    job = job_repository.get_job(job_id) if job_id else None
    if job is None:
        job = job_repository.create_job(job_type, payload, requested_by=str(payload.get("source") or "api"))
    job_repository.mark_running(job.job_id, step="Industry Groups starten")
    try:
        raise_if_cancelled(job.job_id)
        job_repository.update_progress(
            job.job_id,
            progress=10,
            step="Universe und Stammdaten laden",
            message="Persistierte Instrument-, Industry- und SIC-Metadaten werden geladen.",
            result={"job_type": job_type},
        )
        result = fn(str(payload.get("universe") or "us_common_stocks"))
        raise_if_cancelled(job.job_id)
        job_repository.update_progress(
            job.job_id,
            progress=95,
            step="Klassifikation persistiert",
            message=f"{result.get('classified', 0)} Aktien klassifiziert, {result.get('needs_review', 0)} zur Prüfung.",
            result=result,
        )
        job_repository.mark_done(job.job_id, result=result, message="Industry-Group-Klassifikation abgeschlossen.")
        return result
    except JobCancelled:
        job_repository.mark_cancelled(job.job_id)
        return {"ok": False, "cancelled": True, "job_type": job_type}
    except Exception as exc:
        job_repository.mark_failed(
            job.job_id,
            error_message=f"{type(exc).__name__}: {exc}",
            result={"ok": False, "job_type": job_type},
        )
        raise


@celery_app.task(bind=True, name="rebuild_industry_groups")
def rebuild_industry_groups_task(self, job_id: str | None = None, payload: dict | None = None) -> dict:
    return _run("rebuild_industry_groups", rebuild_industry_groups, job_id, payload)


@celery_app.task(bind=True, name="refresh_industry_group_memberships")
def refresh_industry_group_memberships_task(self, job_id: str | None = None, payload: dict | None = None) -> dict:
    return _run("refresh_industry_group_memberships", refresh_industry_group_memberships, job_id, payload)
