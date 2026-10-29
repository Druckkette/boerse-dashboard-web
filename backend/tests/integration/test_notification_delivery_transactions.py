"""Real durable routing transactions; Pushover is always replaced with a fake."""

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from time import sleep

import pytest
from sqlalchemy import create_engine, delete, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.db.models import AppSetting
from app.notification_preferences import NotificationPreferences
from app.services import notification_delivery as delivery, settings, stop_alerts
from app.schemas import AppSettings
from app.services.settings import DEFAULT_SETTINGS

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_POSTGRES_URL"), reason="Disposable Postgres not configured"
)
NOW = datetime(2026, 10, 29, 15, tzinfo=UTC)


@pytest.fixture
def store(monkeypatch):
    url = os.environ["TEST_POSTGRES_URL"]
    assert make_url(url).database == "audit_tests"
    engine = create_engine(url)
    sessions = sessionmaker(bind=engine, autoflush=False)
    monkeypatch.setattr(delivery, "SessionLocal", sessions)
    monkeypatch.setattr(stop_alerts, "SessionLocal", sessions)
    monkeypatch.setattr(settings, "get_runtime_config_value", lambda key: "fake-test-credential")
    monkeypatch.setattr(settings, "get_runtime_config_bool", lambda *args: False)
    with sessions() as db:
        db.execute(
            delete(AppSetting).where(
                AppSetting.key.in_(
                    [delivery.STATE_KEY, delivery.LOG_KEY, "stop_alert:notification-integration"]
                )
            )
        )
        db.commit()
    yield sessions
    with sessions() as db:
        db.execute(
            delete(AppSetting).where(
                AppSetting.key.in_(
                    [delivery.STATE_KEY, delivery.LOG_KEY, "stop_alert:notification-integration"]
                )
            )
        )
        db.commit()
    engine.dispose()


def configured(**changes) -> AppSettings:
    prefs = NotificationPreferences().model_dump()
    for key, value in changes.items():
        prefs[key].update(value)
    return DEFAULT_SETTINGS.model_copy(
        update={
            "pushover_enabled": True,
            "notification_preferences": NotificationPreferences.model_validate(prefs),
        }
    )


def item(identifier="event"):
    return {
        "kind": "atr",
        "ticker": "NTEST",
        "alert_id": identifier,
        "current_price": 90,
        "reference_price": 100,
        "distance_atr": 2,
        "threshold_atr": 1.5,
    }


def test_concurrent_workers_accept_and_deliver_only_once(store):
    messages = []

    def provider(**kwargs):
        messages.append(kwargs)
        sleep(0.05)
        return {"status": 1}

    def dispatch(_):
        return delivery.deliver_notifications(
            [item()], app_settings=configured(), now=NOW, send_message=provider
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(dispatch, range(2)))
    assert len(messages) == 1
    assert sum(result["sent"] for result in results) == 1
    assert all(result["accepted_alert_ids"] == ["event"] for result in results)
    with store() as db:
        row = db.get(AppSetting, delivery.STATE_KEY)
        assert len(row.value_json["seen"]) == 1 and not row.value_json["pending"]


def test_restart_flush_uses_database_queue_and_disabled_policy_cancels(store, monkeypatch):
    messages = []

    def provider(**kwargs):
        messages.append(kwargs)
        return {"status": 1}

    prefs = configured(atr={"mode": "digest"})
    result = delivery.deliver_notifications(
        [item()], app_settings=prefs, now=NOW, send_message=provider
    )
    assert result["accepted_alert_ids"] == ["event"] and not messages
    # Recreate the session factory, as in a newly started worker.
    monkeypatch.setattr(
        delivery, "SessionLocal", sessionmaker(bind=store.kw["bind"], autoflush=False)
    )
    result = delivery.flush_notifications(
        app_settings=prefs, now=NOW.replace(hour=22), send_message=provider
    )
    assert result["sent"] == 1 and len(messages) == 1
    delivery.deliver_notifications(
        [item("muted")], app_settings=prefs, now=NOW + timedelta(days=1), send_message=provider
    )
    result = delivery.flush_notifications(
        app_settings=configured(atr={"mode": "off"}),
        now=NOW + timedelta(days=1),
        send_message=provider,
    )
    assert result["sent"] == 0 and len(messages) == 1
    with store() as db:
        assert not db.get(AppSetting, delivery.STATE_KEY).value_json["pending"]
        assert any(
            row["status"] == "suppressed"
            for row in db.get(AppSetting, delivery.LOG_KEY).value_json["entries"]
        )


def test_manual_rearm_changes_only_matching_position_cycle_and_queued_latches(store):
    observation = {
        "identity": "notification-integration",
        "ticker": "NTEST",
        "name": "Test",
        "price": 90,
        "stop": 100,
        "currency": "EUR",
        "quote_at": NOW.isoformat(),
    }
    accepted = []

    def queue(alerts):
        accepted.extend(alerts)
        return {"accepted_alert_ids": [alert["alert_id"] for alert in alerts], "sent_alert_ids": []}

    result = stop_alerts.deliver_stop_alerts(
        [observation], queue, now=NOW, preferences={"repeat": "manual"}
    )
    assert result["accepted"] == 1 and result["sent"] == 0
    stop_alerts.deliver_stop_alerts([observation], queue, now=NOW, preferences={"repeat": "manual"})
    assert len(accepted) == 1
    assert stop_alerts.rearm_stop_alerts("OTHER")["count"] == 0
    assert stop_alerts.rearm_stop_alerts("ntest")["count"] == 1
    stop_alerts.deliver_stop_alerts([observation], queue, now=NOW, preferences={"repeat": "manual"})
    assert len(accepted) == 2 and accepted[0]["alert_id"] != accepted[1]["alert_id"]
    with store() as db:
        rows = list(
            db.scalars(
                select(AppSetting).where(AppSetting.key == "stop_alert:notification-integration")
            )
        )
        assert len(rows) == 1 and rows[0].value_json["triggered"]


def test_combined_dispatch_runs_on_empty_stop_tick_and_preserves_stop_legacy(store):
    calls = []

    def sender(alerts):
        calls.append(alerts)
        return {"accepted_alert_ids": []}

    stop_alerts.deliver_stop_alerts([], sender, now=NOW, additional_alerts=[])
    assert calls == [[]]
    stop_alerts.deliver_stop_alerts([], sender, now=NOW)
    assert calls == [[]]  # Legacy standalone stop calls do not dispatch empty data.
