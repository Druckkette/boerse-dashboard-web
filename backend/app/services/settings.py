from __future__ import annotations

from app.repositories import settings as settings_repository
from app.repositories.settings import SettingsRepositoryUnavailable
from app.schemas import AppSettings, SettingsPatch


DEFAULT_SETTINGS = AppSettings(
    atr_threshold=1.5,
    risk_per_position_pct=1.0,
    target_risk_contribution=0.20,
    max_depot_loss_lower_pct=4.0,
    max_depot_loss_upper_pct=8.0,
    position_monitor_enabled=False,
    position_monitor_interval_minutes=5,
    position_monitor_threshold_atr=1.5,
    position_monitor_atr_period=21,
    position_monitor_lookback_days=120,
    position_monitor_cooldown_hours=12,
    position_monitor_reference="high_since_buy",
    pushover_enabled=False,
    pushover_configured=False,
    rs_rating_source="computed",
    data_jobs_enabled=True,
)


def get_app_settings() -> AppSettings:
    try:
        values = settings_repository.read_settings()
    except SettingsRepositoryUnavailable:
        values = {}
    return _settings_from_values(values)


def update_app_settings(payload: SettingsPatch) -> AppSettings:
    current = get_app_settings().model_dump()
    updates = payload.model_dump(exclude_none=True)
    current.update(updates)
    next_settings = _settings_from_values(current)
    try:
        persisted = settings_repository.write_settings(next_settings.model_dump())
    except SettingsRepositoryUnavailable:
        return next_settings
    return _settings_from_values(persisted)


def _settings_from_values(values: dict) -> AppSettings:
    merged = DEFAULT_SETTINGS.model_dump()
    merged.update({key: value for key, value in values.items() if key in merged})
    return AppSettings(**merged)
