from __future__ import annotations

from sqlalchemy.exc import SQLAlchemyError

from app.db.models import AppSetting
from app.db.session import SessionLocal


SETTINGS_KEY = "runtime"
RUNTIME_CONFIG_KEY = "runtime_config"
POSITION_MONITOR_STATE_KEY = "position_monitor_state"


class SettingsRepositoryUnavailable(RuntimeError):
    pass


def read_settings() -> dict:
    try:
        with SessionLocal() as db:
            row = db.get(AppSetting, SETTINGS_KEY)
            return dict(row.value_json or {}) if row is not None else {}
    except SQLAlchemyError as exc:
        raise SettingsRepositoryUnavailable(str(exc)) from exc


def write_settings(values: dict) -> dict:
    try:
        with SessionLocal() as db:
            row = db.get(AppSetting, SETTINGS_KEY)
            if row is None:
                row = AppSetting(
                    key=SETTINGS_KEY,
                    value_json=dict(values),
                    description="Runtime settings edited through the web UI.",
                )
                db.add(row)
            else:
                row.value_json = dict(values)
            db.commit()
            return dict(row.value_json or {})
    except SQLAlchemyError as exc:
        raise SettingsRepositoryUnavailable(str(exc)) from exc


def read_runtime_config() -> dict:
    return _read_json_setting(RUNTIME_CONFIG_KEY)


def write_runtime_config(values: dict) -> dict:
    return _write_json_setting(
        RUNTIME_CONFIG_KEY,
        values,
        description="Runtime API keys and integration config edited through the setup UI.",
    )


def read_position_monitor_state() -> dict:
    return _read_json_setting(POSITION_MONITOR_STATE_KEY)


def write_position_monitor_state(values: dict) -> dict:
    return _write_json_setting(
        POSITION_MONITOR_STATE_KEY,
        values,
        description="ATR position monitor cooldown and alert state.",
    )


def _read_json_setting(key: str) -> dict:
    try:
        with SessionLocal() as db:
            row = db.get(AppSetting, key)
            return dict(row.value_json or {}) if row is not None else {}
    except SQLAlchemyError as exc:
        raise SettingsRepositoryUnavailable(str(exc)) from exc


def _write_json_setting(key: str, values: dict, *, description: str) -> dict:
    try:
        with SessionLocal() as db:
            row = db.get(AppSetting, key)
            if row is None:
                row = AppSetting(
                    key=key,
                    value_json=dict(values),
                    description=description,
                )
                db.add(row)
            else:
                row.value_json = dict(values)
                row.description = description
            db.commit()
            return dict(row.value_json or {})
    except SQLAlchemyError as exc:
        raise SettingsRepositoryUnavailable(str(exc)) from exc
