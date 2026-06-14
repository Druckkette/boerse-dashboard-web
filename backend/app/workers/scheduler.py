from __future__ import annotations

from celery.schedules import crontab


def get_beat_schedule() -> dict:
    """Central Celery Beat schedule.

    NAS defaults are intentionally conservative. 13F refreshes run monthly because SEC
    artefacts are large and do not need frequent refreshes.
    """
    return {
        "smart-market-refresh-daily": {
            "task": "smart_refresh_market_data",
            "schedule": crontab(hour=22, minute=15),
            "args": (
                None,
                {
                    "mode": "scheduled",
                    "source": "scheduler",
                    "range": "6m",
                    "initial_range": "2y",
                    "universe": "us_common_stocks",
                    "limit_universe": 5000,
                    "breadth_lookback_days": 550,
                    "rs_lookback_days": 430,
                    "benchmark_ticker": "SPY",
                    "include_position_monitor": True,
                },
            ),
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
