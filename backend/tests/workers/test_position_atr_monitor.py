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


def test_fresh_live_ema_break_creates_portfolio_warning(monkeypatch: pytest.MonkeyPatch) -> None:
    written: dict = {}
    monkeypatch.setattr(monitor_module.settings_repository, "read_position_monitor_state", lambda: {})
    monkeypatch.setattr(
        monitor_module.settings_repository,
        "write_position_monitor_state",
        lambda values: written.update(values) or values,
    )
    result = {
        "items": [
            {
                "ticker": "NVDA",
                "as_of": "2026-08-13",
                "trend_monitor": {
                    "available": True,
                    "as_of": "2026-08-13",
                    "current_price": 180.0,
                    "currency": "USD",
                    "moving_averages": {
                        "ema21": {
                            "label": "21-EMA",
                            "value": 181.5,
                            "above": False,
                            "previous_above": True,
                            "distance_pct": -0.826,
                        }
                    },
                },
            }
        ]
    }

    alerts = monitor_module._apply_portfolio_signal_state(
        result,
        monitor_settings={
            "position_monitor_ma_alerts_enabled": True,
            "position_monitor_assessment_alerts_enabled": False,
        },
        now=datetime(2026, 8, 13, 15, 0, tzinfo=UTC),
    )

    assert alerts[0]["kind"] == "stock_signal"
    assert alerts[0]["events"][0]["label"] == "Bruch der 21-EMA"
    assert alerts[0]["events"][0]["detail"] == (
        "Vorher: darüber · Aktuell: Kurs 180.00 USD · 21-EMA 181.50 · Abstand -0.83%"
    )
    monitor_module._finalize_portfolio_signal_state(
        result,
        alert_delivery={"sent_alert_ids": [alerts[0]["alert_id"]]},
    )
    assert written["signal_tickers"]["NVDA"]["moving_averages"]["ema21"]["above"] is False


def test_unchanged_ma_break_is_not_repeated(monkeypatch: pytest.MonkeyPatch) -> None:
    stored = {
        "signal_tickers": {
            "NVDA": {
                "moving_averages": {
                    "ema21": {"label": "21-EMA", "value": 181.5, "above": False, "distance_pct": -0.8}
                }
            }
        }
    }
    monkeypatch.setattr(monitor_module.settings_repository, "read_position_monitor_state", lambda: stored)
    result = {
        "items": [
            {
                "ticker": "NVDA",
                "as_of": "2026-08-13",
                "trend_monitor": {
                    "available": True,
                    "as_of": "2026-08-13",
                    "current_price": 179.0,
                    "currency": "USD",
                    "moving_averages": {
                        "ema21": {
                            "label": "21-EMA",
                            "value": 181.4,
                            "above": False,
                            "previous_above": True,
                            "distance_pct": -1.323,
                        }
                    },
                },
            }
        ]
    }

    alerts = monitor_module._apply_portfolio_signal_state(
        result,
        monitor_settings={
            "position_monitor_ma_alerts_enabled": True,
            "position_monitor_assessment_alerts_enabled": False,
        },
        now=datetime(2026, 8, 13, 15, 1, tzinfo=UTC),
    )

    assert alerts == []


def test_assessment_changes_report_new_and_resolved_warnings() -> None:
    previous = {
        "overall_score": 76,
        "verdict_label": "Stark",
        "verdict_tone": "good",
        "checks": {
            "CMF Rating A oder B": {"passed": True, "detail": "B"},
            "MA-Ordnung (21>50>200)": {"passed": False, "detail": "nicht korrekt"},
        },
        "signals": {
            "negative:Stau-Tage": {"category": "negative", "label": "Stau-Tage", "detail": "3 in 10T"}
        },
    }
    current = {
        "overall_score": 69,
        "verdict_label": "Beobachten",
        "verdict_tone": "warning",
        "checks": {
            "CMF Rating A oder B": {"passed": False, "detail": "D"},
            "MA-Ordnung (21>50>200)": {"passed": True, "detail": "korrekt"},
        },
        "signals": {
            "negative:Bearish Engulfing": {
                "category": "negative",
                "label": "Bearish Engulfing",
                "detail": "1 in 15T",
            }
        },
        "signal_states": {
            "Stau-Tage": {
                "active": False,
                "available": True,
                "detail": "1/10 Tage · Warnung ab 2",
            },
            "Bearish Engulfing": {
                "active": True,
                "available": True,
                "detail": "1/15 Tage · Warnung ab 1",
            },
        },
    }

    events = monitor_module._assessment_events(previous, current)
    labels = [event["label"] for event in events]

    assert "Neues Warnzeichen: CMF Rating A oder B" in labels
    assert "Kriterium wieder erfüllt: MA-Ordnung (21>50>200)" in labels
    assert "Neues Warnzeichen: Bearish Engulfing" in labels
    assert "Warnzeichen beendet: Stau-Tage" in labels
    assert "Gesamtscore 76 → 69" in labels
    assert "Bewertung: Stark → Beobachten" in labels
    resolved = next(event for event in events if event["label"] == "Warnzeichen beendet: Stau-Tage")
    assert resolved["detail"] == "Vorher: 3 in 10T · Aktuell: 1/10 Tage · Warnung ab 2"


