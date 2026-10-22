"""Scheduled checks share durable state with the alarm centre."""

import logging
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from app.repositories import desk as repository
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="check_workspace_alerts")
def check_workspace_alerts():
    from app.services.desk import evaluate_alerts
    from app.core_config import get_settings as runtime_settings
    from app.services.settings import (
        get_app_settings,
        get_runtime_config_bool,
        get_runtime_config_value,
    )
    from app.workers.tasks.pushover_test import _send_pushover_message

    try:
        checked = evaluate_alerts()
    except repository.DeskConflict:
        return {"status": "deferred", "reason": "Arbeitsbereich wurde geändert"}
    if not any(entry.get("push_status") == "pending" for entry in checked["history"]):
        return {"status": "checked", "deliveries": 0}
    settings = runtime_settings()
    # Only explicit opt-in rules send; existing global notification settings apply.
    allowed = get_app_settings().pushover_enabled
    dry_run = get_runtime_config_bool("PUSHOVER_DRY_RUN", settings.pushover_dry_run)
    token = get_runtime_config_value("PUSHOVER_APP_TOKEN") or settings.pushover_app_token
    user = get_runtime_config_value("PUSHOVER_USER_KEY") or settings.pushover_user_key
    pending = []

    def claim(value):
        from app.domain.desk import in_quiet_hours

        for entry in value["history"]:
            if entry.get("push_status") == "pending":
                rule = next((r for r in value["alerts"] if r["id"] == entry["rule_id"]), None)
                # Do not transmit queued messages after a rule was disabled or acknowledged.
                if (
                    not allowed
                    or dry_run
                    or not token
                    or not user
                    or not rule
                    or not rule["enabled"]
                    or not rule["push"]
                    or entry.get("acknowledged_at")
                ):
                    entry["push_status"] = "skipped"
                elif in_quiet_hours(
                    datetime.now(ZoneInfo("Europe/Berlin")), rule["quiet_start"], rule["quiet_end"]
                ):
                    continue
                elif len(pending) < 5:
                    entry["push_status"] = "sending"
                    pending.append(dict(entry))

    repository.transact(claim)
    for entry in pending:
        status = "failed"
        try:
            response = _send_pushover_message(
                user_key=user,
                app_token=token,
                title=entry["name"],
                message=f"{entry['ticker']} · {entry['detail']} · Stand {entry['as_of']}",
                priority=0,
            )
            status = "sent" if int(response.get("status", 0)) == 1 else "failed"
        except Exception:
            logger.exception("Workspace notification failed: %s", entry["id"])

        def finish(value):
            row = next((r for r in value["history"] if r["id"] == entry["id"]), None)
            if row:
                row.update(push_status=status, delivery_checked_at=datetime.now(UTC).isoformat())

        repository.transact(finish)
    return {"status": "checked", "deliveries": len(pending)}
