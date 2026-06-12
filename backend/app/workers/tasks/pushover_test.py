from __future__ import annotations

import json
import urllib.parse
import urllib.request
from datetime import UTC, datetime

from app.core_config import get_settings
from app.repositories import jobs as job_repository
from app.workers.celery_app import celery_app
from app.workers.tasks.common import JobCancelled, raise_if_cancelled


PUSHOVER_API_URL = "https://api.pushover.net/1/messages.json"


@celery_app.task(bind=True, name="pushover_test")
def pushover_test(self, job_id: str | None = None, payload: dict | None = None) -> dict:
    payload = payload or {}
    job = job_repository.get_job(job_id) if job_id else None
    if job is None:
        job = job_repository.create_job("pushover_test", payload, requested_by=str(payload.get("source") or "api"))

    job_repository.mark_running(job.job_id, step="Pushover-Konfiguration prüfen")
    try:
        raise_if_cancelled(job.job_id)
        settings = get_settings()
        configured = bool(settings.pushover_user_key and settings.pushover_app_token)
        dry_run = bool(payload.get("dry_run") or settings.pushover_dry_run)
        result = {
            "ok": False,
            "job_type": "pushover_test",
            "configured": configured,
            "dry_run": dry_run,
            "sent": False,
        }
        if not configured:
            result["reason"] = "PUSHOVER_USER_KEY oder PUSHOVER_APP_TOKEN fehlt."
            job_repository.mark_skipped(job.job_id, message=result["reason"], result=result)
            return result

        job_repository.update_progress(
            job.job_id,
            progress=45,
            step="Testnachricht vorbereiten",
            message="Pushover-Secrets sind gesetzt.",
            result=result,
        )
        raise_if_cancelled(job.job_id)
        if dry_run:
            result.update(ok=True, sent=False, message="Dry Run aktiv, keine Nachricht gesendet.")
            job_repository.mark_done(job.job_id, result=result, message=result["message"])
            return result

        response = _send_pushover_message(
            user_key=settings.pushover_user_key,
            app_token=settings.pushover_app_token,
            message=f"boerse-dashboard-web Pushover-Test {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S')} UTC",
        )
        result.update(ok=True, sent=True, response=response)
        job_repository.mark_done(job.job_id, result=result, message="Pushover-Test gesendet.")
        return result
    except JobCancelled:
        job_repository.mark_cancelled(job.job_id)
        return {"ok": False, "cancelled": True, "job_type": "pushover_test"}
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        job_repository.mark_failed(job.job_id, error_message=error, result={"ok": False, "job_type": "pushover_test"})
        raise


def _send_pushover_message(*, user_key: str, app_token: str, message: str) -> dict:
    data = urllib.parse.urlencode(
        {
            "token": app_token,
            "user": user_key,
            "title": "boerse-dashboard-web",
            "message": message,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        PUSHOVER_API_URL,
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=15) as response:  # noqa: S310
        body = response.read().decode("utf-8")
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return {"raw": body}