def test_resolved_high_volume_drop_message_shows_previous_and_current_count() -> None:
    previous = {
        "overall_score": 70,
        "verdict_label": "Beobachten",
        "signals": {
            "negative:Preisrückgänge bei hohem Vol.": {
                "category": "negative",
                "label": "Preisrückgänge bei hohem Vol.",
                "detail": "5/15 Tage, Kurs <= -0.9%, Vol. > Vortag oder 50T",
            }
        },
    }
    current = {
        "overall_score": 70,
        "verdict_label": "Beobachten",
        "signals": {},
        "signal_states": {
            "Preisrückgänge bei hohem Vol.": {
                "active": False,
                "available": True,
                "detail": "4/15 Tage · Kurs <= -0,9% und Volumen > Vortag oder 50T · Warnung ab 5",
            }
        },
    }

    events = monitor_module._assessment_events(previous, current)

    assert events == [
        {
            "tone": "good",
            "label": "Warnzeichen beendet: Preisrückgänge bei hohem Vol.",
            "detail": (
                "Vorher: 5/15 Tage, Kurs <= -0.9%, Vol. > Vortag oder 50T · "
                "Aktuell: 4/15 Tage · Kurs <= -0,9% und Volumen > Vortag oder 50T · Warnung ab 5"
            ),
        }
    ]


def test_missing_current_signal_data_is_not_reported_as_recovery() -> None:
    previous = {
        "overall_score": 70,
        "verdict_label": "Beobachten",
        "signals": {
            "negative:Schwaches RS-Rating": {
                "category": "negative",
                "label": "Schwaches RS-Rating",
                "detail": "RS 65",
            }
        },
    }
    current = {
        "overall_score": 70,
        "verdict_label": "Beobachten",
        "signals": {},
        "signal_states": {
            "Schwaches RS-Rating": {
                "active": False,
                "available": False,
                "detail": "RS-Rating nicht verfügbar",
            }
        },
    }

    events = monitor_module._assessment_events(previous, current)

    assert events[0]["tone"] == "neutral"
    assert events[0]["label"] == "Warnzeichen derzeit nicht bewertbar: Schwaches RS-Rating"


def test_missing_check_data_is_reported_as_data_hint_instead_of_warning() -> None:
    previous = {
        "overall_score": 70,
        "verdict_label": "Beobachten",
        "checks": {
            "EPS-Wachstum letzte 3 Jahre jeweils >=20% YoY": {
                "passed": True,
                "detail": "2025 +25,0%, 2024 +24,0%, 2023 +22,0% · alle >=20%",
            }
        },
    }
    current = {
        "overall_score": 70,
        "verdict_label": "Beobachten",
        "checks": {
            "EPS-Wachstum letzte 3 Jahre jeweils >=20% YoY": {
                "passed": False,
                "detail": "Nicht verfügbar: keine jährliche EPS-Historie gespeichert",
            }
        },
    }

    events = monitor_module._assessment_events(previous, current)

    assert events[0]["tone"] == "neutral"
    assert events[0]["label"].startswith("Kriterium derzeit nicht bewertbar:")


def test_newly_available_failed_check_is_reported_as_warning() -> None:
    label = "Institutionelle Unterstützung"
    previous = {
        "overall_score": 70,
        "verdict_label": "Beobachten",
        "checks": {label: {"passed": False, "detail": "Keine gespeicherten 13F-Trends"}},
    }
    current = {
        "overall_score": 70,
        "verdict_label": "Beobachten",
        "checks": {label: {"passed": False, "detail": "Große Institutionen: 3 · Trend negative"}},
    }

    events = monitor_module._assessment_events(previous, current)

    assert events[0]["tone"] == "warning"
    assert events[0]["label"] == f"Kriterium jetzt bewertbar: {label}"


def test_stock_signal_message_uses_clear_status_without_duplicate_wording() -> None:
    message = monitor_module._format_stock_signal_alert_message(
        {
            "ticker": "NVDA",
            "events": [
                {
                    "tone": "good",
                    "label": "Warnzeichen beendet: Preisrückgänge bei hohem Vol.",
                    "detail": "Vorher: 5/15 Tage · Aktuell: 4/15 Tage · Warnung ab 5",
                },
                {
                    "tone": "neutral",
                    "label": "Warnzeichen derzeit nicht bewertbar: Schwaches RS-Rating",
                    "detail": "Aktuell: RS-Rating nicht verfügbar",
                },
            ],
        }
    )

    assert "ENTWARNUNG: Preisrückgänge bei hohem Vol." in message
    assert "DATENHINWEIS: Schwaches RS-Rating" in message
    assert "ENTWARNUNG: Warnzeichen beendet" not in message


def test_failed_signal_delivery_keeps_previous_state(monkeypatch: pytest.MonkeyPatch) -> None:
    previous = {"moving_averages": {"sma50": {"above": True}}}
    written: dict = {}
    monkeypatch.setattr(
        monitor_module.settings_repository,
        "write_position_monitor_state",
        lambda values: written.update(values) or values,
    )
    result = {
        "_pending_signal_state": {
            "base_state": {},
            "finished_at": "2026-08-13T15:00:00+00:00",
            "tickers": {
                "AAPL": {
                    "previous": previous,
                    "current": {"moving_averages": {"sma50": {"above": False}}},
                    "alert_id": "stock-signal:AAPL:1",
                }
            },
        }
    }

    monitor_module._finalize_portfolio_signal_state(
        result,
        alert_delivery={"sent_alert_ids": []},
    )

    assert written["signal_tickers"]["AAPL"] == previous
