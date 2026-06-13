from __future__ import annotations

from celery import Celery

from app.core_config import get_settings
from app.workers.scheduler import get_beat_schedule


settings = get_settings()
broker_url = settings.celery_broker_url or settings.redis_url
result_backend = settings.celery_result_backend or settings.redis_url

celery_app = Celery("boerse_dashboard_web", broker=broker_url, backend=result_backend)
celery_app.conf.update(
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    worker_disable_rate_limits=settings.worker_disable_rate_limits,
    task_time_limit=6 * 60 * 60,
    task_soft_time_limit=5 * 60 * 60 + 45 * 60,
    result_expires=60 * 60 * 24,
    broker_connection_retry_on_startup=True,
    task_default_queue="default",
    imports=(
        "app.workers.tasks.bootstrap_market_data",
        "app.workers.tasks.refresh_prices",
        "app.workers.tasks.refresh_breadth",
        "app.workers.tasks.refresh_relative_strength",
        "app.workers.tasks.refresh_fundamentals",
        "app.workers.tasks.refresh_universe",
        "app.workers.tasks.refresh_sec13f",
        "app.workers.tasks.position_atr_monitor",
        "app.workers.tasks.pushover_test",
        "app.workers.tasks.yahoo_symbol_diagnostics",
    ),
)

if settings.scheduler_enabled:
    celery_app.conf.beat_schedule = get_beat_schedule()
