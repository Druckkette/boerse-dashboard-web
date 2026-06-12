from __future__ import annotations

from celery.schedules import crontab


def get_beat_schedule() -> dict:
    """Central Celery Beat schedule.

    NAS defaults are intentionally conservative. 13F refreshes run monthly because SEC
    artefacts are large and do not need frequent refreshes.
    """
    return {
        "refresh-prices-daily": {
            "task": "refresh_prices",
            "schedule": crontab(hour=22, minute=15),
            "args": (None, {"mode": "incremental", "source": "scheduler"}),
        },
        "refresh-universe-weekly": {
            "task": "refresh_universe",
            "schedule": crontab(day_of_week="sun", hour=2, minute=15),
            "args": (None, {"mode": "weekly", "source": "scheduler"}),
        },
        "refresh-breadth-daily": {
            "task": "refresh_breadth",
            "schedule": crontab(hour=22, minute=45),
            "args": (None, {"mode": "incremental", "source": "scheduler"}),
        },
        "refresh-relative-strength-daily": {
            "task": "refresh_relative_strength",
            "schedule": crontab(hour=23, minute=10),
            "args": (None, {"mode": "incremental", "source": "scheduler"}),
        },
        "position-atr-monitor": {
            "task": "position_atr_monitor",
            "schedule": crontab(minute="*/15"),
            "args": (None, {"mode": "open_positions", "source": "scheduler"}),
        },
        "refresh-sec13f-monthly": {
            "task": "refresh_sec13f",
            "schedule": crontab(day_of_month=1, hour=3, minute=30),
            "args": (None, {"mode": "incremental", "source": "scheduler"}),
        },
    }
