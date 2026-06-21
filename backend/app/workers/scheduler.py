from __future__ import annotations

from celery.schedules import crontab


SMART_REFRESH_PAYLOAD = {
    "mode": "scheduled",
    "source": "scheduler",
    "range": "6m",
    "initial_range": "2y",
    "incremental_prices": True,
    "price_provider_timeout_seconds": 15,
    "price_action_max_seconds": 7200,
    "price_batch_size": 50,
    "price_overlap_days": 1,
    "universe": "us_common_stocks",
    "limit_universe": 5000,
    "breadth_lookback_days": 550,
    "rs_lookback_days": 430,
    "benchmark_ticker": "SPY",
    "include_position_monitor": True,
    "include_fundamentals": True,
    "include_sec13f": True,
    "fundamental_universe": "all",
    "fundamental_limit": 5000,
    "incremental_fundamentals": True,
    "fundamental_action_max_seconds": 2700,
    "sec13f_universe": "open_positions",
    "sec13f_limit_universe": 500,
    "sec13f_dataset_count": 2,
}


def get_beat_schedule() -> dict:
    """Central Celery Beat schedule.

    NAS defaults are intentionally conservative. 13F refreshes are freshness-gated
    in Smart Refresh and also run monthly as a backup because SEC artefacts are large.
    """
    return {
        "smart-market-refresh-afternoon": {
            "task": "smart_refresh_market_data",
            "schedule": crontab(hour=16, minute=0),
            "args": (None, {**SMART_REFRESH_PAYLOAD, "scheduled_window": "afternoon"}),
        },
        "smart-market-refresh-evening": {
            "task": "smart_refresh_market_data",
            "schedule": crontab(hour=22, minute=30),
            "args": (None, {**SMART_REFRESH_PAYLOAD, "scheduled_window": "evening"}),
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
