"""Policy tests use an in-memory state and a fake provider, never Pushover."""

import copy
from datetime import UTC, datetime, timedelta

import pytest

from app.services import notification_delivery as delivery

NOW = datetime(2026, 10, 29, 15, 0, tzinfo=UTC)


def preferences():
    return {
        "version": 1,
        "timezone": "Europe/Berlin",
        "ma": {
            "sma10": {
                "break_mode": "immediate",
                "recovery_mode": "digest",
                "worsening_mode": "digest",
                "max_per_day": 1,
                "priority": 0,
                "session": "all",
            }
        },
        "stop": {"mode": "immediate", "priority": 1, "session": "all"},
        "atr": {"mode": "immediate", "priority": 1, "session": "all"},
        "assessment": {
            "score_mode": "digest",
            "verdict_mode": "digest",
            "priority": 0,
            "session": "all",
        },
        "grouping": {
            "enabled": True,
            "window_minutes": 30,
            "max_immediate_per_ticker_day": 3,
            "stop_bypass": True,
            "atr_escalation_bypass": True,
        },
        "summary": {
            "enabled": True,
            "time": "22:45",
            "categories": ["ma", "score", "verdict", "stop", "atr"],
            "include_sent": False,
            "only_changes": True,
            "max_tickers": 5,
            "priority": 0,
        },
        "quiet": {
            "enabled": False,
            "start": "22:00",
            "end": "07:00",
            "stop_bypass": True,
            "atr_escalation_bypass": True,
        },
        "custom_session": {"start": "08:00", "end": "22:00"},
    }


def alert(identifier="one", ticker="TEST", kind="atr", **extra):
    return {"alert_id": identifier, "ticker": ticker, "kind": kind, **extra}


def signal(identifier="one", mode="immediate", **event):
    return alert(
        identifier,
        kind="stock_signal",
        events=[
            {
                "category": "ma",
                "event_type": "ma_break",
                "ma_key": "sma10",
                "mode": mode,
                "label": "10-SMA unterschritten",
                **event,
            }
        ],
    )


@pytest.fixture(autouse=True)
def simple_formatter(monkeypatch):
    monkeypatch.setattr(
        delivery,
        "_format_alert",
        lambda item: (
            f"Hinweis {item['ticker']}",
            f"{item['ticker']}: neuer Hinweis {item.get('alert_id', '')}",
        ),
    )
    monkeypatch.setattr(delivery, "_regular_session", lambda ticker, now: True)


def run(state, alerts=(), *, prefs=None, now=NOW, sender=None, flush=False):
    sent = []

    def fake_sender(**message):
        sent.append(message)
        return {"status": 1}

    value, result, logs = delivery._dispatch_state(
        state,
        list(alerts),
        prefs=prefs or preferences(),
        now=now,
        sender=sender or fake_sender,
        flush=flush,
    )
    return value, result, logs, sent


def test_same_ticker_alerts_merge_and_durable_acceptance_deduplicates():
    state, result, logs, messages = run(
        {}, [alert("atr"), alert("stop", kind="stop"), signal("ma")]
    )
    assert result["sent"] == 1 == len(messages)
    assert messages[0]["priority"] == 1
    assert set(result["accepted_alert_ids"]) == {"atr", "stop", "ma"}
    assert len(logs) == 3 and all(row["status"] == "sent" for row in logs)
    _, repeated, _, more = run(state, [alert("atr"), alert("stop", kind="stop"), signal("ma")])
    assert more == [] and repeated["accepted_alert_ids"] == ["atr", "stop", "ma"]


def test_followup_waits_then_flushes_without_new_quote():
    state, _, _, _ = run({}, [signal("first")])
    state, result, logs, messages = run(state, [alert("second")], now=NOW + timedelta(minutes=1))
    assert messages == [] and result["accepted_alert_ids"] == ["second"]
    assert logs[0]["status"] == "queued"
    assert "second" in logs[0]["message"]
    state, result, _, messages = run(state, now=NOW + timedelta(minutes=31), flush=True)
    assert result["sent"] == 1 and len(messages) == 1 and not state["pending"]


