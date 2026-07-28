from __future__ import annotations

from datetime import UTC, datetime
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
        "monitor_open_position_atr",
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
    monkeypatch.setattr(monitor_module, "monitor_open_position_atr", fake_monitor)
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


def test_monitor_trade_day_resets_at_0730_berlin() -> None:
    before_reset = datetime(2026, 6, 18, 5, 29, tzinfo=UTC)
    at_reset = datetime(2026, 6, 18, 5, 30, tzinfo=UTC)

    assert monitor_module._monitor_trade_day(before_reset) == "2026-06-17"
    assert monitor_module._monitor_trade_day(at_reset) == "2026-06-18"


def test_position_monitor_cooldown_suppresses_same_trade_day(monkeypatch: pytest.MonkeyPatch) -> None:
    stored_state = {
        "tickers": {
            "AAPL": {
                "trade_day": "2026-06-18",
                "last_alert_at": "2026-06-18T07:35:00+02:00",
                "last_distance_atr": 1.8,
                "threshold_atr": 1.5,
                "escalated_2x": False,
            }
        }
    }
    written: dict = {}
    monkeypatch.setattr(monitor_module.settings_repository, "read_position_monitor_state", lambda: stored_state)
    monkeypatch.setattr(monitor_module.settings_repository, "write_position_monitor_state", lambda values: written.update(values) or values)

    result = monitor_module._apply_cooldown_state(
        {
            "ok": True,
            "records_seen": 1,
            "items": [
                {
                    "ticker": "AAPL",
                    "monitor": {
                        "threshold_crossed": True,
                        "distance_atr": 2.2,
                        "threshold_atr": 1.5,
                        "reference": "previous_close",
                    },
                }
            ],
        },
        monitor_settings={"position_monitor_threshold_atr": 1.5},
        now=datetime(2026, 6, 18, 6, 0, tzinfo=UTC),
    )

    monitor = result["items"][0]["monitor"]
    assert result["alerts"] == []
    assert result["alerts_suppressed"][0]["ticker"] == "AAPL"
    assert monitor["alert_allowed"] is False
    assert monitor["alert_reason"] == "cooldown_same_trade_day"
    assert written["last_summary"]["suppressed"] == 1


def test_position_monitor_allows_2x_atr_escalation_same_trade_day(monkeypatch: pytest.MonkeyPatch) -> None:
    stored_state = {
        "tickers": {
            "AAPL": {
                "trade_day": "2026-06-18",
                "last_alert_at": "2026-06-18T07:35:00+02:00",
                "last_distance_atr": 1.8,
                "threshold_atr": 1.5,
                "escalated_2x": False,
            }
        }
    }
    written: dict = {}
    monkeypatch.setattr(monitor_module.settings_repository, "read_position_monitor_state", lambda: stored_state)
    monkeypatch.setattr(monitor_module.settings_repository, "write_position_monitor_state", lambda values: written.update(values) or values)

    result = monitor_module._apply_cooldown_state(
        {
            "ok": True,
            "records_seen": 1,
            "items": [
                {
                    "ticker": "AAPL",
                    "monitor": {
                        "threshold_crossed": True,
                        "distance_atr": 3.1,
                        "threshold_atr": 1.5,
                        "reference": "previous_close",
                    },
                }
            ],
        },
        monitor_settings={"position_monitor_threshold_atr": 1.5},
        now=datetime(2026, 6, 18, 6, 0, tzinfo=UTC),
    )

    monitor = result["items"][0]["monitor"]
    assert result["alerts"][0]["ticker"] == "AAPL"
    assert monitor["alert_allowed"] is True
    assert monitor["alert_reason"] == "2x_atr_escalation"
    assert written["tickers"]["AAPL"]["escalated_2x"] is True


def test_position_monitor_does_not_repeat_prior_day_loss_after_reset(monkeypatch: pytest.MonkeyPatch) -> None:
    stored_state = {
        "tickers": {
            "AAPL": {
                "trade_day": "2026-06-17",
                "last_alert_at": "2026-06-17T18:00:00+02:00",
                "last_distance_atr": 1.8,
                "threshold_atr": 1.5,
                "reference": "previous_close",
                "reference_price": 100.0,
                "current_price": 96.4,
                "escalated_2x": False,
            }
        }
    }
    written: dict = {}
    monkeypatch.setattr(monitor_module.settings_repository, "read_position_monitor_state", lambda: stored_state)
    monkeypatch.setattr(monitor_module.settings_repository, "write_position_monitor_state", lambda values: written.update(values) or values)

    result = monitor_module._apply_cooldown_state(
        {
            "ok": True,
            "records_seen": 1,
            "items": [
                {
                    "ticker": "AAPL",
                    "monitor": {
                        "threshold_crossed": True,
                        "distance_atr": 1.8,
                        "threshold_atr": 1.5,
                        "reference": "previous_close",
                        "reference_price": 100.0,
                        "current_price": 96.4,
                    },
                }
            ],
        },
        monitor_settings={"position_monitor_threshold_atr": 1.5},
        now=datetime(2026, 6, 18, 6, 0, tzinfo=UTC),
    )

    monitor = result["items"][0]["monitor"]
    assert result["alerts"] == []
    assert result["alerts_suppressed"][0]["reason"] == "new_trade_day_no_new_loss"
    assert monitor["alert_allowed"] is False
    assert monitor["alert_reason"] == "new_trade_day_no_new_loss"
    assert written["tickers"]["AAPL"]["trade_day"] == "2026-06-18"


