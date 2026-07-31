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
    assert afternoon["schedule"]._orig_day_of_week == "1-5"
    assert afternoon["args"][1]["scheduled_window"] == "afternoon"
    assert afternoon["args"][1]["mode"] == "scheduled"
    assert afternoon["args"][1]["source"] == "scheduler"
    assert afternoon["args"][1]["include_sec13f"] is True
    assert afternoon["args"][1]["sec13f_universe"] == "us_common_stocks"
    assert afternoon["args"][1]["limit_universe"] == 10000
    assert afternoon["args"][1]["sec13f_limit_universe"] == 10000
    assert afternoon["args"][1]["fundamental_limit"] == 10000
    assert afternoon["args"][1]["fundamental_max_refresh_count"] == 250
    assert afternoon["args"][1]["fundamental_freshness_days"] == 14
    assert afternoon["options"]["expires"] == 6 * 60 * 60

    assert evening["task"] == "smart_refresh_market_data"
    assert evening["schedule"]._orig_hour == 22
    assert evening["schedule"]._orig_minute == 30
    assert evening["schedule"]._orig_day_of_week == "1-5"
    assert evening["args"][1]["scheduled_window"] == "evening"
    assert evening["args"][1]["mode"] == "scheduled"
    assert evening["args"][1]["source"] == "scheduler"
    assert evening["args"][1]["include_sec13f"] is True
    assert evening["args"][1]["limit_universe"] == 10000
    assert evening["args"][1]["fundamental_limit"] == 10000
    assert evening["args"][1]["fundamental_max_refresh_count"] == 250
    assert evening["options"]["expires"] == 6 * 60 * 60

    earnings_afternoon = schedule["earnings-calendar-before-afternoon-refresh"]
    earnings_evening = schedule["earnings-calendar-before-evening-refresh"]
    assert earnings_afternoon["task"] == "refresh_earnings_calendar"
    assert earnings_afternoon["schedule"]._orig_hour == 15
    assert earnings_afternoon["schedule"]._orig_minute == 50
    assert earnings_evening["schedule"]._orig_hour == 22
    assert earnings_evening["schedule"]._orig_minute == 20

    afternoon_repair = schedule["smart-market-refresh-afternoon-repair"]
    evening_repair = schedule["smart-market-refresh-evening-repair"]
    assert afternoon_repair["args"][1]["mode"] == "repair"
    assert afternoon_repair["schedule"]._orig_hour == 18
    assert afternoon_repair["schedule"]._orig_minute == 45
    assert evening_repair["args"][1]["mode"] == "repair"
    assert evening_repair["schedule"]._orig_hour == 1
    assert evening_repair["schedule"]._orig_day_of_week == "2-6"


def test_sec13f_monthly_schedule_remains_as_backup() -> None:
    schedule = get_beat_schedule()

    monthly = schedule["refresh-sec13f-monthly"]

    assert monthly["task"] == "refresh_sec13f"
    assert monthly["args"][1]["source"] == "scheduler"
    assert monthly["options"]["expires"] == 24 * 60 * 60


def test_position_atr_monitor_runs_every_minute_on_dedicated_queue() -> None:
    schedule = get_beat_schedule()

    monitor = schedule["position-atr-monitor"]

    assert monitor["task"] == "position_atr_monitor"
    assert monitor["schedule"]._orig_minute == "*"
    assert monitor["schedule"]._orig_hour == "8-23"
    assert monitor["schedule"]._orig_day_of_week == "1-5"
    assert monitor["args"][1]["source"] == "scheduler"
    assert monitor["options"]["expires"] == 50
    assert monitor["options"]["queue"] == "monitor"

    after_hours = schedule["position-atr-monitor-us-after-hours"]
    assert after_hours["task"] == "position_atr_monitor"
    assert after_hours["schedule"]._orig_minute == "*"
    assert after_hours["schedule"]._orig_hour == "0-1"
    assert after_hours["schedule"]._orig_day_of_week == "2-6"
    assert after_hours["options"]["queue"] == "monitor"