def test_daily_cap_holds_normal_alert_but_stop_and_escalation_bypass():
    prefs = preferences()
    prefs["grouping"].update(max_immediate_per_ticker_day=1, window_minutes=0)
    state, _, _, _ = run({}, [alert("first")], prefs=prefs)
    state, result, _, messages = run(
        state, [alert("ordinary")], prefs=prefs, now=NOW + timedelta(minutes=1)
    )
    assert not messages and result["queued"] == 1
    state, result, _, messages = run(
        state,
        [alert("stop", kind="stop"), alert("escalation", reason="escalation")],
        prefs=prefs,
        now=NOW + timedelta(minutes=2),
    )
    assert len(messages) == 1 and set(result["sent_alert_ids"]) == {"stop", "escalation"}
    assert [entry["id"] for entry in state["pending"]] == ["ordinary"]


def test_quiet_hours_and_session_preserve_events_until_allowed(monkeypatch):
    prefs = preferences()
    prefs["quiet"]["enabled"] = True
    night = NOW.replace(hour=22)
    state, result, _, messages = run({}, [signal()], prefs=prefs, now=night)
    assert not messages and result["accepted_alert_ids"] == ["one"]
    state, result, _, messages = run(state, prefs=prefs, now=NOW + timedelta(days=1), flush=True)
    assert len(messages) == 1 and not state["pending"]
    prefs["ma"]["sma10"]["session"] = "regular"
    monkeypatch.setattr(delivery, "_regular_session", lambda ticker, now: False)
    state, _, _, messages = run({}, [signal("closed")], prefs=prefs)
    assert not messages and len(state["pending"]) == 1


def test_per_ma_daily_limit_does_not_prevent_other_categories():
    prefs = preferences()
    prefs["grouping"]["window_minutes"] = 0
    state, _, _, _ = run(
        {}, [signal("first", limit_key="ma:TEST:sma10", max_per_day=1)], prefs=prefs
    )
    state, result, _, messages = run(
        state,
        [signal("second", limit_key="ma:TEST:sma10", max_per_day=1), alert("atr")],
        prefs=prefs,
        now=NOW + timedelta(minutes=1),
    )
    assert result["sent_alert_ids"] == ["atr"] and len(messages) == 1
    assert state["pending"][0]["cap_held"] == "2026-10-29"


def test_digest_off_and_mixed_modes_accept_whole_parent_without_immediate_push():
    prefs = preferences()
    prefs["ma"]["sma10"]["break_mode"] = "off"
    item = signal()
    item["events"].append(
        {
            "category": "score",
            "event_type": "score",
            "label": "Gesamtscore verbessert",
            "mode": "digest",
        }
    )
    state, result, logs, messages = run({}, [item], prefs=prefs)
    assert not messages and result["accepted_alert_ids"] == ["one"]
    assert {row["status"] for row in logs} == {"suppressed", "digest"}
    assert len(state["pending"]) == 1


def test_summary_honours_schedule_once_categories_and_max_tickers():
    prefs = preferences()
    prefs["summary"]["max_tickers"] = 1
    prefs["atr"]["mode"] = "digest"
    state, _, _, _ = run({}, [alert("one", ticker="AAA"), alert("two", ticker="BBB")], prefs=prefs)
    state, _, _, messages = run(state, prefs=prefs, now=NOW.replace(hour=21, minute=44), flush=True)
    assert not messages
    state, result, logs, messages = run(
        state, prefs=prefs, now=NOW.replace(hour=21, minute=45), flush=True
    )
    assert result["sent"] == 1 and "Eine weitere Aktie" in messages[0]["message"]
    assert not state["pending"] and logs[-1]["priority"] == 0
    _, _, _, messages = run(state, prefs=prefs, now=NOW.replace(hour=21, minute=46), flush=True)
    assert not messages


