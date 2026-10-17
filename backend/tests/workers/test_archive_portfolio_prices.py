from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from app.repositories import jobs
from app.workers.tasks import archive_portfolio_prices as task


def point(day, complete=True):
    return SimpleNamespace(date=day, valuation_complete=complete, missing_instruments=[] if complete else ["TEST"], sp500_index=100)


@pytest.fixture
def capture(monkeypatch):
    jobs.clear_memory_jobs()
    monkeypatch.setattr(task, "datetime", SimpleNamespace(
        now=lambda tz: datetime(2026, 10, 17, 6, 15, tzinfo=tz), fromisoformat=datetime.fromisoformat))
    monkeypatch.setattr(task, "refresh_portfolio_curve_prices", lambda: {"ok": True, "errors": [], "archived": 3, "archive_ok": True})


@pytest.mark.parametrize("stamp,expected", [
    ("2026-10-16T22:40:00", "2026-10-16"),
    ("2026-10-17T06:15:00", "2026-10-16"),
    ("2026-10-19T08:00:00", "2026-10-16"),
    ("2027-01-01T06:15:00", "2026-12-31"),
])
def test_completed_day_respects_close_weekend_and_new_year(stamp, expected):
    assert task.completed_valuation_day(datetime.fromisoformat(stamp).replace(tzinfo=ZoneInfo("Europe/Berlin"))).isoformat() == expected


def test_historical_gap_stays_visible_without_hiding_successful_daily_capture(capture, monkeypatch):
    monkeypatch.setattr(task, "get_portfolio_curve", lambda **kw: SimpleNamespace(model="execution_history", complete_points=189, total_points=207,
        points=[point("2026-02-24", False), point("2026-10-16")]))
    result = task.archive_portfolio_prices.run()
    assert result["ok"] and result["partial"]
    assert result["refresh"]["archived"] == 3


def test_missing_recent_price_is_failed_and_retried(capture, monkeypatch):
    monkeypatch.setattr(task, "get_portfolio_curve", lambda **kw: SimpleNamespace(model="execution_history", complete_points=0, total_points=1, points=[point("2026-10-16", False)]))
    calls = []
    def retry(**kwargs):
        calls.append(kwargs)
        return RuntimeError("retry recorded")
    monkeypatch.setattr(task.archive_portfolio_prices, "retry", retry)
    with pytest.raises(RuntimeError, match="retry recorded"):
        task.archive_portfolio_prices.run()
    assert calls[0]["countdown"] == 900
    job = jobs.get_job(calls[0]["args"][0])
    assert job.status == "failed" and job.result["current_missing"] == [{"date": "2026-10-16", "instruments": ["TEST"]}]


def test_archive_write_failure_cannot_report_success(capture, monkeypatch):
    monkeypatch.setattr(task, "refresh_portfolio_curve_prices", lambda: {"ok": False, "errors": ["Archive: database unavailable"]})
    monkeypatch.setattr(task, "get_portfolio_curve", lambda **kw: SimpleNamespace(model="execution_history", complete_points=1, total_points=1, points=[point("2026-10-16")]))
    monkeypatch.setattr(task.archive_portfolio_prices, "retry", lambda **kw: RuntimeError("archive retry"))
    with pytest.raises(RuntimeError, match="archive retry"):
        task.archive_portfolio_prices.run()
