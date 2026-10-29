from copy import deepcopy

import pytest
from pydantic import ValidationError

from app.notification_preferences import NotificationPreferences
from app.schemas import AppSettings, SettingsPatch
from app.services import settings as service


@pytest.fixture
def settings_store(monkeypatch):
    store = {"position_monitor_enabled": True, "position_monitor_threshold_atr": 1.5}
    monkeypatch.setattr(service.settings_repository, "read_settings", lambda: deepcopy(store))
    monkeypatch.setattr(service, "get_runtime_config_value", lambda key: "")
    def save(values):
        store.clear()
        store.update(deepcopy(values))
        return deepcopy(store)
    monkeypatch.setattr(service.settings_repository, "write_settings", save)
    return store


def test_default_profile_selects_long_ma_breaks_only_and_digests_changes():
    prefs = NotificationPreferences()
    assert prefs.ma["sma10"].break_mode == prefs.ma["ema21"].break_mode == "digest"
    assert prefs.ma["sma50"].break_mode == prefs.ma["sma200"].break_mode == "immediate"
    assert all(rule.recovery_mode == rule.worsening_mode == "digest" for rule in prefs.ma.values())
    assert prefs.stop.repeat == prefs.atr.repeat == "daily"
    assert prefs.assessment.score_mode == prefs.assessment.verdict_mode == "digest"


def test_partial_nested_update_preserves_other_saved_choices_and_monitor(settings_store):
    service.update_app_settings(SettingsPatch(notification_preferences={
        "quiet": {"enabled": True, "start": "21:30"},
        "ma": {"ema21": {"break_mode": "immediate", "min_distance": 0.4}},
        "summary": {"time": "23:15"},
    }))
    result = service.update_app_settings(SettingsPatch(notification_preferences={
        "ma": {"sma50": {"recovery_mode": "off"}},
    }))
    prefs = result.notification_preferences
    assert prefs.ma["ema21"].break_mode == "immediate"
    assert prefs.ma["ema21"].min_distance == 0.4
    assert prefs.ma["sma50"].recovery_mode == "off"
    assert prefs.ma["sma200"].break_mode == "immediate"
    assert prefs.quiet.enabled and prefs.quiet.start == "21:30"
    assert prefs.summary.time == "23:15"
    assert result.position_monitor_enabled
    assert settings_store["notification_preferences"] == prefs.model_dump()


def test_legacy_opt_out_remains_off_and_calculation_monitor_remains_enabled(settings_store):
    settings_store.update(position_monitor_ma_alerts_enabled=False, position_monitor_assessment_alerts_enabled=False)
    result = service.get_app_settings()
    assert result.position_monitor_enabled
    assert all(rule.break_mode == rule.recovery_mode == rule.worsening_mode == "off"
               for rule in result.notification_preferences.ma.values())
    assert result.notification_preferences.assessment.score_mode == "off"
    assert result.notification_preferences.atr.mode == "immediate"


@pytest.mark.parametrize("patch", [
    {"timezone": "Not/A_Zone"},
    {"summary": {"time": "25:00"}},
    {"summary": {"categories": ["unknown"]}},
    {"ma": {"sma20": {"break_mode": "immediate"}}},
    {"ma": {"sma10": {"min_distance": float("nan")}}},
    {"stop": {"repeat_minutes": 0}},
    {"grouping": {"window_minutes": 0}},
    {"grouping": {"max_immediate_per_ticker_day": -1}},
    {"atr": {"mode": "disabled"}},
    {"unexpected": True},
])
def test_invalid_preferences_are_rejected(patch):
    with pytest.raises(ValidationError):
        SettingsPatch(notification_preferences=patch)


def test_recovery_and_escalation_thresholds_are_consistent_with_first_alarm():
    values = service.DEFAULT_SETTINGS.model_dump()
    values["notification_preferences"]["atr"].update(escalation_atr=1)
    with pytest.raises(ValidationError, match="Eskalation"):
        AppSettings.model_validate(values)
    values["notification_preferences"]["atr"].update(escalation_atr=3, repeat="recovery", recovery_atr=2)
    with pytest.raises(ValidationError, match="Erholungsschwelle"):
        AppSettings.model_validate(values)


def test_invalid_effective_threshold_patch_does_not_persist(settings_store):
    before = deepcopy(settings_store)
    with pytest.raises(ValidationError):
        service.update_app_settings(SettingsPatch(position_monitor_threshold_atr=4))
    assert settings_store == before


def test_legacy_high_atr_threshold_remains_readable(settings_store):
    settings_store["position_monitor_threshold_atr"] = 4
    result = service.get_app_settings()
    assert result.position_monitor_threshold_atr == 4
    assert result.notification_preferences.atr.escalation_atr == 8


def test_effective_validation_error_is_readable_in_dashboard(settings_store):
    from fastapi.testclient import TestClient
    from app.main import app
    response = TestClient(app).patch("/api/v1/settings", json={"position_monitor_threshold_atr": 4})
    assert response.status_code == 422
    assert response.json()["detail"] == "Die ATR-Eskalation muss über der ersten Warnschwelle liegen."
    assert "input_value" not in response.text
