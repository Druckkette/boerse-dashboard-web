"""Independent regressions for delivery policy; all sends use a local fake."""

from datetime import UTC, datetime, timedelta

from app.notification_preferences import NotificationPreferences
from app.services import notification_delivery as delivery
from app.services.stop_alerts import stop_transition

NOW = datetime(2026, 10, 29, 15, 0, tzinfo=UTC)


def test_latest_verified_close_is_delivered_after_regular_session_but_respects_quiet_hours():
    preferences = NotificationPreferences().model_dump()
    after_close = datetime(2026, 10, 29, 20, 1, tzinfo=UTC)
    entry = {"ticker": "AAPL", "category": "ma", "session": "regular", "alert": {
        "kind": "stock_signal", "events": [{"confirmation": "close", "observation": "2026-10-29"}],
    }}
    assert not delivery._regular_session("AAPL", after_close)
    assert delivery._held_reason(entry, preferences, after_close) == ""
    entry["alert"]["events"][0]["observation"] = "2026-10-28"
    assert "Außerhalb" in delivery._held_reason(entry, preferences, after_close)
    entry["alert"]["events"][0]["observation"] = "2026-10-29"
    preferences["quiet"].update(enabled=True, start="20:00", end="07:00")
    assert "Ruhezeit" in delivery._held_reason(entry, preferences, after_close)
    preferences["quiet"]["enabled"] = False
    entry["session"] = "custom"
    preferences["custom_session"].update(start="08:00", end="20:00")
    assert "Außerhalb" in delivery._held_reason(entry, preferences, after_close)


def prefs():
    value = NotificationPreferences().model_dump()
    value["assessment"]["session"] = "all"
    return value


def signal(
    identifier,
    *,
    category="verdict",
    event_type="verdict",
    mode="digest",
    label="Bewertung geändert",
):
    return {
        "ticker": "BE",
        "kind": "stock_signal",
        "alert_id": identifier,
        "events": [
            {
                "event_id": identifier + ":event",
                "category": category,
                "event_type": event_type,
                "mode": mode,
                "label": label,
                "tone": "warning",
            }
        ],
    }


def dispatch(state, alerts, *, preferences, now=NOW, flush=False):
    messages = []

    def sender(**message):
        messages.append(message)
        return {"status": 1}

    state, result, logs = delivery._dispatch_state(
        state, alerts, prefs=preferences, now=now, flush=flush, sender=sender
    )
    return state, result, logs, messages


def test_summary_held_by_quiet_hours_is_delivered_next_morning():
    preferences = prefs()
    preferences["quiet"]["enabled"] = True
    preferences["summary"].update(time="22:45")
    state, _, _, _ = dispatch({}, [signal("verdict")], preferences=preferences)
    night = NOW.replace(hour=21, minute=45)  # 22:45 Berlin.
    state, _, _, messages = dispatch(state, [], preferences=preferences, now=night, flush=True)
    assert messages == []
    morning = (NOW + timedelta(days=1)).replace(hour=6, minute=0)  # 07:00 Berlin.
    state, result, _, messages = dispatch(
        state, [], preferences=preferences, now=morning, flush=True
    )
    assert len(messages) == 1
    assert result["sent"] == 1
    assert not state["pending"]


def test_secondary_criterion_does_not_supersede_a_distinct_verdict():
    preferences = prefs()
    state, _, _, _ = dispatch({}, [signal("verdict")], preferences=preferences)
    detail = signal("criterion", event_type="assessment_detail", label="CMF wieder erfüllt")
    state, _, _, _ = dispatch(
        state, [detail], preferences=preferences, now=NOW + timedelta(minutes=1)
    )
    assert {entry["id"] for entry in state["pending"]} == {"verdict:event", "criterion:event"}


def test_cached_quotes_do_not_bridge_a_stop_recovery_gap():
    policy = {"repeat": "recovery", "recovery_pct": 1, "recovery_minutes": 10}
    state = {"stop": 100, "triggered": True, "last_sent_at": NOW.isoformat()}
    item = {
        "identity": "be-position",
        "ticker": "BE",
        "name": "Bloom Energy",
        "price": 102,
        "stop": 100,
        "currency": "USD",
        "quote_at": NOW.isoformat(),
    }
    for minute in range(11):
        state, _ = stop_transition(state, item, NOW + timedelta(minutes=minute), preferences=policy)
    later = NOW + timedelta(minutes=11)
    state, _ = stop_transition(
        state, {**item, "quote_at": later.isoformat()}, later, preferences=policy
    )
    assert state["triggered"] is True


def test_direction_disabled_after_queueing_mutes_the_waiting_improvement():
    preferences = prefs()
    preferences["assessment"]["score_mode"] = "immediate"
    state, _, _, _ = dispatch(
        {}, [{"kind": "atr", "ticker": "BE", "alert_id": "first"}], preferences=preferences
    )
    improved = signal(
        "score",
        category="score",
        event_type="score",
        mode="immediate",
        label="Gesamtscore gestiegen",
    )
    improved["events"][0]["tone"] = "good"
    state, _, _, messages = dispatch(
        state, [improved], preferences=preferences, now=NOW + timedelta(minutes=1)
    )
    assert not messages
    preferences["assessment"]["notify_improvements"] = False
    state, _, logs, messages = dispatch(
        state, [], preferences=preferences, now=NOW + timedelta(minutes=31), flush=True
    )
    assert not messages
    assert not state["pending"]
    assert any(log["status"] == "suppressed" for log in logs)
