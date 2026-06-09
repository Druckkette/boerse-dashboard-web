from __future__ import annotations

from app.workers.celery_app import celery_app
from app.workers.tasks.common import run_skeleton_job


@celery_app.task(bind=True, name="position_atr_monitor")
def position_atr_monitor(self, job_id: str | None = None, payload: dict | None = None) -> dict:
    return run_skeleton_job(
        job_type="position_atr_monitor",
        job_id=job_id,
        payload=payload,
        steps=[
            (20, "Offene Positionen laden", {"records_seen": 4}),
            (45, "ATR-Abstände prüfen", {"records_seen": 4}),
            (70, "Sell-Recommendation-State vorbereiten", {"records_written": 0}),
            (95, "Monitoring-Snapshot aktualisieren", {"records_written": 1}),
        ],
    )
