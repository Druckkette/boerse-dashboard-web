from datetime import UTC, datetime, timedelta

from app.notification_preferences import NotificationPreferences
from app.services.notification_snapshot import snapshot_summary_entries


NOW = datetime(2026, 10, 29, 21, 45, tzinfo=UTC)


def observed():
    return {"NOW": {"observed_at": NOW.isoformat(),
                    "monitor": {"current_price": 90, "atr_value": 5, "distance_atr": 2, "threshold_atr": 1.5},
                    "trend_monitor": {"moving_averages": {"sma50": {"distance_pct": -5}}},
                    "stop_observation": {"price": 90, "stop": 91, "currency": "USD"},
                    "assessment": {"overall_score": 42, "verdict_label": "Beobachten"}}}


def test_observed_status_contains_real_current_risks_and_readable_prose():
    result = snapshot_summary_entries(observed(), NotificationPreferences().model_dump(), NOW)
    assert {entry["category"] for entry in result} == {"atr", "stop", "ma", "score", "verdict"}
    text = " ".join(entry["alert"]["events"][0]["label"] for entry in result)
    assert "weiterhin 2,0 ATR" in text and "50-Tage-Linie" in text
    assert all(operator not in text for operator in (">=", "<=", "→"))


def test_recovered_stale_disabled_or_already_reported_conditions_are_not_replayed():
    snapshots = observed()
    snapshots["NOW"]["monitor"]["distance_atr"] = 0.5
    snapshots["NOW"]["stop_observation"]["price"] = 95
    snapshots["NOW"]["trend_monitor"]["moving_averages"]["sma50"]["distance_pct"] = 2
    prefs = NotificationPreferences().model_dump()
    prefs["assessment"].update(score_mode="off", verdict_mode="off")
    assert snapshot_summary_entries(snapshots, prefs, NOW) == []
    snapshots = observed()
    snapshots["NOW"]["observed_at"] = (NOW - timedelta(days=2)).isoformat()
    assert snapshot_summary_entries(snapshots, prefs, NOW) == []
    prefs["summary"]["categories"] = ["atr"]
    assert snapshot_summary_entries(observed(), prefs, NOW, existing_entries=[{"ticker": "NOW", "category": "atr"}]) == []
