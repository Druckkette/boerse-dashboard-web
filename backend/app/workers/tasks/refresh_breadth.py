from __future__ import annotations

from app.workers.celery_app import celery_app
from app.workers.tasks.common import run_skeleton_job


@celery_app.task(bind=True, name="refresh_breadth")
def refresh_breadth(self, job_id: str | None = None, payload: dict | None = None) -> dict:
    return run_skeleton_job(
        job_type="refresh_breadth",
        job_id=job_id,
        payload=payload,
        steps=[
            (20, "Universum laden", {"records_seen": 620}),
            (45, "Breadth-Indikatoren berechnen", {"records_seen": 620}),
            (75, "MarketSnapshot vorbereiten", {"records_written": 1}),
            (95, "BreadthDaily schreiben", {"records_written": 2}),
        ],
    )
