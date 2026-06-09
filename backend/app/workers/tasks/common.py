from __future__ import annotations

import time
from collections.abc import Iterable
from typing import Any

from app.repositories import jobs as job_repository


class JobCancelled(RuntimeError):
    pass


def run_skeleton_job(
    *,
    job_type: str,
    job_id: str | None,
    payload: dict | None,
    steps: Iterable[tuple[int, str, dict[str, Any]]],
) -> dict[str, Any]:
    payload = payload or {}
    job = job_repository.get_job(job_id) if job_id else None
    if job is None:
        job = job_repository.create_job(job_type, payload, requested_by=str(payload.get("source") or "scheduler"))

    job_repository.mark_running(job.job_id, step="Worker startet")
    result: dict[str, Any] = {"job_type": job_type, "mode": payload.get("mode", "manual")}

    try:
        if payload.get("fail"):
            raise RuntimeError("Skeleton job wurde per Payload fail=true absichtlich beendet.")

        for progress, step, partial_result in steps:
            _raise_if_cancelled(job.job_id)
            job_repository.update_progress(
                job.job_id,
                progress=progress,
                step=step,
                message=step,
                result={**result, **partial_result},
            )
            result.update(partial_result)
            time.sleep(float(payload.get("step_sleep_seconds", 0.15)))

        _raise_if_cancelled(job.job_id)
        final_result = {
            **result,
            "ok": True,
            "source": payload.get("source", "api"),
            "records_seen": int(result.get("records_seen", 0)),
            "records_written": int(result.get("records_written", 0)),
        }
        job_repository.mark_done(job.job_id, result=final_result)
        return final_result
    except JobCancelled:
        job_repository.mark_cancelled(job.job_id)
        return {"ok": False, "cancelled": True, "job_type": job_type}
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        job_repository.mark_failed(job.job_id, error_message=error, result={**result, "ok": False})
        raise


def _raise_if_cancelled(job_id: str) -> None:
    if job_repository.is_cancelled(job_id):
        raise JobCancelled(f"Job {job_id} wurde abgebrochen.")


def raise_if_cancelled(job_id: str) -> None:
    _raise_if_cancelled(job_id)
