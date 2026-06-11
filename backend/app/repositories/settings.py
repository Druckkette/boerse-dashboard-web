from __future__ import annotations

from sqlalchemy.exc import SQLAlchemyError

from app.db.models import AppSetting
from app.db.session import SessionLocal


SETTINGS_KEY = "runtime"


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
