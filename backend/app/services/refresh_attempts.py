"""Persistent, bounded retry history; unresolved symbols must not starve the universe."""
from datetime import UTC, datetime, timedelta

from app.repositories.settings import _read_json_setting, _write_json_setting, SettingsRepositoryUnavailable
from app.db.models import AppSetting
from app.db.session import SessionLocal
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

KEY = "fundamental_attempt:"


def read_attempts() -> dict:
    try:
        with SessionLocal() as db:
            rows = db.scalars(select(AppSetting).where(AppSetting.key.startswith(KEY))).all()
            return {row.key[len(KEY):]: row.value_json for row in rows}
    except SQLAlchemyError:
        return {}


def record_attempt(ticker: str, *, error: str | None = None) -> None:
    now = datetime.now(UTC)
    try:
        previous = _read_json_setting(KEY + ticker)
    except SettingsRepositoryUnavailable:
        previous = {}
    failures = int(previous.get("failures", 0)) + 1 if error else 0
    delay = min(168, 6 * 2 ** min(failures, 5)) if error else 6
    attempt = {
        "last_attempt": now.isoformat(),
        "next_attempt": (now + timedelta(hours=delay)).isoformat(),
        "failures": failures,
        "error": (error or "")[:300],
    }
    try:
        _write_json_setting(KEY + ticker, attempt, description="Fundamental retry history and fair scheduling")
    except SettingsRepositoryUnavailable:
        # A failed checkpoint must never mark provider work as completed.
        pass


def retry_due(attempt: dict, now: datetime) -> bool:
    try:
        return datetime.fromisoformat(attempt["next_attempt"]) <= now
    except (KeyError, TypeError, ValueError):
        return True