def test_position_monitor_allows_new_trade_day_when_reference_changes(monkeypatch: pytest.MonkeyPatch) -> None:
    stored_state = {
        "tickers": {
            "AAPL": {
                "trade_day": "2026-06-17",
                "last_alert_at": "2026-06-17T18:00:00+02:00",
                "last_distance_atr": 1.8,
                "threshold_atr": 1.5,
                "reference": "previous_close",
                "reference_price": 100.0,
                "current_price": 96.4,
                "escalated_2x": False,
            }
        }
    }
    written: dict = {}
    monkeypatch.setattr(monitor_module.settings_repository, "read_position_monitor_state", lambda: stored_state)
    monkeypatch.setattr(monitor_module.settings_repository, "write_position_monitor_state", lambda values: written.update(values) or values)

    result = monitor_module._apply_cooldown_state(
        {
            "ok": True,
            "records_seen": 1,
            "items": [
                {
                    "ticker": "AAPL",
                    "monitor": {
                        "threshold_crossed": True,
                        "distance_atr": 1.6,
                        "threshold_atr": 1.5,
                        "reference": "previous_close",
                        "reference_price": 96.0,
                        "current_price": 92.8,
                    },
                }
            ],
        },
        monitor_settings={"position_monitor_threshold_atr": 1.5},
        now=datetime(2026, 6, 18, 6, 0, tzinfo=UTC),
    )

    assert result["alerts"][0]["ticker"] == "AAPL"
    assert result["alerts"][0]["reason"] == "new_trade_day"
    assert written["tickers"]["AAPL"]["reference_price"] == 96.0


def test_position_monitor_allows_changed_reference_mode_same_trade_day(monkeypatch: pytest.MonkeyPatch) -> None:
    stored_state = {
        "tickers": {
            "AAPL": {
                "trade_day": "2026-06-18",
                "last_distance_atr": 1.8,
                "threshold_atr": 1.5,
                "reference": "previous_close",
                "reference_price": 100.0,
                "threshold_crossed": True,
                "escalated_2x": False,
            }
        }
    }
    monkeypatch.setattr(monitor_module.settings_repository, "read_position_monitor_state", lambda: stored_state)
    monkeypatch.setattr(monitor_module.settings_repository, "write_position_monitor_state", lambda values: values)

    result = monitor_module._apply_cooldown_state(
        {
            "ok": True,
            "records_seen": 1,
            "items": [
                {
                    "ticker": "AAPL",
                    "monitor": {
                        "threshold_crossed": True,
                        "distance_atr": 1.7,
                        "threshold_atr": 1.5,
                        "reference": "entry_price",
                        "reference_label": "Vom Einstand",
                        "reference_price": 100.0,
                        "current_price": 96.6,
                    },
                }
            ],
        },
        monitor_settings={"position_monitor_threshold_atr": 1.5},
        now=datetime(2026, 6, 18, 6, 0, tzinfo=UTC),
    )

    assert result["alerts"][0]["reason"] == "monitor_configuration_changed"
    assert result["items"][0]["monitor"]["alert_allowed"] is True


def test_position_monitor_rearms_after_real_recovery(monkeypatch: pytest.MonkeyPatch) -> None:
    stored_state = {
        "tickers": {
            "AAPL": {
                "trade_day": "2026-06-18",
                "last_distance_atr": 1.8,
                "threshold_atr": 1.5,
                "reference": "entry_price",
                "reference_price": 100.0,
                "threshold_crossed": True,
                "escalated_2x": False,
            }
        }
    }
    written: dict = {}
    monkeypatch.setattr(monitor_module.settings_repository, "read_position_monitor_state", lambda: stored_state)
    monkeypatch.setattr(
        monitor_module.settings_repository,
        "write_position_monitor_state",
        lambda values: written.update(values) or values,
    )

    recovery = monitor_module._apply_cooldown_state(
        {
            "ok": True,
            "records_seen": 1,
            "items": [
                {
                    "ticker": "AAPL",
                    "monitor": {
                        "threshold_crossed": False,
                        "distance_atr": 1.2,
                        "threshold_atr": 1.5,
                        "reference": "entry_price",
                        "reference_price": 100.0,
                        "current_price": 97.6,
                    },
                }
            ],
        },
        monitor_settings={"position_monitor_threshold_atr": 1.5},
        now=datetime(2026, 6, 18, 6, 0, tzinfo=UTC),
    )

    assert recovery["alerts"] == []
    assert written["tickers"]["AAPL"]["threshold_crossed"] is False

    monkeypatch.setattr(monitor_module.settings_repository, "read_position_monitor_state", lambda: written)
    recross = monitor_module._apply_cooldown_state(
        {
            "ok": True,
            "records_seen": 1,
            "items": [
                {
                    "ticker": "AAPL",
                    "monitor": {
                        "threshold_crossed": True,
                        "distance_atr": 1.6,
                        "threshold_atr": 1.5,
                        "reference": "entry_price",
                        "reference_label": "Vom Einstand",
                        "reference_price": 100.0,
                        "current_price": 96.8,
                    },
                }
            ],
        },
        monitor_settings={"position_monitor_threshold_atr": 1.5},
        now=datetime(2026, 6, 18, 6, 5, tzinfo=UTC),
    )

    assert recross["alerts"][0]["reason"] == "threshold_recrossed"
    assert recross["items"][0]["monitor"]["alert_allowed"] is True


