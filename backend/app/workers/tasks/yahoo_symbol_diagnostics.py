from __future__ import annotations

from app.repositories import jobs as job_repository
from app.services.universes import diagnose_yahoo_symbols
from app.workers.celery_app import celery_app
from app.workers.tasks.common import JobCancelled, raise_if_cancelled


@celery_app.task(bind=True, name="yahoo_symbol_diagnostics")
def yahoo_symbol_diagnostics(self, job_id: str | None = None, payload: dict | None = None) -> dict:
    return _run_yahoo_symbol_probe("yahoo_symbol_diagnostics", job_id, payload or {}, apply_mappings=False)


@celery_app.task(bind=True, name="yahoo_symbol_rescue")
def yahoo_symbol_rescue(self, job_id: str | None = None, payload: dict | None = None) -> dict:
    return _run_yahoo_symbol_probe("yahoo_symbol_rescue", job_id, payload or {}, apply_mappings=True)


def _run_yahoo_symbol_probe(
    job_type: str,
    job_id: str | None,
    payload: dict,
    *,
    apply_mappings: bool,
) -> dict:
    job = job_repository.get_job(job_id) if job_id else None
    if job is None:
        job = job_repository.create_job(job_type, payload, requested_by=str(payload.get("source") or "api"))

    job_repository.mark_running(job.job_id, step="Yahoo-Symbole werden geprüft")
    try:
        raise_if_cancelled(job.job_id)
        job_repository.update_progress(
            job.job_id,
            progress=20,
            step="Ticker-Stichprobe vorbereiten",
            message="Fehlende Universe-/Price-Ticker werden gegen yfinance geprüft.",
        )
        result = diagnose_yahoo_symbols(payload, apply_mappings=apply_mappings)
        raise_if_cancelled(job.job_id)
        message = "Yahoo-Diagnose abgeschlossen."
        if apply_mappings:
            message = f"Yahoo-Rescue abgeschlossen; {result.get('mapped_count', 0)} Mappings gespeichert."
        job_repository.mark_done(job.job_id, result=result, message=message)
        return result
    except JobCancelled:
        job_repository.mark_cancelled(job.job_id)
        return {"ok": False, "cancelled": True, "job_type": job_type}
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        job_repository.mark_failed(job.job_id, error_message=error, result={"ok": False, "job_type": job_type})
        raise
