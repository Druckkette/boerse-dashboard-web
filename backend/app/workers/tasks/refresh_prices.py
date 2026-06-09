from __future__ import annotations

from app.workers.celery_app import celery_app
from app.workers.tasks.common import run_skeleton_job


@celery_app.task(bind=True, name="refresh_prices")
def refresh_prices(self, job_id: str | None = None, payload: dict | None = None) -> dict:
    return run_skeleton_job(
        job_type="refresh_prices",
        job_id=job_id,
        payload=payload,
        steps=[
            (15, "Instrumente aus Cache laden", {"records_seen": 0}),
            (40, "Inkrementelle Kursfenster bestimmen", {"records_seen": 128}),
            (70, "OHLC-Bars validieren", {"records_written": 512}),
            (95, "Price-Cache-Freshness aktualisieren", {"coverage": 0.86}),
        ],
    )