def test_failed_delivery_does_not_consume_atr_alert(monkeypatch: pytest.MonkeyPatch) -> None:
    written: dict = {}
    monkeypatch.setattr(monitor_module.settings_repository, "read_position_monitor_state", lambda: {})
    monkeypatch.setattr(
        monitor_module.settings_repository,
        "write_position_monitor_state",
        lambda values: written.update(values) or values,
    )
    result = monitor_module._apply_cooldown_state(
        {
            "ok": True,
            "records_seen": 1,
            "items": [
                {
                    "ticker": "AAPL",
                    "monitor": {
                        "threshold_crossed": True,
                        "distance_atr": 1.8,
                        "threshold_atr": 1.5,
                        "reference": "previous_close",
                        "reference_price": 100.0,
                        "current_price": 96.4,
                    },
                }
            ],
        },
        monitor_settings={"position_monitor_threshold_atr": 1.5},
        now=datetime(2026, 6, 18, 6, 0, tzinfo=UTC),
        persist_state=False,
    )

    monitor_module._finalize_monitor_state(
        result,
        alert_delivery={"sent": 0, "failed": 1, "skipped": 0, "sent_tickers": []},
    )

    assert "_pending_monitor_state" not in result
    assert "AAPL" not in written["tickers"]
    assert written["last_summary"]["delivery_failed"] == 1


def test_confirmed_delivery_consumes_atr_alert(monkeypatch: pytest.MonkeyPatch) -> None:
    written: dict = {}
    monkeypatch.setattr(monitor_module.settings_repository, "read_position_monitor_state", lambda: {})
    monkeypatch.setattr(
        monitor_module.settings_repository,
        "write_position_monitor_state",
        lambda values: written.update(values) or values,
    )
    result = monitor_module._apply_cooldown_state(
        {
            "ok": True,
            "records_seen": 1,
            "items": [
                {
                    "ticker": "AAPL",
                    "monitor": {
                        "threshold_crossed": True,
                        "distance_atr": 1.8,
                        "threshold_atr": 1.5,
                        "reference": "previous_close",
                        "reference_price": 100.0,
                        "current_price": 96.4,
                    },
                }
            ],
        },
        monitor_settings={"position_monitor_threshold_atr": 1.5},
        now=datetime(2026, 6, 18, 6, 0, tzinfo=UTC),
        persist_state=False,
    )

    monitor_module._finalize_monitor_state(
        result,
        alert_delivery={"sent": 1, "failed": 0, "skipped": 0, "sent_tickers": ["AAPL"]},
    )

    assert written["tickers"]["AAPL"]["trade_day"] == "2026-06-18"
    assert written["last_summary"]["sent"] == 1


def test_pushover_delivery_uses_high_priority(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}
    app_settings = SimpleNamespace(pushover_enabled=True)
    monkeypatch.setattr(
        monitor_module,
        "get_runtime_config_value",
        lambda key: "user" if "USER" in key else "token",
    )
    monkeypatch.setattr(monitor_module, "get_runtime_config_bool", lambda *args: False)

    def fake_send(**kwargs):
        captured.update(kwargs)
        return {"status": 1, "request": "test"}

    monkeypatch.setattr(monitor_module, "_send_pushover_message", fake_send)
    delivery = monitor_module._deliver_monitor_alerts(
        [
            {
                "ticker": "AAPL",
                "distance_atr": 1.6,
                "threshold_atr": 1.5,
                "reference": "previous_close",
                "current_price": 96.8,
                "reference_price": 100.0,
                "reason": "new_trade_day",
            }
        ],
        app_settings=app_settings,
    )

    assert delivery["sent"] == 1
    assert delivery["sent_tickers"] == ["AAPL"]
    assert captured["priority"] == 1
    assert captured["title"] == "ATR-Alarm AAPL"
