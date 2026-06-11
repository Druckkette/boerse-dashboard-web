from __future__ import annotations

from app.repositories import jobs as job_repository
from app.services.sec13f import ingest_institutional_13f_payload
from app.workers.celery_app import celery_app
from app.workers.tasks.common import JobCancelled, raise_if_cancelled


@celery_app.task(bind=True, name="refresh_sec13f")
def refresh_sec13f(self, job_id: str | None = None, payload: dict | None = None) -> dict:
    payload = payload or {}
    job = job_repository.get_job(job_id) if job_id else None
    if job is None:
        job = job_repository.create_job("refresh_sec13f", payload, requested_by=str(payload.get("source") or "api"))

    job_repository.mark_running(job.job_id, step="13F Payload prüfen")
    try:
        raise_if_cancelled(job.job_id)
        if not isinstance(payload.get("tickers"), dict) and not _looks_like_ticker_payload(payload):
            result = {
                "ok": False,
                "skipped": True,
                "reason": "Kein 13F-Trendpayload übergeben. Erwartet altes JSON-Format mit Feld 'tickers'.",
                "job_type": "refresh_sec13f",
            }
            job_repository.mark_skipped(job.job_id, message=result["reason"], result=result)
            return result

        job_repository.update_progress(
            job.job_id,
            progress=35,
            step="13F-Trends normalisieren",
            message="Altes Streamlit-JSON-Format wird in Repository-Writes umgewandelt.",
        )
        raise_if_cancelled(job.job_id)
        result = ingest_institutional_13f_payload(payload)
        result["job_type"] = "refresh_sec13f"
        job_repository.update_progress(
            job.job_id,
            progress=90,
            step="13F-Trends speichern",
            message=f"{result.get('records_written', 0)} Trenddatensätze geschrieben.",
            result=result,
        )
        job_repository.mark_done(job.job_id, result=result, message="13F-Trends aktualisiert.")
        return result
    except JobCancelled:
        job_repository.mark_cancelled(job.job_id)
        return {"ok": False, "cancelled": True, "job_type": "refresh_sec13f"}
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        job_repository.mark_failed(job.job_id, error_message=error, result={"ok": False, "job_type": "refresh_sec13f"})
        raise


def _looks_like_ticker_payload(payload: dict) -> bool:
    return any(isinstance(value, dict) and "period" in value for value in payload.values())
