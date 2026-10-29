"""Deliver durable grouped alerts and summaries without fetching market data."""
from app.services.settings import get_app_settings
from app.services.notification_delivery import flush_notifications
from app.workers.celery_app import celery_app


@celery_app.task(name="flush_position_notifications", soft_time_limit=45, time_limit=50, ignore_result=True)
def flush_position_notifications() -> dict:
    settings = get_app_settings()
    if not settings.position_monitor_enabled or not settings.pushover_enabled:
        return {"skipped": True, "reason": "Benachrichtigungen sind deaktiviert."}
    return flush_notifications(app_settings=settings)
