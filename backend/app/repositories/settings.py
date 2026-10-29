from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.db.models import AppSetting
from app.db.session import SessionLocal


SETTINGS_KEY = "runtime"
RUNTIME_CONFIG_KEY = "runtime_config"
POSITION_MONITOR_STATE_KEY = "position_monitor_state"
PUSHOVER_DELIVERY_LOG_KEY = "pushover_delivery_log"
ATR_REARM_KEY = "notification_atr_rearm"


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


def patch_runtime_config(values: dict, clear_keys: list[str]) -> dict:
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT pg_advisory_xact_lock(hashtext('runtime_config'))"))
            row = db.get(AppSetting, RUNTIME_CONFIG_KEY)
            current = dict(row.value_json or {}) if row else {}
            for key in clear_keys:
                current.pop(key, None)
                if key == "NEON_DATABASE_URL":
                    current.pop("DATABASE_URL", None)
            current.update(values)
            if row is None:
                row = AppSetting(key=RUNTIME_CONFIG_KEY, description="Runtime integration configuration")
                db.add(row)
            row.value_json = current
            db.commit()
            return current
    except SQLAlchemyError as exc:
        raise SettingsRepositoryUnavailable(str(exc)) from exc


def read_position_monitor_state() -> dict:
    return _read_json_setting(POSITION_MONITOR_STATE_KEY)


def write_position_monitor_state(values: dict) -> dict:
    return _write_json_setting(
        POSITION_MONITOR_STATE_KEY,
        values,
        description="ATR position monitor cooldown and alert state.",
    )


def read_pushover_delivery_log() -> list[dict]:
    payload = _read_json_setting(PUSHOVER_DELIVERY_LOG_KEY)
    entries = payload.get("entries")
    return [dict(item) for item in entries if isinstance(item, dict)] if isinstance(entries, list) else []


def read_atr_rearm_requests() -> dict:
    return _read_json_setting(ATR_REARM_KEY)


def request_atr_rearm(ticker: str) -> dict:
    from datetime import UTC, datetime
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": ATR_REARM_KEY})
            row = db.get(AppSetting, ATR_REARM_KEY)
            values = dict(row.value_json or {}) if row is not None else {}
            values[ticker] = datetime.now(UTC).isoformat()
            # Requests are monotonic markers and need no destructive consumption.
            values = dict(sorted(values.items(), key=lambda item: item[1], reverse=True)[:500])
            if row is None:
                row = AppSetting(key=ATR_REARM_KEY, description="Explicit manual ATR notification rearm")
                db.add(row)
            row.value_json = values
            db.commit()
            return {"ok": True, "ticker": ticker, "count": 1}
    except SQLAlchemyError as exc:
        raise SettingsRepositoryUnavailable(str(exc)) from exc


def append_pushover_delivery_log(entries: list[dict], *, limit: int = 100) -> list[dict]:
    if not entries:
        return read_pushover_delivery_log()
    current = read_pushover_delivery_log()
    merged = [*entries, *current][: max(1, min(limit, 500))]
    stored = _write_json_setting(
        PUSHOVER_DELIVERY_LOG_KEY,
        {"entries": merged},
        description="Bounded Pushover ATR-monitor delivery history.",
    )
    raw = stored.get("entries")
    return [dict(item) for item in raw if isinstance(item, dict)] if isinstance(raw, list) else []


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
