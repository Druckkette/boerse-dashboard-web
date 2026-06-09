from __future__ import annotations

from app.workers.celery_app import celery_app
from app.workers.tasks.common import run_skeleton_job


@celery_app.task(bind=True, name="refresh_sec13f")
def refresh_sec13f(self, job_id: str | None = None, payload: dict | None = None) -> dict:
    return run_skeleton_job(
        job_type="refresh_sec13f",
        job_id=job_id,
        payload=payload,
        steps=[
            (10, "SEC-Index inkrementell prüfen", {"records_seen": 0}),
            (35, "Neue 13F-Filings vormerken", {"records_seen": 24}),
            (65, "CUSIP-Mappings vorbereiten", {"records_written": 12}),
            (90, "Institutional-Trends speichern", {"records_written": 48}),
        ],
    )
