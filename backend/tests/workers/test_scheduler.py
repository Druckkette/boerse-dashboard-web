from __future__ import annotations

from app.workers.celery_app import celery_app
from app.workers.scheduler import get_beat_schedule


def test_celery_beat_uses_german_market_update_timezone() -> None:
    assert celery_app.conf.timezone == "Europe/Berlin"


def test_smart_market_refresh_runs_morning_and_evening() -> None:
    schedule = get_beat_schedule()

    morning = schedule["smart-market-refresh-morning"]
    evening = schedule["smart-market-refresh-evening"]

    assert morning["task"] == "smart_refresh_market_data"
    assert morning["schedule"]._orig_hour == 7
    assert morning["schedule"]._orig_minute == 45
    assert morning["args"][1]["scheduled_window"] == "morning"
    assert morning["args"][1]["mode"] == "scheduled"
    assert morning["args"][1]["source"] == "scheduler"

    assert evening["task"] == "smart_refresh_market_data"
    assert evening["schedule"]._orig_hour == 22
    assert evening["schedule"]._orig_minute == 30
    assert evening["args"][1]["scheduled_window"] == "evening"
    assert evening["args"][1]["mode"] == "scheduled"
    assert evening["args"][1]["source"] == "scheduler"
