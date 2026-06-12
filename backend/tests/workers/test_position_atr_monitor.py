from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.repositories import jobs as job_repository
from app.workers.tasks import position_atr_monitor as monitor_module


@pytest.fixture(autouse=True)
def reset_jobs() -> None:
    job_repository.clear_memory_jobs()


def test_position_atr_monitor_skips_scheduler_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = SimpleNamespace(
        position_monitor_enabled=False,
        model_dump=lambda: {
            "position_monitor_enabled": False,
            "position_monitor_reference": "high_since_buy",
            "position_monitor_threshold_atr": 1.5,
            "position_monitor_atr_period": 21,
            "position_monitor_lookback_days": 120,
            "position_monitor_cooldown_hours": 12,
        },
    )
    monkeypatch.setattr(monitor_module, "get_app_settings", lambda: settings)
    monkeypatch.setattr(
        monitor_module,
        "monitor_open_positions",
        lambda *args, **kwargs: pytest.fail("scheduler run should be skipped"),
    )
    job = job_repository.create_job("position_atr_monitor", {"source": "scheduler"})

    result = monitor_module.position_atr_monitor.run(job.job_id, job.payload)
    updated = job_repository.get_job(job.job_id)

    assert result["skipped"] is True
    assert updated is not None
    assert updated.status == "skipped"


def test_position_atr_monitor_allows_manual_run_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = SimpleNamespace(
        position_monitor_enabled=False,
        model_dump=lambda: {
            "position_monitor_enabled": False,
            "position_monitor_reference": "entry_price",
            "position_monitor_threshold_atr": 2.0,
            "position_monitor_atr_period": 14,
            "position_monitor_lookback_days": 90,
            "position_monitor_cooldown_hours": 24,
        },
    )
    captured: dict = {}

    def fake_monitor(*, tickers, monitor_settings):
        captured["tickers"] = tickers
        captured["settings"] = monitor_settings
        return {"ok": True, "records_seen": 1, "records_written": 1, "items": []}

    monkeypatch.setattr(monitor_module, "get_app_settings", lambda: settings)
    monkeypatch.setattr(monitor_module, "monitor_open_positions", fake_monitor)
    job = job_repository.create_job(
        "position_atr_monitor",
        {"tickers": ["NVDA"], "monitor_settings": {"position_monitor_threshold_atr": 1.25}},
    )

    result = monitor_module.position_atr_monitor.run(job.job_id, job.payload)
    updated = job_repository.get_job(job.job_id)

    assert result["ok"] is True
    assert captured["tickers"] == ["NVDA"]
    assert captured["settings"]["position_monitor_threshold_atr"] == 1.25
    assert updated is not None
    assert updated.status == "done"
