from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from time import monotonic
from typing import Any, Literal

from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from redis import Redis
from redis.exceptions import RedisError
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import SQLAlchemyError

from app.core_config import get_settings
from app.db.session import engine
from app.schemas import SystemReadinessCheck, SystemReadinessResponse


def get_system_readiness() -> SystemReadinessResponse:
    checks: list[SystemReadinessCheck] = []
    db_connection: Connection | None = None

    try:
        db_check, db_connection = _check_database()
        checks.append(db_check)
        checks.append(_check_migrations(db_connection) if db_connection is not None else _migration_skipped_check())
    finally:
        if db_connection is not None:
            db_connection.close()

    checks.append(_check_redis())

    return SystemReadinessResponse(
        status=_overall_readiness(checks),
        generated_at=datetime.now(UTC),
        checks=checks,
    )


def _check_database() -> tuple[SystemReadinessCheck, Connection | None]:
    started = monotonic()
    try:
        connection = engine.connect()
        connection.execute(text("select 1"))
        return (
            SystemReadinessCheck(
                name="database",
                status="ok",
                required=True,
                detail="Postgres-Verbindung ist erreichbar.",
                latency_ms=_elapsed_ms(started),
                metadata={"dialect": engine.dialect.name},
            ),
            connection,
        )
    except (OSError, SQLAlchemyError) as exc:
        return (
            SystemReadinessCheck(
                name="database",
                status="error",
                required=True,
                detail=f"Datenbank nicht erreichbar: {_compact_error(exc)}",
                latency_ms=_elapsed_ms(started),
                metadata={"dialect": engine.dialect.name},
            ),
            None,
        )


def _check_migrations(connection: Connection) -> SystemReadinessCheck:
    started = monotonic()
    try:
        current_revision = MigrationContext.configure(connection).get_current_revision()
        script = ScriptDirectory.from_config(_alembic_config())
        head_revision = script.get_current_head()
        metadata: dict[str, Any] = {
            "current_revision": current_revision,
            "head_revision": head_revision,
        }

        if current_revision == head_revision:
            return SystemReadinessCheck(
                name="migrations",
                status="ok",
                required=True,
                detail="Datenbankschema ist auf Alembic Head.",
                latency_ms=_elapsed_ms(started),
                metadata=metadata,
            )

        status = "warning" if current_revision else "error"
        detail = (
            "Datenbank hat noch keine Alembic-Version."
            if current_revision is None
            else "Datenbankschema ist nicht auf Alembic Head."
        )
        return SystemReadinessCheck(
            name="migrations",
            status=status,
            required=True,
            detail=detail,
            latency_ms=_elapsed_ms(started),
            metadata=metadata,
        )
    except Exception as exc:  # Alembic raises mixed exception types around config/script errors.
        return SystemReadinessCheck(
            name="migrations",
            status="unknown",
            required=True,
            detail=f"Migrationsstatus konnte nicht geprüft werden: {_compact_error(exc)}",
            latency_ms=_elapsed_ms(started),
        )


def _check_redis() -> SystemReadinessCheck:
    started = monotonic()
    settings = get_settings()
    try:
        client = Redis.from_url(
            settings.redis_url,
            socket_connect_timeout=0.25,
            socket_timeout=0.25,
            retry_on_timeout=False,
        )
        client.ping()
        return SystemReadinessCheck(
            name="redis",
            status="ok",
            required=False,
            detail="Redis ist erreichbar.",
            latency_ms=_elapsed_ms(started),
            metadata={"url": _redact_url(settings.redis_url)},
        )
    except (OSError, RedisError) as exc:
        return SystemReadinessCheck(
            name="redis",
            status="warning",
            required=False,
            detail=f"Redis nicht erreichbar; API läuft weiter, Worker/Jobs sind eingeschränkt: {_compact_error(exc)}",
            latency_ms=_elapsed_ms(started),
            metadata={"url": _redact_url(settings.redis_url)},
        )


def _migration_skipped_check() -> SystemReadinessCheck:
    return SystemReadinessCheck(
        name="migrations",
        status="unknown",
        required=True,
        detail="Migrationsstatus übersprungen, weil die Datenbank nicht erreichbar ist.",
    )


def _overall_readiness(checks: list[SystemReadinessCheck]) -> Literal["ready", "degraded", "not_ready"]:
    required_checks = [check for check in checks if check.required]
    if any(check.status == "error" for check in required_checks):
        return "not_ready"
    if any(check.status in {"warning", "unknown"} for check in checks):
        return "degraded"
    return "ready"


def _alembic_config() -> Config:
    backend_dir = Path(__file__).resolve().parents[2]
    config = Config(str(backend_dir / "alembic.ini"))
    config.set_main_option("script_location", str(backend_dir / "alembic"))
    return config


def _elapsed_ms(started: float) -> int:
    return max(0, round((monotonic() - started) * 1000))


def _compact_error(exc: BaseException) -> str:
    message = str(exc).strip().replace("\n", " ")
    return message[:220] if message else exc.__class__.__name__


def _redact_url(url: str) -> str:
    if "@" not in url or "://" not in url:
        return url
    scheme, rest = url.split("://", 1)
    return f"{scheme}://***@{rest.split('@', 1)[1]}"
