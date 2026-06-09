from __future__ import annotations

from app.workers.celery_app import celery_app
from app.workers.tasks.common import run_skeleton_job


@celery_app.task(bind=True, name="refresh_relative_strength")
def refresh_relative_strength(self, job_id: str | None = None, payload: dict | None = None) -> dict:
    return run_skeleton_job(
        job_type="refresh_relative_strength",
        job_id=job_id,
        payload=payload,
        steps=[
            (15, "RS-Universum laden", {"records_seen": 0}),
            (45, "Benchmark-Returns vorbereiten", {"records_seen": 420}),
            (75, "RS-Ratings sortieren", {"records_written": 420}),
            (95, "Ranking-Snapshot aktualisieren", {"coverage": 0.82}),
        ],
    )
