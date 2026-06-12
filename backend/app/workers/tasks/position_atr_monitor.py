from __future__ import annotations

from app.domain.sell.service import monitor_open_positions
from app.repositories import jobs as job_repository
from app.services.settings import get_app_settings
from app.workers.celery_app import celery_app
from app.workers.tasks.common import JobCancelled, raise_if_cancelled


@celery_app.task(bind=True, name="position_atr_monitor")
def position_atr_monitor(self, job_id: str | None = None, payload: dict | None = None) -> dict:
    payload = payload or {}
    job = job_repository.get_job(job_id) if job_id else None
    if job is None:
        job = job_repository.create_job(
            "position_atr_monitor",
            payload,
            requested_by=str(payload.get("source") or "scheduler"),
        )

    tickers = _normalize_tickers(payload.get("tickers"))
    job_repository.mark_running(job.job_id, step="Positionsmonitor startet")
    try:
        settings = get_app_settings()
        monitor_settings = settings.model_dump()
        payload_settings = payload.get("monitor_settings")
        if isinstance(payload_settings, dict):
            monitor_settings.update(payload_settings)

        requested_by = str(payload.get("source") or job.requested_by or "").lower()
        is_scheduler_run = requested_by == "scheduler"
        if is_scheduler_run and not settings.position_monitor_enabled and not payload.get("force"):
            result = {
                "ok": False,
                "skipped": True,
                "reason": "Positionsmonitor ist in den Settings deaktiviert.",
                "job_type": "position_atr_monitor",
                "records_seen": 0,
                "records_written": 0,
            }
            job_repository.mark_skipped(job.job_id, message=result["reason"], result=result)
            return result

        raise_if_cancelled(job.job_id)
        job_repository.update_progress(
            job.job_id,
            progress=20,
            step="Offene Positionen laden",
            message="Importierte offene Positionen werden aus Postgres gelesen.",
            result={"job_type": "position_atr_monitor", "tickers": tickers},
        )
        raise_if_cancelled(job.job_id)
        job_repository.update_progress(
            job.job_id,
            progress=55,
            step="Sell-Engine ausführen",
            message="ATR, Health Score und Verkaufssignale werden aus dem Price Cache berechnet.",
        )
        result = monitor_open_positions(tickers=tickers or None, monitor_settings=monitor_settings)
        if result.get("skipped"):
            job_repository.mark_skipped(job.job_id, message=str(result.get("reason") or "Keine Positionen."), result=result)
            return result

        raise_if_cancelled(job.job_id)
        job_repository.update_progress(
            job.job_id,
            progress=90,
            step="Recommendation-State schreiben",
            message=f"{result.get('records_written', 0)} Positionen aktualisiert.",
            result=result,
        )
        job_repository.mark_done(job.job_id, result=result, message="Positionsmonitor aktualisiert.")
        return result
    except JobCancelled:
        job_repository.mark_cancelled(job.job_id)
        return {"ok": False, "cancelled": True, "job_type": "position_atr_monitor"}
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        job_repository.mark_failed(job.job_id, error_message=error, result={"ok": False, "job_type": "position_atr_monitor"})
        raise


def _normalize_tickers(value: object) -> list[str]:
    if isinstance(value, str):
        raw = value.replace(";", ",").split(",")
    elif isinstance(value, list):
        raw = [str(item) for item in value]
    else:
        raw = []
    return list(dict.fromkeys(item.strip().upper() for item in raw if item and item.strip()))[:80]
