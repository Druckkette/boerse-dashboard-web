from datetime import UTC, datetime, timedelta
from app.services.stop_alerts import stop_transition
from app.workers.tasks import position_atr_monitor as monitor
from app.services.settings import DEFAULT_SETTINGS

NOW = datetime(2026, 9, 19, 12, tzinfo=UTC)


def observation(price, stop=100, now=NOW):
    return {"identity": "position-1", "ticker": "TEST", "name": "Test AG", "price": price,
            "stop": stop, "currency": "EUR", "quote_at": now.isoformat()}


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


def test_provider_failure_is_contained(monkeypatch):
    monkeypatch.setattr(monitor, "get_runtime_config_value", lambda key: "test-key")
    monkeypatch.setattr(monitor, "get_runtime_config_bool", lambda *args: False)
    monkeypatch.setattr(monitor, "_append_delivery_logs", lambda entries: None)
    def fail(**kwargs):
        raise TimeoutError("provider unavailable")
    monkeypatch.setattr(monitor, "_send_pushover_message", fail)
    _, alert = stop_transition({}, observation(99), NOW)
    result = monitor._deliver_monitor_alerts([alert], app_settings=DEFAULT_SETTINGS.model_copy(update={"pushover_enabled": True}))
    assert result["failed"] == 1
    assert result["sent"] == 0
    message = monitor._format_monitor_alert_message(alert)
    assert all(part in message for part in ("Test AG", "TEST", "99.00 EUR", "100.00 EUR", NOW.isoformat()))
