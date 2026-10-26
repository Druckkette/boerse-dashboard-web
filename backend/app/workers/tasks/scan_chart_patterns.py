from app.repositories import jobs
from app.services.chart_analysis import scan_universe
from app.workers.celery_app import celery_app
from app.workers.tasks.common import JobCancelled, raise_if_cancelled


@celery_app.task(bind=True, name="scan_chart_patterns", soft_time_limit=3500, time_limit=3600)
def scan_chart_patterns(self, job_id: str, payload: dict | None = None) -> dict:
    jobs.mark_running(job_id, step="Basismuster prüfen")
    try:

        def progress(done, total):
            jobs.update_progress(
                job_id,
                progress=int(95 * done / max(1, total)),
                step=f"{done} / {total} Aktien geprüft",
                message="Gespeicherte Tageskurse werden nach Kapitel 4.2 analysiert.",
            )

        result = scan_universe(progress=progress, cancelled=lambda: raise_if_cancelled(job_id))
        jobs.mark_done(
            job_id, result=result, message=f"{result['records_written']} Basismuster erkannt."
        )
        return result
    except JobCancelled:
        jobs.mark_cancelled(job_id)
        return {"ok": False, "cancelled": True}
    except Exception as exc:
        jobs.mark_failed(job_id, error_message=f"{type(exc).__name__}: {exc}")
        raise
