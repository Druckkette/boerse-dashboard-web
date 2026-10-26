from app.repositories import jobs
from app.services.chart_analysis import scan_universe
from app.workers.celery_app import celery_app
from app.workers.tasks.common import JobCancelled, raise_if_cancelled


@celery_app.task(bind=True, name="scan_chart_patterns", soft_time_limit=7100, time_limit=7200)
def scan_chart_patterns(self, job_id: str, payload: dict | None = None) -> dict:
    jobs.mark_running(job_id, step="Basismuster prüfen")
    try:

        def progress(done, total, phase="analysis"):
            phases = {
                "quality": (
                    0,
                    10,
                    "Kursqualität prüfen",
                    "Auffällige Kursreihen werden für gezieltes Nachladen ausgewählt.",
                ),
                "repair": (
                    10,
                    10,
                    "Problemdaten nachladen",
                    "Vollständige Kursbasis und Splitereignisse werden geprüft.",
                ),
                "analysis": (
                    20,
                    75,
                    "Aktien analysieren",
                    "Saubere Kursabschnitte werden einzeln nach Kapitel 4.2 analysiert.",
                ),
            }
            begin, span, label, message = phases[phase]
            jobs.update_progress(
                job_id,
                progress=begin + int(span * done / max(1, total)),
                step=f"{label}: {done} / {total}",
                message=message,
            )

        options = payload or {}
        result = scan_universe(
            progress=progress,
            cancelled=lambda: raise_if_cancelled(job_id),
            repair_prices=options.get("repair_prices", True),
            repair_limit=options.get("repair_limit", 100),
            repair_seconds=options.get("repair_seconds", 300),
        )
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
