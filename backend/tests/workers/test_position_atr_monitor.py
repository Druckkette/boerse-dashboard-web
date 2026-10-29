from __future__ import annotations

import copy
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.notification_preferences import NotificationPreferences, merge_preferences
from app.repositories import jobs as job_repository
from app.services import stop_alerts
from app.workers.tasks import position_atr_monitor as monitor_module

NOW = datetime(2026, 10, 26, 15, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def reset_jobs(monkeypatch: pytest.MonkeyPatch) -> None:
    job_repository.clear_memory_jobs()
    monkeypatch.setattr(monitor_module.settings_repository, "read_atr_rearm_requests", lambda: {})


def settings(**patch) -> dict:
    return {
        "notification_preferences": merge_preferences(NotificationPreferences().model_dump(), patch)
    }


def atr_tick(
    state: dict,
    distance: float | None,
    now: datetime = NOW,
    *,
    prefs: dict | None = None,
    quote_at: datetime | None = None,
    rearm: dict | None = None,
) -> dict:
    result = monitor_module._cooldown_decision(
        ticker="BE",
        monitor={
            "distance_atr": distance,
            "threshold_atr": 1.5,
            "threshold_crossed": distance is not None and distance >= 1.5,
            "current_price": 97.0,
            "reference": "previous_close",
            "reference_price": 100.0,
            "live_quote_at": (quote_at or now).isoformat(),
        },
        ticker_state={"BE": copy.deepcopy(state)},
        trade_day=monitor_module._monitor_trade_day(now),
        now=now,
        reset_at=monitor_module._next_monitor_reset(now),
        monitor_settings={**(prefs or settings()), "atr_rearm_requests": rearm or {}},
    )
    return result


def first_atr(**atr_preferences) -> dict:
    return atr_tick({}, 1.6, prefs=settings(atr=atr_preferences))["state_update"]


def test_scheduler_disabled_does_not_read_prices(monkeypatch: pytest.MonkeyPatch) -> None:
    app_settings = SimpleNamespace(position_monitor_enabled=False, model_dump=lambda: {})
    monkeypatch.setattr(monitor_module, "get_app_settings", lambda: app_settings)
    monkeypatch.setattr(
        monitor_module, "monitor_open_position_atr", lambda **kw: pytest.fail("must skip")
    )
    job = job_repository.create_job("position_atr_monitor", {"source": "scheduler"})
    assert monitor_module.position_atr_monitor.run(job.job_id, job.payload)["skipped"] is True


def test_worker_dispatches_stop_atr_and_signals_together(monkeypatch: pytest.MonkeyPatch) -> None:
    app_settings = SimpleNamespace(position_monitor_enabled=True, model_dump=lambda: settings())
    monkeypatch.setattr(monitor_module, "get_app_settings", lambda: app_settings)
    monkeypatch.setattr(
        monitor_module,
        "monitor_open_position_atr",
        lambda **kw: {"items": [{"stop_observation": {"ticker": "BE"}}]},
    )
    monkeypatch.setattr(
        monitor_module,
        "_apply_cooldown_state",
        lambda result, **kw: {**result, "alerts": [{"kind": "atr", "alert_id": "atr1"}]},
    )
    monkeypatch.setattr(
        monitor_module,
        "_apply_portfolio_signal_state",
        lambda *a, **kw: [{"kind": "stock_signal", "alert_id": "ma1"}],
    )
    captured = {}
    delivery = {"sent": 1, "accepted_alert_ids": ["stop1", "atr1", "ma1"]}

    def deliver(items, sender, **kwargs):
        captured.update(kwargs)
        assert items == [{"ticker": "BE"}]
        return {"delivery": delivery}

    monkeypatch.setattr(stop_alerts, "deliver_stop_alerts", deliver)
    monkeypatch.setattr(
        monitor_module,
        "_finalize_monitor_state",
        lambda result, **kw: captured.update(atr_delivery=kw["alert_delivery"]),
    )
    monkeypatch.setattr(
        monitor_module,
        "_finalize_portfolio_signal_state",
        lambda result, **kw: captured.update(ma_delivery=kw["alert_delivery"]),
    )
    job = job_repository.create_job("position_atr_monitor", {})
    monitor_module.position_atr_monitor.run(job.job_id, {})
    assert [a["alert_id"] for a in captured["additional_alerts"]] == ["atr1", "ma1"]
    assert captured["atr_delivery"] is captured["ma_delivery"] is delivery


def test_atr_threshold_chatter_never_rearms() -> None:
    state = first_atr(repeat="recovery")
    for minute in range(1, 20):
        outcome = atr_tick(
            state,
            1.49 if minute % 2 else 1.51,
            NOW + timedelta(minutes=minute),
            prefs=settings(atr={"repeat": "recovery"}),
        )
        assert not outcome["allowed"]
        state = outcome["state_update"] or state
    assert state["threshold_crossed"] is True


@pytest.mark.parametrize("distance", [None, float("nan"), float("inf")])
def test_atr_missing_data_preserves_latch(distance: float | None) -> None:
    previous = first_atr()
    result = atr_tick(previous, distance, NOW + timedelta(minutes=1))
    assert result["state_update"] is None
    assert not result["allowed"]
    assert previous["threshold_crossed"] is True


@pytest.mark.parametrize("offset", [-21, 1])
def test_atr_stale_or_future_quote_cannot_recover_or_warn(offset: int) -> None:
    result = atr_tick(
        first_atr(), 0.1, NOW + timedelta(minutes=1), quote_at=NOW + timedelta(minutes=1 + offset)
    )
    assert result["state_update"] is None
    assert result["monitor_update"]["alert_reason"] == "no_fresh_quote"


def test_atr_recovery_requires_ten_minutes_of_distinct_quotes() -> None:
    prefs = settings(atr={"repeat": "recovery", "recovery_atr": 1, "recovery_minutes": 10})
    state = first_atr()
    for minute in range(1, 12):
        tick = atr_tick(state, 0.9, NOW + timedelta(minutes=minute), prefs=prefs)
        assert not tick["allowed"]
        state = tick["state_update"]
        assert state["threshold_crossed"] is (minute < 11)
    result = atr_tick(state, 1.55, NOW + timedelta(minutes=12), prefs=prefs)
    assert result["allowed"]
    assert result["alert"]["reason"] == "confirmed_recovery"


def test_repeated_same_quote_does_not_count_toward_recovery() -> None:
    state = first_atr()
    state = atr_tick(state, 0.8, NOW + timedelta(minutes=1))["state_update"]
    for minute in range(2, 12):
        result = atr_tick(
            state, 0.8, NOW + timedelta(minutes=minute), quote_at=NOW + timedelta(minutes=1)
        )
        assert result["state_update"] is None
    assert state["recovery_count"] == 1
    assert state["threshold_crossed"] is True


def test_gap_breaks_recovery_confirmation() -> None:
    state = first_atr()
    state = atr_tick(state, 0.8, NOW + timedelta(minutes=1))["state_update"]
    state = atr_tick(state, 0.8, NOW + timedelta(minutes=12))["state_update"]
    assert state["threshold_crossed"] is True
    assert state["recovery_count"] == 1


@pytest.mark.parametrize(
    "repeat,minutes,expected",
    [
        ("manual", 1500, False),
        ("daily", 1500, True),
        ("daily", 60, False),
        ("interval", 59, False),
        ("interval", 60, True),
    ],
)
def test_atr_repeat_policy(repeat: str, minutes: int, expected: bool) -> None:
    result = atr_tick(
        first_atr(),
        1.6,
        NOW + timedelta(minutes=minutes),
        prefs=settings(atr={"repeat": repeat, "repeat_minutes": 60}),
    )
    assert result["allowed"] is expected


def test_manual_atr_rearm_is_consumed_after_acceptance() -> None:
    prefs = settings(atr={"repeat": "manual"})
    marker = {"BE": (NOW + timedelta(minutes=2)).isoformat()}
    tick = atr_tick(first_atr(), 1.6, NOW + timedelta(minutes=3), prefs=prefs, rearm=marker)
    assert tick["alert"]["reason"] == "manual_rearm"
    assert not atr_tick(
        tick["state_update"], 1.6, NOW + timedelta(minutes=4), prefs=prefs, rearm=marker
    )["allowed"]


def test_atr_escalation_is_configurable_and_once_per_episode() -> None:
    prefs = settings(atr={"repeat": "manual", "escalation_atr": 4})
    state = first_atr()
    assert not atr_tick(state, 3.1, NOW + timedelta(minutes=1), prefs=prefs)["allowed"]
    tick = atr_tick(state, 4.1, NOW + timedelta(minutes=2), prefs=prefs)
    assert tick["alert"]["event_type"] == "atr_escalation"
    assert not atr_tick(tick["state_update"], 5.0, NOW + timedelta(minutes=3), prefs=prefs)[
        "allowed"
    ]
    assert not atr_tick(
        state,
        5,
        NOW + timedelta(minutes=4),
        prefs=settings(atr={"repeat": "manual", "escalation_enabled": False}),
    )["allowed"]


def test_failed_atr_does_not_erase_previous_latch_or_accept_by_other_ticker_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    previous = first_atr()
    written = {}
    result = {
        "_pending_monitor_state": {"tickers": {"BE": {"changed": True}}},
        "_previous_monitor_tickers": {"BE": previous},
        "alerts": [{"ticker": "BE", "alert_id": "atr1"}],
    }
    monkeypatch.setattr(
        monitor_module.settings_repository,
        "write_position_monitor_state",
        lambda value: written.update(value),
    )
    monitor_module._finalize_monitor_state(
        result, alert_delivery={"accepted_alert_ids": ["ma1"], "accepted_tickers": ["BE"]}
    )
    assert written["tickers"]["BE"] == previous


def test_digest_acceptance_commits_atr_and_preserves_it_for_signal_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    written = {}
    result = {
        "_pending_monitor_state": {"tickers": {"BE": {"changed": True}}},
        "_previous_monitor_tickers": {},
        "alerts": [{"ticker": "BE", "alert_id": "atr1"}],
        "_pending_signal_state": {"base_state": {}, "tickers": {}},
    }
    monkeypatch.setattr(
        monitor_module.settings_repository,
        "write_position_monitor_state",
        lambda value: written.update(value),
    )
    monitor_module._finalize_monitor_state(
        result, alert_delivery={"accepted_alert_ids": ["atr1"], "accepted_tickers": ["BE"]}
    )
    monitor_module._finalize_portfolio_signal_state(
        result, alert_delivery={"accepted_alert_ids": []}
    )
    assert written["tickers"]["BE"] == {"changed": True}


def ma_tick(
    state: dict,
    distance: float,
    now: datetime,
    *,
    rule: dict | None = None,
    quote_at: datetime | None = None,
    closed: dict | None = None,
) -> tuple[dict, list]:
    current = copy.deepcopy(state)
    trend = {
        "current_price": 100,
        "currency": "USD",
        "quote_at": (quote_at or now).isoformat(),
        "moving_averages": {
            "ema21": {
                "label": "21-EMA",
                "above": distance >= 0,
                "distance_pct": distance,
                "value": 101,
            }
        },
    }
    rules = merge_preferences(NotificationPreferences().model_dump()["ma"], {"ema21": rule or {}})
    events = monitor_module._update_moving_average_signal_state(
        previous=state,
        current=current,
        trend=trend,
        monitor={"atr_value": 2, "current_price": 100},
        now=now,
        preferences=rules,
        closed_trend=closed,
    )
    return current, events


def baseline_ma() -> dict:
    return ma_tick({}, 1, NOW)[0]


def test_ma_confirmation_and_per_event_routing_are_independent() -> None:
    state = baseline_ma()
    rule = {
        "confirmation_minutes": 3,
        "break_mode": "off",
        "recovery_mode": "digest",
        "priority": -1,
        "session": "custom",
        "min_distance": 0.3,
        "distance_unit": "pct",
    }
    for minute in range(1, 5):
        state, events = ma_tick(state, -0.8, NOW + timedelta(minutes=minute), rule=rule)
        if minute < 4:
            assert not events
    event = events[0]
    assert (event["event_type"], event["mode"], event["priority"], event["session"]) == (
        "ma_break",
        "off",
        -1,
        "custom",
    )
    assert "3 Minuten" in event["detail"]
    for minute in range(5, 9):
        state, events = ma_tick(state, 0.8, NOW + timedelta(minutes=minute), rule=rule)
    assert events[0]["event_type"] == "ma_recovery"
    assert events[0]["mode"] == "digest"


def test_ma_same_stale_or_future_quote_never_confirms() -> None:
    state = baseline_ma()
    state, _ = ma_tick(state, -1, NOW + timedelta(minutes=1))
    for minute in range(2, 14):
        unchanged, events = ma_tick(
            state, -1, NOW + timedelta(minutes=minute), quote_at=NOW + timedelta(minutes=1)
        )
        assert not events
        assert unchanged == state
    unchanged, events = ma_tick(
        state, -1, NOW + timedelta(minutes=30), quote_at=NOW + timedelta(minutes=1)
    )
    assert not events
    assert unchanged == state


def test_ma_min_distance_in_atr_and_percent() -> None:
    state = baseline_ma()
    for minute in range(1, 15):
        state, events = ma_tick(
            state,
            -0.3,
            NOW + timedelta(minutes=minute),
            rule={"distance_unit": "atr", "min_distance": 0.2},
        )
        assert not events  # ATR=2%, threshold 0.4%.
    assert state["ma_alert_state"]["ema21"]["stable_zone"] == "above"


def test_ma_worsening_waits_for_configured_distance_and_confirmation() -> None:
    state = ma_tick({}, -1, NOW)[0]
    rule = {"confirmation_minutes": 2, "worsening_atr": 1, "worsening_mode": "immediate"}
    state, events = ma_tick(state, -2.9, NOW + timedelta(minutes=1), rule=rule)
    assert not events
    for minute in range(2, 5):
        state, events = ma_tick(state, -3.1, NOW + timedelta(minutes=minute), rule=rule)
    assert events[0]["event_type"] == "ma_worsening"
    assert events[0]["mode"] == "immediate"
    assert not ma_tick(state, -3.2, NOW + timedelta(minutes=5), rule=rule)[1]


def test_close_confirmation_uses_verified_final_close_once() -> None:
    state = baseline_ma()
    rule = {"confirmation": "close", "break_mode": "immediate"}
    closed = {
        "as_of": "2026-10-23",
        "current_price": 100,
        "currency": "USD",
        "is_final": True,
        "moving_averages": {"ema21": {"above": False, "value": 101, "distance_pct": -1}},
    }
    # An intraday quote below the line is insufficient without a verified close.
    assert not ma_tick(
        state, -1, NOW + timedelta(minutes=1), rule=rule, closed={**closed, "is_final": False}
    )[1]
    state, events = ma_tick(state, 1, NOW + timedelta(minutes=2), rule=rule, closed=closed)
    assert events[0]["event_type"] == "ma_break"
    assert "Schlusskurs" in events[0]["detail"]
    assert not ma_tick(state, 1, NOW + timedelta(minutes=3), rule=rule, closed=closed)[1]


def test_score_threshold_direction_and_digest_state_are_independent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stored = {
        "signal_tickers": {
            "BE": {
                "assessment": {
                    "source": "database",
                    "as_of": "2026-10-26",
                    "overall_score": 60,
                    "verdict_label": "Beobachten",
                    "verdict_tone": "warning",
                    "checks": {},
                    "signals": {},
                    "signal_states": {},
                },
                "score_notification_anchor": 60,
            }
        }
    }
    monkeypatch.setattr(
        monitor_module.settings_repository, "read_position_monitor_state", lambda: stored
    )

    def write(value):
        stored.clear()
        stored.update(copy.deepcopy(value))

    monkeypatch.setattr(monitor_module.settings_repository, "write_position_monitor_state", write)
    score = {"value": 69}
    monkeypatch.setattr(
        monitor_module,
        "get_stock_assessment",
        lambda ticker: SimpleNamespace(
            model_dump=lambda **kw: {
                "source": "database",
                "as_of": "2026-10-26",
                "scores": {"overall": score["value"]},
                "verdict_label": "Beobachten",
                "verdict_tone": "warning",
                "checks": [],
                "chart_signals": [],
            }
        ),
    )
    prefs = settings(
        assessment={"score_min_change": 10, "score_mode": "immediate", "notify_improvements": False}
    )
    result = {"items": [{"ticker": "BE", "as_of": "2026-10-26"}]}
    assert (
        monitor_module._apply_portfolio_signal_state(result, monitor_settings=prefs, now=NOW) == []
    )
    monitor_module._finalize_portfolio_signal_state(
        result, alert_delivery={"accepted_alert_ids": []}
    )
    score["value"] = 70
    alerts = monitor_module._apply_portfolio_signal_state(
        result, monitor_settings=prefs, now=NOW + timedelta(minutes=16)
    )
    assert alerts[0]["events"][0]["event_type"] == "score"
    assert alerts[0]["events"][0]["mode"] == "off"
    assert "von 60 auf 70 gestiegen" in alerts[0]["events"][0]["label"]
    monitor_module._finalize_portfolio_signal_state(
        result, alert_delivery={"accepted_alert_ids": [alerts[0]["alert_id"]]}
    )
    assert stored["signal_tickers"]["BE"]["score_notification_anchor"] == 70


@pytest.mark.parametrize(
    "old,new,expected",
    [
        ("Unter 200 Tage", "Zu schwach", "good"),
        ("Zu schwach", "Beobachten", "good"),
        ("Beobachten", "Unter 200 Tage", "warning"),
        ("Überdehnt", "Beobachten", "neutral"),
    ],
)
def test_verdict_direction_compares_old_and_new(old: str, new: str, expected: str) -> None:
    events = monitor_module._assessment_events({"verdict_label": old}, {"verdict_label": new})
    assert events[0]["tone"] == expected
    assert events[0]["event_type"] == "verdict"


def test_detector_does_not_build_legacy_daily_summary(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        monitor_module.settings_repository, "read_position_monitor_state", lambda: {}
    )
    result = {"items": []}
    assert (
        monitor_module._apply_portfolio_signal_state(
            result, monitor_settings=settings(), now=NOW.replace(hour=23)
        )
        == []
    )


def test_formatted_notifications_use_german_prose() -> None:
    alert = atr_tick({}, 1.6)["alert"]
    message = monitor_module._format_monitor_alert_message(alert)
    assert "1,60 ATR" in message
    assert "Verlustschwelle" in message
    message = monitor_module._format_stock_signal_alert_message(
        {
            "ticker": "BE",
            "current_price": 123.45,
            "events": [
                {
                    "tone": "warning",
                    "label": "Kurs >= 15",
                    "detail": "Abstand <= 3.5%; vorher < 2.0%.",
                }
            ],
        }
    )
    assert "123,45" in message and "höchstens 3,5" in message
    assert not any(symbol in message for symbol in ("<", ">", "→", "≥", "≤"))


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
            "negative:Stau-Tage": {
                "category": "negative",
                "label": "Stau-Tage",
                "detail": "3 in 10T",
            }
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
    assert "Gesamtscore von 76 auf 69 gefallen" in labels
    assert "Bewertung von „Stark“ auf „Beobachten“ geändert" in labels
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

    assert "Preisrückgänge bei hohem Vol." in message
    assert "Schwaches RS-Rating" in message
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


def test_legacy_daily_latch_uses_last_alert_day_after_a_non_crossing_observation() -> None:
    yesterday = NOW - timedelta(days=1)
    legacy = {
        "last_alert_at": yesterday.isoformat(),
        "trade_day": monitor_module._monitor_trade_day(yesterday),
        "threshold_crossed": True,
    }
    state = atr_tick(legacy, 1.3)["state_update"]
    assert atr_tick(state, 1.6, NOW + timedelta(minutes=1))["allowed"] is True


def test_ma_atr_threshold_uses_matching_currencies() -> None:
    current = {}
    # Same instrument: 100 EUR / 120 USD, daily ATR 2 EUR / 2.4 USD.
    monitor_module._update_moving_average_signal_state(
        previous={},
        current=current,
        trend={
            "current_price": 100,
            "currency": "EUR",
            "quote_at": NOW.isoformat(),
            "moving_averages": {"ema21": {"above": True, "distance_pct": 1, "value": 99}},
        },
        monitor={"atr_value": 2.4, "current_price": 120},
        now=NOW,
    )
    assert current["ma_alert_state"]["ema21"]["threshold_pct"] == pytest.approx(0.4)
