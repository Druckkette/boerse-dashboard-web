from __future__ import annotations

from app.workers.celery_app import celery_app
from app.workers.scheduler import get_beat_schedule


def test_celery_beat_uses_german_market_update_timezone() -> None:
    assert celery_app.conf.timezone == "Europe/Berlin"


def test_smart_market_refresh_runs_afternoon_and_evening() -> None:
    schedule = get_beat_schedule()

    afternoon = schedule["smart-market-refresh-afternoon"]
    evening = schedule["smart-market-refresh-evening"]

    assert afternoon["task"] == "smart_refresh_market_data"
    assert afternoon["schedule"]._orig_hour == 16
    assert afternoon["schedule"]._orig_minute == 0
    assert afternoon["args"][1]["scheduled_window"] == "afternoon"
    assert afternoon["args"][1]["mode"] == "scheduled"
    assert afternoon["args"][1]["source"] == "scheduler"

    assert evening["task"] == "smart_refresh_market_data"
    assert evening["schedule"]._orig_hour == 22
    assert evening["schedule"]._orig_minute == 30
    assert evening["args"][1]["scheduled_window"] == "evening"
    assert evening["args"][1]["mode"] == "scheduled"
    assert evening["args"][1]["source"] == "scheduler"