def test_empty_summary_only_changes_and_include_sent():
    prefs = preferences()
    state, _, logs, messages = run({}, prefs=prefs, now=NOW.replace(hour=22), flush=True)
    assert not messages and logs[-1]["status"] == "skipped"
    prefs["summary"].update(only_changes=False)
    _, _, _, messages = run({}, prefs=prefs, now=NOW.replace(hour=22), flush=True)
    assert "keine neuen" in messages[0]["message"]
    prefs["summary"].update(only_changes=True, include_sent=True)
    state, _, _, _ = run({}, [alert()], prefs=prefs)
    _, _, _, messages = run(state, prefs=prefs, now=NOW.replace(hour=22), flush=True)
    assert "TEST" in messages[0]["message"]


def test_failed_provider_keeps_accepted_event_and_retries_with_backoff():
    attempts = []

    def fail(**kwargs):
        attempts.append(kwargs)
        raise TimeoutError("simulated provider timeout")

    state, result, logs, _ = run({}, [alert()], sender=fail)
    assert result["failed"] == 1 and result["accepted_alert_ids"] == ["one"]
    assert len(state["pending"]) == 1 and logs[-1]["status"] == "failed"
    _, _, _, _ = run(state, now=NOW + timedelta(minutes=1), sender=fail, flush=True)
    assert len(attempts) == 1
    state, result, _, messages = run(state, now=NOW + timedelta(minutes=5), flush=True)
    assert len(messages) == 1 and result["sent"] == 1 and not state["pending"]


def test_preference_changes_apply_to_already_queued_events():
    prefs = preferences()
    prefs["atr"]["mode"] = "digest"
    state, _, _, _ = run({}, [alert()], prefs=prefs)
    prefs["atr"]["mode"] = "off"
    state, _, logs, messages = run(state, prefs=prefs, flush=True)
    assert not messages and not state["pending"]
    assert logs[-1]["status"] == "suppressed"


def test_state_and_input_are_not_mutated():
    state, items = {"pending": []}, [alert()]
    before = copy.deepcopy((state, items))
    run(state, items)
    assert (state, items) == before


def test_monitor_day_cap_does_not_reset_at_midnight():
    prefs = preferences()
    prefs["grouping"].update(max_immediate_per_ticker_day=1, window_minutes=0)
    night = NOW.replace(hour=22)
    state, _, _, _ = run({}, [alert("first")], prefs=prefs, now=night)
    state, result, _, messages = run(
        state, [alert("midnight")], prefs=prefs, now=night + timedelta(hours=2)
    )
    assert not messages and result["queued"] == 1
    state, result, _, messages = run(
        state, prefs=prefs, now=NOW.replace(hour=7) + timedelta(days=1), flush=True
    )
    assert not messages and result["sent"] == 0
    # The new day allows a genuinely new alert, never a delayed old cap event.
    state, result, _, messages = run(
        state, [alert("new-day")], prefs=prefs,
        now=NOW.replace(hour=7, minute=1) + timedelta(days=1),
    )
    assert len(messages) == 1 and result["sent"] == 1


def test_new_recovery_replaces_queued_ma_break_and_session_holds_become_digest(monkeypatch):
    prefs = preferences()
    prefs["ma"]["sma10"]["session"] = "regular"
    monkeypatch.setattr(delivery, "_regular_session", lambda ticker, now: False)
    state, _, _, messages = run({}, [signal("break")], prefs=prefs)
    assert not messages and state["pending"][0]["mode"] == "digest"
    state, result, logs, messages = run(
        state,
        [signal("recovery", event_type="ma_recovery", label="10-SMA zurückerobert")],
        prefs=prefs,
        now=NOW + timedelta(minutes=1),
    )
    assert not messages and result["accepted_alert_ids"] == ["recovery"]
    assert [entry["parent_id"] for entry in state["pending"]] == ["recovery"]
    assert any("neuere Entwicklung" in row["detail"] for row in logs)
    monkeypatch.setattr(delivery, "_regular_session", lambda ticker, now: True)
    _, _, _, messages = run(state, prefs=prefs, now=NOW + timedelta(days=1), flush=True)
    assert not messages  # The historical break cannot appear tomorrow as an immediate warning.


