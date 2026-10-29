from datetime import UTC, datetime, timedelta
from app.services.stop_alerts import stop_transition
from app.workers.tasks import position_atr_monitor as monitor
from app.services.settings import DEFAULT_SETTINGS

NOW = datetime(2026, 9, 19, 12, tzinfo=UTC)


def observation(price, stop=100, now=NOW):
    return {
        "identity": "position-1",
        "ticker": "TEST",
        "name": "Test AG",
        "price": price,
        "stop": stop,
        "currency": "EUR",
        "quote_at": now.isoformat(),
    }


def test_crossing_recovery_hysteresis_and_stop_change():
    state, alert = stop_transition({}, observation(101), NOW)
    assert alert is None
    state, alert = stop_transition(state, observation(100), NOW)
    assert alert["stop_price"] == 100
    state["triggered"] = True  # Confirmed delivery
    for price in (99, 80, 100.1, 99):
        state, alert = stop_transition(state, observation(price), NOW)
        assert alert is None
    state, alert = stop_transition(state, observation(100.6), NOW)
    assert alert is None and state["triggered"] is False
    state, alert = stop_transition(state, observation(99), NOW)
    assert alert is not None
    state["triggered"] = True
    state, alert = stop_transition(state, observation(101, stop=102), NOW)
    assert alert is not None


def test_no_daily_reset_and_failed_delivery_backoff():
    state, _ = stop_transition({}, observation(99), NOW)
    _, alert = stop_transition(state, observation(98), NOW + timedelta(minutes=1))
    assert alert is None
    later = NOW + timedelta(minutes=16)
    state, alert = stop_transition(state, observation(98, now=later), later)
    assert alert is not None
    state["triggered"] = True
    later += timedelta(days=3)
    _, alert = stop_transition(state, observation(80, now=later), later)
    assert alert is None


def test_stale_quote_is_not_a_new_stop_event():
    assert stop_transition({}, observation(90), NOW + timedelta(hours=1))[1] is None
    assert stop_transition({}, observation(float("nan")), NOW)[1] is None


def test_provider_failure_is_contained():
    from app.services.notification_delivery import _dispatch_state

    def fail(**kwargs):
        raise TimeoutError("provider unavailable")

    _, alert = stop_transition({}, observation(99), NOW)
    _, result, logs = _dispatch_state(
        {},
        [alert],
        prefs=DEFAULT_SETTINGS.notification_preferences.model_dump(),
        now=NOW,
        sender=fail,
    )
    assert result["failed"] == 1
    assert result["sent"] == 0
    assert logs[0]["status"] == "failed"
    message = monitor._format_monitor_alert_message(alert)
    assert all(part in message for part in ("Test AG", "99,00 EUR", "100,00 EUR"))


def test_new_recovery_policy_requires_fresh_sustained_quotes():
    policy = {"repeat": "recovery", "recovery_pct": 1, "recovery_minutes": 10}
    state, _ = stop_transition({}, observation(99), NOW, preferences=policy)
    state.update(triggered=True, last_sent_at=NOW.isoformat())
    state, _ = stop_transition(state, observation(102), NOW, preferences=policy)
    state, _ = stop_transition(
        state, observation(102), NOW + timedelta(minutes=11), preferences=policy
    )
    assert state["triggered"]  # Reusing one cached quote cannot prove recovery.
    for minute in range(12, 23):
        later = NOW + timedelta(minutes=minute)
        state, _ = stop_transition(state, observation(102, now=later), later, preferences=policy)
    assert not state["triggered"]
    state, alert = stop_transition(state, observation(99, now=later), later, preferences=policy)
    assert alert is not None and alert["stop_identity"] == "position-1"


def test_new_manual_daily_and_interval_stop_rearm_policies():
    state, _ = stop_transition({}, observation(99), NOW)
    state.update(triggered=True, last_sent_at=NOW.isoformat(), retry_at=None)
    later = NOW + timedelta(days=2)
    assert (
        stop_transition(state, observation(99, now=later), later, preferences={"repeat": "manual"})[
            1
        ]
        is None
    )
    assert (
        stop_transition(state, observation(99, now=later), later, preferences={"repeat": "daily"})[
            1
        ]
        is not None
    )
    assert (
        stop_transition(
            state,
            observation(99, now=later),
            later,
            preferences={"repeat": "interval", "repeat_minutes": 60},
        )[1]
        is not None
    )
    assert (
        stop_transition(
            state,
            observation(99, now=NOW + timedelta(minutes=59)),
            NOW + timedelta(minutes=59),
            preferences={"repeat": "interval", "repeat_minutes": 60},
        )[1]
        is None
    )


def test_stale_quote_breaks_recovery_streak():
    policy = {"repeat": "recovery", "recovery_pct": 1, "recovery_minutes": 10}
    state = {"stop": 100, "triggered": True, "recovery_since": NOW.isoformat()}
    later = NOW + timedelta(hours=1)
    state, alert = stop_transition(state, observation(102), later, preferences=policy)
    assert "recovery_since" not in state and alert is None and state["triggered"]