def test_zero_caps_are_unlimited_and_disabled_grouping_still_enforces_nonzero_cap():
    prefs = preferences()
    prefs["grouping"].update(enabled=False, max_immediate_per_ticker_day=0)
    prefs["ma"]["sma10"]["max_per_day"] = 0
    state, result, _, messages = run(
        {}, [signal("first", limit_key="ma:TEST:sma10"), alert("second")], prefs=prefs
    )
    assert len(messages) == 2 and result["sent"] == 2
    state, result, _, messages = run(
        state,
        [signal("third", limit_key="ma:TEST:sma10")],
        prefs=prefs,
        now=NOW + timedelta(minutes=1),
    )
    assert len(messages) == 1 and result["sent"] == 1
    prefs["grouping"]["max_immediate_per_ticker_day"] = 1
    state, result, _, messages = run({}, [alert("a"), alert("b")], prefs=prefs)
    assert len(messages) == 1 and len(state["pending"]) == 1


def test_detector_direction_filters_and_secondary_details_stay_muted_or_digest():
    prefs = preferences()
    prefs["assessment"]["verdict_mode"] = "immediate"
    muted = signal("muted", mode="off", suppression_reason="direction_disabled")
    detail = signal("detail", category="verdict", event_type="assessment_detail", mode="digest")
    state, result, logs, messages = run({}, [muted, detail], prefs=prefs)
    assert not messages and result["accepted_alert_ids"] == ["muted", "detail"]
    assert len(state["pending"]) == 1 and state["pending"][0]["mode"] == "digest"
    assert any(row["status"] == "suppressed" for row in logs)


def test_only_fresh_observations_replace_snapshot():
    observation = {
        "ticker": "TEST",
        "monitor": {"quote_at": NOW.isoformat(), "current_price": 90},
        "trend_monitor": {"moving_averages": {}},
        "stop_observation": {"price": 90, "stop": 100},
    }
    state, _, _ = delivery._dispatch_state(
        {},
        [],
        prefs=preferences(),
        now=NOW,
        sender=lambda **kwargs: {"status": 1},
        observations=[observation],
    )
    assert state["latest_observations"]["TEST"]["monitor"]["current_price"] == 90
    observation["monitor"]["current_price"] = 50
    state, _, _ = delivery._dispatch_state(
        state,
        [],
        prefs=preferences(),
        now=NOW + timedelta(hours=1),
        sender=lambda **kwargs: {"status": 1},
        observations=[observation],
    )
    assert state["latest_observations"]["TEST"]["monitor"]["current_price"] == 90


def test_quiet_summary_preserves_due_date_and_does_not_misdate_next_day_events():
    prefs = preferences()
    prefs["quiet"]["enabled"] = True
    prefs["atr"]["mode"] = "digest"
    state, _, _, _ = run({}, [alert("yesterday", ticker="AAA")], prefs=prefs)
    state, _, _, messages = run(state, prefs=prefs, now=NOW.replace(hour=21, minute=45), flush=True)
    assert not messages and state["summary_waiting"]["date"] == "2026-10-29"
    morning = (NOW + timedelta(days=1)).replace(hour=6, minute=0)  # 07:00 Berlin
    state, _, _, _ = run(state, [alert("today", ticker="BBB")], prefs=prefs, now=morning)
    state, result, _, messages = run(state, prefs=prefs, now=morning, flush=True)
    assert result["sent"] == 1 and "29.10.2026" in messages[0]["message"]
    assert "AAA" in messages[0]["message"] and "BBB" not in messages[0]["message"]
    assert [entry["id"] for entry in state["pending"]] == ["today"]
    prefs["quiet"]["enabled"] = False
    state, _, _, messages = run(
        state, prefs=prefs, now=morning.replace(hour=21, minute=45), flush=True
    )
    assert "30.10.2026" in messages[0]["message"] and "BBB" in messages[0]["message"]
    assert not state["pending"]


def test_weekend_does_not_start_an_extra_monitor_day():
    friday = datetime(2026, 10, 30, 16, tzinfo=UTC)
    assert delivery._monitor_day(friday) == "2026-10-30"
    assert delivery._monitor_day(friday + timedelta(days=1)) == "2026-10-30"
    assert delivery._monitor_day(friday + timedelta(days=2)) == "2026-10-30"
    assert delivery._monitor_day(friday + timedelta(days=3)) == "2026-11-02"
