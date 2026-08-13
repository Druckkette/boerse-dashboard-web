from __future__ import annotations

import os
import re
import socket
import subprocess
import threading
import time
from datetime import UTC, datetime
from json import dumps, loads
from pathlib import Path
from typing import Any

import requests
from sqlalchemy import create_engine, text

from app.core_config import get_settings
from app.data_sources.fmp_client import FMP_PROFILE_URL, compact_fmp_response_body, is_non_empty_fmp_payload
from app.repositories import settings as settings_repository
from app.repositories.settings import SettingsRepositoryUnavailable
from app.schemas import (
    AppSettings,
    DataDiagnosticsResponse,
    DatabaseTargetResponse,
    DatabaseTargetSwitchRequest,
    RuntimeConfigItem,
    RuntimeConfigPatch,
    RuntimeConfigResponse,
    RuntimeConfigTestRequest,
    RuntimeConfigTestResponse,
    RuntimeServicesRestartResponse,
    SettingsPatch,
)


DEFAULT_SETTINGS = AppSettings(
    atr_threshold=1.5,
    risk_per_position_pct=1.0,
    target_risk_contribution=0.20,
    max_depot_loss_lower_pct=4.0,
    max_depot_loss_upper_pct=8.0,
    position_monitor_enabled=False,
    position_monitor_interval_minutes=1,
    position_monitor_threshold_atr=1.5,
    position_monitor_atr_period=14,
    position_monitor_lookback_days=420,
    position_monitor_cooldown_hours=18,
    position_monitor_reference="previous_close",
    position_monitor_ma_alerts_enabled=True,
    position_monitor_assessment_alerts_enabled=True,
    position_monitor_assessment_interval_minutes=15,
    pushover_enabled=False,
    pushover_configured=False,
    rs_rating_source="computed",
    data_jobs_enabled=True,
)


RUNTIME_CONFIG_DEFINITIONS: dict[str, dict[str, Any]] = {
    "SEC_USER_AGENT": {
        "label": "SEC User Agent",
        "category": "external_api",
        "description": "Pflicht für SEC/13F-Jobs und SEC Company Facts. Format: '<project> <contact-email>'.",
        "secret": True,
        "editable": True,
        "restart_required": False,
        "runtime_applied": True,
        "placeholder": "boerse-dashboard-web name@example.com",
        "attr": "sec_user_agent",
    },
    "FMP_API_KEY": {
        "label": "Financial Modeling Prep API Key",
        "category": "external_api",
        "description": "Optional für tiefere Fundamental-Daten im Fundamentals-Worker.",
        "secret": True,
        "editable": True,
        "restart_required": False,
        "runtime_applied": True,
        "placeholder": "FMP API Key",
        "attr": "fmp_api_key",
    },
    "PUSHOVER_USER_KEY": {
        "label": "Pushover User Key",
        "category": "notifications",
        "description": "Optional für Alert-Zustellung aus Worker-Jobs.",
        "secret": True,
        "editable": True,
        "restart_required": False,
        "runtime_applied": True,
        "placeholder": "Pushover User Key",
        "attr": "pushover_user_key",
    },
    "PUSHOVER_APP_TOKEN": {
        "label": "Pushover App Token",
        "category": "notifications",
        "description": "Optionales App Token für Pushover-Test und spätere Alerts.",
        "secret": True,
        "editable": True,
        "restart_required": False,
        "runtime_applied": True,
        "placeholder": "Pushover App Token",
        "attr": "pushover_app_token",
    },
    "PUSHOVER_DRY_RUN": {
        "label": "Pushover Dry Run",
        "category": "notifications",
        "description": "Wenn aktiv, prüft der Testjob die Konfiguration ohne Nachricht zu senden.",
        "secret": False,
        "editable": True,
        "restart_required": False,
        "runtime_applied": True,
        "placeholder": "0 oder 1",
    },
    "NEON_DATABASE_URL": {
        "label": "Neon DATABASE_URL",
        "category": "database",
        "description": "Optionale Neon-Verbindung. Speichern und Testen schaltet nicht um; die aktive Datenbank wird separat gewählt.",
        "secret": True,
        "editable": True,
        "restart_required": True,
        "runtime_applied": False,
        "placeholder": "postgresql+psycopg://...",
    },
    "DATABASE_URL": {
        "label": "Aktive DATABASE_URL",
        "category": "database",
        "description": "Interner aktiver Datenbankwert; wird über den lokalen/Neon-Schalter erzeugt.",
        "secret": True,
        "editable": False,
        "restart_required": True,
        "runtime_applied": False,
        "placeholder": "postgresql+psycopg://...",
        "attr": "database_url",
        "visible": False,
    },
    "POSTGRES_PASSWORD": {
        "label": "Postgres Passwort",
        "category": "database",
        "description": "Bootstrap-Wert für den lokalen Postgres-Container; wird von Docker Compose gelesen.",
        "secret": True,
        "editable": False,
        "restart_required": True,
        "runtime_applied": False,
        "placeholder": "langes Passwort",
        "visible": False,
    },
    "REDIS_URL": {
        "label": "Redis URL",
        "category": "database",
        "description": "Bootstrap-Wert für Backend, Worker und Scheduler.",
        "secret": False,
        "editable": False,
        "restart_required": True,
        "runtime_applied": False,
        "placeholder": "redis://redis:6379/0",
        "attr": "redis_url",
        "visible": False,
    },
    "APP_AUTH_ENABLED": {
        "label": "Frontend Basic Auth aktiv",
        "category": "security",
        "description": "Aktiviert den Passwortschutz vor dem Dashboard. Änderung greift nach Frontend-Neustart.",
        "secret": False,
        "editable": True,
        "restart_required": True,
        "runtime_applied": False,
        "placeholder": "0 oder 1",
    },
    "APP_AUTH_USER": {
        "label": "Frontend Auth User",
        "category": "security",
        "description": "Benutzername für den Dashboard-Passwortschutz. Änderung greift nach Frontend-Neustart.",
        "secret": True,
        "editable": True,
        "restart_required": True,
        "runtime_applied": False,
        "placeholder": "boerse",
    },
    "APP_AUTH_PASSWORD": {
        "label": "Frontend Auth Passwort",
        "category": "security",
        "description": "Passwort für den Dashboard-Passwortschutz. Änderung greift nach Frontend-Neustart.",
        "secret": True,
        "editable": True,
        "restart_required": True,
        "runtime_applied": False,
        "placeholder": "langes Passwort",
    },
    "GHCR_OWNER": {
        "label": "GHCR Owner",
        "category": "deployment",
        "description": "Docker-Compose-Bootstrap-Wert für Image-Namen.",
        "secret": False,
        "editable": False,
        "restart_required": True,
        "runtime_applied": False,
        "placeholder": "druckkette",
        "visible": False,
    },
    "IMAGE_TAG": {
        "label": "Docker Image Tag",
        "category": "deployment",
        "description": "Docker-Compose-Bootstrap-Wert für Rollback/Pinning, z. B. latest oder Commit-SHA.",
        "secret": False,
        "editable": False,
        "restart_required": True,
        "runtime_applied": False,
        "placeholder": "latest",
        "visible": False,
    },
}


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


def get_runtime_config() -> RuntimeConfigResponse:
    stored = _read_runtime_config()
    return _runtime_config_response(stored)


def _runtime_config_response(stored: dict) -> RuntimeConfigResponse:
    visible_definitions = {
        key: definition
        for key, definition in RUNTIME_CONFIG_DEFINITIONS.items()
        if bool(definition.get("visible", True))
    }
    items = [_runtime_config_item(key, definition, stored) for key, definition in visible_definitions.items()]
    return RuntimeConfigResponse(
        items=items,
        editable_keys=[item.key for item in items if item.editable],
        bootstrap_keys=[item.key for item in items if not item.editable and item.restart_required],
        note=(
            "API- und Secret-Werte werden in Postgres gespeichert und in eine persistente Runtime-Env-Datei gespiegelt. "
            "Security-Werte und Neon/Postgres werden vorbereitet; sie greifen nach dem Neustart der betroffenen Container."
        ),
    )


def update_runtime_config(payload: RuntimeConfigPatch) -> RuntimeConfigResponse:
    stored = _read_runtime_config()
    editable = {key for key, definition in RUNTIME_CONFIG_DEFINITIONS.items() if bool(definition.get("editable"))}
    for key in payload.clear_keys:
        if key in editable:
            stored.pop(key, None)
            if key == "NEON_DATABASE_URL":
                stored.pop("DATABASE_URL", None)
    for key, raw_value in payload.values.items():
        if key not in editable:
            continue
        value = str(raw_value).strip()
        if value:
            stored[key] = value
    try:
        settings_repository.write_runtime_config(stored)
    except SettingsRepositoryUnavailable:
        return _runtime_config_response(stored)
    _write_runtime_env_file(stored)
    return get_runtime_config()


def test_runtime_config(payload: RuntimeConfigTestRequest) -> RuntimeConfigTestResponse:
    key = payload.key.strip().upper()
    definition = RUNTIME_CONFIG_DEFINITIONS.get(key)
    checked_at = datetime.now(UTC)
    if not definition or not bool(definition.get("visible", True)):
        return RuntimeConfigTestResponse(
            key=key,
            ok=False,
            status="unsupported",
            detail="Dieser Wert ist kein prüfbarer Setup-Eintrag.",
            checked_at=checked_at,
        )

    value = str(payload.value or "").strip() or get_runtime_config_value(key)
    if key == "SEC_USER_AGENT":
        ok = bool(value and re.search(r"[^@\s]+@[^@\s]+\.[^@\s]+", value) and len(value.split()) >= 2)
        return RuntimeConfigTestResponse(
            key=key,
            ok=ok,
            status="ok" if ok else "invalid",
            detail="SEC User Agent sieht gültig aus." if ok else "Format erwartet: '<project> <contact-email>'.",
            checked_at=checked_at,
        )
    if key == "NEON_DATABASE_URL":
        return _test_database_url(key=key, value=value, checked_at=checked_at)
    if key == "FMP_API_KEY":
        return _test_fmp_api_key(key=key, value=value, checked_at=checked_at)
    if key in {"PUSHOVER_USER_KEY", "PUSHOVER_APP_TOKEN"}:
        return _test_pushover(key=key, candidate_key=payload.value, checked_at=checked_at)
    if key == "PUSHOVER_DRY_RUN":
        clean = value.lower()
        ok = clean in {"0", "1", "true", "false", "yes", "no", "on", "off"}
        return RuntimeConfigTestResponse(
            key=key,
            ok=ok,
            status="ok" if ok else "invalid",
            detail="Boolean-Wert ist gültig." if ok else "Erlaubt sind 0/1, true/false, yes/no oder on/off.",
            checked_at=checked_at,
        )
    if key == "APP_AUTH_ENABLED":
        clean = value.lower()
        ok = clean in {"0", "1", "true", "false", "yes", "no", "on", "off"}
        return RuntimeConfigTestResponse(
            key=key,
            ok=ok,
            status="ok" if ok else "invalid",
            detail="Boolean-Wert ist gültig." if ok else "Erlaubt sind 0/1, true/false, yes/no oder on/off.",
            checked_at=checked_at,
            restart_required=True,
        )
    if key == "APP_AUTH_USER":
        ok = bool(value)
        return RuntimeConfigTestResponse(
            key=key,
            ok=ok,
            status="ok" if ok else "missing",
            detail="Auth-Benutzername ist gesetzt." if ok else "Bitte einen Benutzername eintragen.",
            checked_at=checked_at,
            restart_required=True,
        )
    if key == "APP_AUTH_PASSWORD":
        if not value:
            return RuntimeConfigTestResponse(
                key=key,
                ok=False,
                status="missing",
                detail="Bitte ein Passwort eintragen.",
                checked_at=checked_at,
                restart_required=True,
            )
        strong_enough = len(value) >= 12
        return RuntimeConfigTestResponse(
            key=key,
            ok=strong_enough,
            status="ok" if strong_enough else "invalid",
            detail="Passwortlänge ist ausreichend." if strong_enough else "Nutze mindestens 12 Zeichen.",
            checked_at=checked_at,
            restart_required=True,
        )
    return RuntimeConfigTestResponse(
        key=key,
        ok=False,
        status="unsupported",
        detail="Für diesen Eintrag ist noch kein Verbindungstest hinterlegt.",
        checked_at=checked_at,
        restart_required=bool(definition.get("restart_required", False)),
    )


def get_database_target() -> DatabaseTargetResponse:
    stored = _read_runtime_config()
    return _database_target_response(stored)


def switch_database_target(payload: DatabaseTargetSwitchRequest) -> DatabaseTargetResponse:
    stored = _read_runtime_config()
    target = payload.target
    if target == "neon" and not _stored_neon_database_url(stored):
        raise ValueError("NEON_DATABASE_URL ist nicht gespeichert. Bitte zuerst Neon-Adresse eintragen und testen.")

    if target == "neon" and not str(stored.get("LOCAL_DATABASE_URL") or "").strip():
        current_url = get_settings().database_url
        if _database_target_for_url(current_url) == "local":
            stored["LOCAL_DATABASE_URL"] = current_url

    target_url = _database_url_for_target(target, stored)
    _migrate_database_target(target_url)
    stored["DATABASE_TARGET"] = target
    try:
        settings_repository.write_runtime_config(stored)
    except SettingsRepositoryUnavailable:
        pass
    _write_runtime_env_file(stored)
    return _database_target_response(stored)


def restart_runtime_services() -> RuntimeServicesRestartResponse:
    started_at = datetime.now(UTC)
    services = _runtime_restart_services()
    if not get_runtime_config_bool("NAS_CONTROL_ENABLED", fallback=_env_bool("NAS_CONTROL_ENABLED", False)):
        return RuntimeServicesRestartResponse(
            ok=False,
            status="disabled",
            detail="NAS-Control ist deaktiviert. Setze NAS_CONTROL_ENABLED=1, damit die App Docker-Dienste neu starten darf.",
            services=services,
            started_at=started_at,
        )
    try:
        _list_compose_containers(project=_nas_compose_project(), services=services)
    except Exception as exc:
        return RuntimeServicesRestartResponse(
            ok=False,
            status="failed",
            detail=f"Docker-Socket nicht erreichbar oder Compose-Container nicht gefunden: {type(exc).__name__}: {exc}",
            services=services,
            started_at=started_at,
        )

    thread = threading.Thread(
        target=_restart_runtime_services_background,
        kwargs={"project": _nas_compose_project(), "services": services},
        daemon=True,
    )
    thread.start()
    return RuntimeServicesRestartResponse(
        ok=True,
        status="scheduled",
        detail=(
            "Neustart wurde geplant. Worker und Scheduler werden zuerst neu gestartet, Backend zuletzt. "
            "Die Weboberfläche kann kurz nicht erreichbar sein."
        ),
        services=services,
        started_at=started_at,
    )


def get_runtime_config_value(key: str) -> str:
    definition = RUNTIME_CONFIG_DEFINITIONS.get(key)
    if not definition:
        return ""
    stored = _read_runtime_config()
    stored_value = _stored_runtime_value(key, stored)
    if stored_value:
        return stored_value
    return _environment_value(key, definition).strip()


def get_runtime_config_bool(key: str, fallback: bool = False) -> bool:
    value = get_runtime_config_value(key)
    if not value:
        return fallback
    return value.lower() in {"1", "true", "yes", "on"}


def _test_database_url(*, key: str, value: str, checked_at: datetime) -> RuntimeConfigTestResponse:
    if not value:
        return RuntimeConfigTestResponse(
            key=key,
            ok=False,
            status="missing",
            detail="Keine DATABASE_URL angegeben.",
            checked_at=checked_at,
            restart_required=True,
        )
    url = _normalize_database_url(value)
    try:
        engine = create_engine(url, pool_pre_ping=True, connect_args={"connect_timeout": 10})
        with engine.connect() as connection:
            connection.execute(text("select 1"))
        engine.dispose()
    except Exception as exc:
        return RuntimeConfigTestResponse(
            key=key,
            ok=False,
            status="failed",
            detail=f"Verbindung fehlgeschlagen: {type(exc).__name__}: {exc}",
            checked_at=checked_at,
            restart_required=True,
        )
    return RuntimeConfigTestResponse(
        key=key,
        ok=True,
        status="ok",
        detail="Datenbankverbindung erfolgreich. Speichern schreibt die Runtime-Konfiguration; danach Container neu starten.",
        checked_at=checked_at,
        restart_required=True,
    )


def _test_fmp_api_key(*, key: str, value: str, checked_at: datetime) -> RuntimeConfigTestResponse:
    if not value:
        return RuntimeConfigTestResponse(
            key=key,
            ok=False,
            status="missing",
            detail="Kein FMP API Key angegeben.",
            checked_at=checked_at,
        )
    try:
        response = requests.get(
            FMP_PROFILE_URL,
            params={"symbol": "AAPL", "apikey": value},
            timeout=12,
        )
        if response.status_code != 200:
            body = compact_fmp_response_body(response)
            detail = f"FMP antwortet mit HTTP {response.status_code}."
            if body:
                detail = f"{detail} Antwort: {body}"
            return RuntimeConfigTestResponse(
                key=key,
                ok=False,
                status="failed",
                detail=detail,
                checked_at=checked_at,
            )
        payload = response.json()
        ok = is_non_empty_fmp_payload(payload)
        return RuntimeConfigTestResponse(
            key=key,
            ok=ok,
            status="ok" if ok else "invalid",
            detail="FMP API Key funktioniert." if ok else "FMP-Antwort war leer oder enthielt eine Fehlermeldung.",
            checked_at=checked_at,
        )
    except Exception as exc:
        return RuntimeConfigTestResponse(
            key=key,
            ok=False,
            status="failed",
            detail=f"FMP-Test fehlgeschlagen: {type(exc).__name__}: {exc}",
            checked_at=checked_at,
        )


def _test_pushover(*, key: str, candidate_key: str | None, checked_at: datetime) -> RuntimeConfigTestResponse:
    stored = _read_runtime_config()
    user_key = str(stored.get("PUSHOVER_USER_KEY") or _environment_value("PUSHOVER_USER_KEY", RUNTIME_CONFIG_DEFINITIONS["PUSHOVER_USER_KEY"]) or "").strip()
    app_token = str(stored.get("PUSHOVER_APP_TOKEN") or _environment_value("PUSHOVER_APP_TOKEN", RUNTIME_CONFIG_DEFINITIONS["PUSHOVER_APP_TOKEN"]) or "").strip()
    if key == "PUSHOVER_USER_KEY" and candidate_key:
        user_key = candidate_key.strip()
    if key == "PUSHOVER_APP_TOKEN" and candidate_key:
        app_token = candidate_key.strip()
    if not user_key or not app_token:
        return RuntimeConfigTestResponse(
            key=key,
            ok=False,
            status="missing",
            detail="Pushover-Test benötigt User Key und App Token.",
            checked_at=checked_at,
        )
    try:
        response = requests.post(
            "https://api.pushover.net/1/users/validate.json",
            data={"token": app_token, "user": user_key},
            timeout=12,
        )
        ok = response.status_code == 200 and bool(response.json().get("status") == 1)
        return RuntimeConfigTestResponse(
            key=key,
            ok=ok,
            status="ok" if ok else "failed",
            detail="Pushover-Zugang ist gültig." if ok else f"Pushover validiert die Daten nicht (HTTP {response.status_code}).",
            checked_at=checked_at,
        )
    except Exception as exc:
        return RuntimeConfigTestResponse(
            key=key,
            ok=False,
            status="failed",
            detail=f"Pushover-Test fehlgeschlagen: {type(exc).__name__}: {exc}",
            checked_at=checked_at,
        )


def _write_runtime_env_file(stored: dict) -> None:
    path = os.environ.get("APP_RUNTIME_ENV_FILE", "/app/runtime/runtime.env")
    runtime_values = {
        key: str(stored.get(key) or "").strip()
        for key in (
            "SEC_USER_AGENT",
            "FMP_API_KEY",
            "PUSHOVER_USER_KEY",
            "PUSHOVER_APP_TOKEN",
            "PUSHOVER_DRY_RUN",
            "APP_AUTH_ENABLED",
            "APP_AUTH_USER",
            "APP_AUTH_PASSWORD",
        )
        if str(stored.get(key) or "").strip()
    }
    target = _stored_database_target(stored)
    runtime_values["DATABASE_TARGET"] = target
    if target == "neon":
        runtime_values["DATABASE_URL"] = _normalize_database_url(_stored_neon_database_url(stored))
    elif str(stored.get("LOCAL_DATABASE_URL") or "").strip():
        runtime_values["DATABASE_URL"] = _normalize_database_url(str(stored.get("LOCAL_DATABASE_URL") or ""))
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if not runtime_values:
            if os.path.exists(path):
                os.remove(path)
            return
        tmp_path = f"{path}.tmp"
        with open(tmp_path, "w", encoding="utf-8") as handle:
            handle.write("# Generated by boerse-dashboard-web setup. Do not commit.\n")
            for key, value in runtime_values.items():
                handle.write(f"{key}={_shell_quote(value)}\n")
        os.replace(tmp_path, path)
    except OSError:
        return


def _database_target_response(stored: dict) -> DatabaseTargetResponse:
    target = _stored_database_target(stored)
    running_url = get_settings().database_url
    running_target = _database_target_for_url(running_url)
    neon_url = _stored_neon_database_url(stored)
    local_url = str(stored.get("LOCAL_DATABASE_URL") or os.environ.get("LOCAL_DATABASE_URL") or "").strip()
    if not local_url and running_target == "local":
        local_url = running_url
    restart_required = target != running_target
    if target == "neon" and neon_url and _preview_value(running_url, secret=True) != _preview_value(neon_url, secret=True):
        restart_required = True
    message = (
        "Neon ist vorbereitet; Backend, Worker und Scheduler neu starten, damit es aktiv wird."
        if restart_required and target == "neon"
        else "Lokale Postgres ist vorbereitet; Dienste neu starten, damit sie wieder lokal laufen."
        if restart_required
        else "Die laufenden Dienste verwenden bereits das ausgewählte Datenbankziel."
    )
    return DatabaseTargetResponse(
        target=target,
        running_target=running_target,
        restart_required=restart_required,
        neon_configured=bool(neon_url),
        neon_value_preview=_preview_value(neon_url, secret=True),
        local_value_preview=_preview_value(local_url, secret=True),
        active_value_preview=_preview_value(running_url, secret=True),
        message=message,
    )


def _stored_database_target(stored: dict) -> str:
    target = str(stored.get("DATABASE_TARGET") or "").strip().lower()
    return "neon" if target == "neon" else "local"


def _stored_neon_database_url(stored: dict) -> str:
    return str(stored.get("NEON_DATABASE_URL") or stored.get("DATABASE_URL") or "").strip()


def _database_url_for_target(target: str, stored: dict) -> str:
    if target == "neon":
        value = _stored_neon_database_url(stored)
    else:
        value = str(stored.get("LOCAL_DATABASE_URL") or os.environ.get("LOCAL_DATABASE_URL") or "").strip()
        if not value and _database_target_for_url(get_settings().database_url) == "local":
            value = get_settings().database_url
    if not value:
        raise ValueError(f"Für das Datenbankziel {target} ist keine Verbindungsadresse gespeichert.")
    return _normalize_database_url(value)


def _migrate_database_target(database_url: str) -> None:
    backend_root = Path(__file__).resolve().parents[2]
    env = os.environ.copy()
    env["DATABASE_URL"] = database_url
    try:
        completed = subprocess.run(
            ["alembic", "upgrade", "head"],
            cwd=backend_root,
            env=env,
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ValueError(f"Datenbankmigration konnte nicht gestartet werden: {type(exc).__name__}.") from exc
    if completed.returncode == 0:
        return
    detail = (completed.stderr or completed.stdout or "").strip().splitlines()
    last_line = detail[-1] if detail else "unbekannter Alembic-Fehler"
    safe_detail = last_line.replace(database_url, "<database-url>")
    raise ValueError(f"Datenbankziel wurde nicht umgeschaltet: Alembic-Migration fehlgeschlagen ({safe_detail}).")


def _database_target_for_url(value: str) -> str:
    clean = value.lower()
    return "neon" if "neon.tech" in clean or "pooler" in clean and "neon" in clean else "local"


def _env_bool(key: str, fallback: bool = False) -> bool:
    raw = str(os.environ.get(key) or "").strip().lower()
    if not raw:
        return fallback
    return raw in {"1", "true", "yes", "on"}


def _runtime_restart_services() -> list[str]:
    raw = str(os.environ.get("NAS_RESTART_SERVICES") or "worker,monitor,scheduler,frontend,backend")
    services = [item.strip() for item in raw.split(",") if item.strip()]
    ordered = [service for service in services if service != "backend"]
    if "backend" in services:
        ordered.append("backend")
    return ordered or ["worker", "monitor", "scheduler", "frontend", "backend"]


def _nas_compose_project() -> str:
    return str(os.environ.get("NAS_COMPOSE_PROJECT") or "infra").strip() or "infra"


def _docker_socket_path() -> str:
    return str(os.environ.get("NAS_DOCKER_SOCKET") or "/var/run/docker.sock")


def _restart_runtime_services_background(*, project: str, services: list[str]) -> None:
    time.sleep(1.5)
    containers = _list_compose_containers(project=project, services=services)
    by_service = {container["service"]: container["id"] for container in containers}
    for service in services:
        container_id = by_service.get(service)
        if not container_id:
            continue
        _docker_request("POST", f"/containers/{container_id}/restart?t=10")


def _list_compose_containers(*, project: str, services: list[str]) -> list[dict[str, str]]:
    response = _docker_request("GET", "/containers/json?all=1")
    containers: list[dict[str, str]] = []
    for item in loads(response or "[]"):
        labels = item.get("Labels") or {}
        if labels.get("com.docker.compose.project") != project:
            continue
        service = labels.get("com.docker.compose.service")
        if service not in services:
            continue
        containers.append({"id": str(item.get("Id")), "service": str(service)})
    missing = [service for service in services if service not in {item["service"] for item in containers}]
    if missing:
        raise RuntimeError(f"Compose-Services nicht gefunden: {', '.join(missing)}")
    return containers


def _docker_request(method: str, path: str, body: dict | None = None) -> str:
    payload = dumps(body).encode("utf-8") if body is not None else b""
    headers = [
        f"{method} {path} HTTP/1.1",
        "Host: docker",
        "Connection: close",
    ]
    if body is not None:
        headers.extend(["Content-Type: application/json", f"Content-Length: {len(payload)}"])
    request = ("\r\n".join(headers) + "\r\n\r\n").encode("utf-8") + payload
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(15)
        client.connect(_docker_socket_path())
        client.sendall(request)
        chunks: list[bytes] = []
        while True:
            chunk = client.recv(65536)
            if not chunk:
                break
            chunks.append(chunk)
    raw = b"".join(chunks)
    header_bytes, _, body_bytes = raw.partition(b"\r\n\r\n")
    header_text = header_bytes.decode("iso-8859-1", errors="replace")
    status_line = header_text.splitlines()[0]
    status_code = int(status_line.split()[1])
    if "transfer-encoding: chunked" in header_text.lower():
        body_bytes = _decode_http_chunked_body(body_bytes)
    if status_code >= 400:
        raise RuntimeError(f"Docker API HTTP {status_code}: {body_bytes.decode('utf-8', errors='replace')}")
    return body_bytes.decode("utf-8", errors="replace")


def _decode_http_chunked_body(body: bytes) -> bytes:
    output = bytearray()
    rest = body
    while rest:
        line, separator, remainder = rest.partition(b"\r\n")
        if not separator:
            break
        try:
            size = int(line.split(b";", 1)[0], 16)
        except ValueError:
            return body
        if size == 0:
            break
        output.extend(remainder[:size])
        rest = remainder[size + 2 :]
    return bytes(output)


def _normalize_database_url(value: str) -> str:
    clean = value.strip()
    if clean.startswith("postgres://"):
        return "postgresql+psycopg://" + clean.removeprefix("postgres://")
    if clean.startswith("postgresql://"):
        return "postgresql+psycopg://" + clean.removeprefix("postgresql://")
    return clean


def _shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def get_data_diagnostics() -> DataDiagnosticsResponse:
    from app.services.data_quality import build_data_diagnostics

    return build_data_diagnostics()


def _settings_from_values(values: dict) -> AppSettings:
    merged = DEFAULT_SETTINGS.model_dump()
    merged.update({key: value for key, value in values.items() if key in merged})
    # The dedicated monitor queue has a fixed one-minute cadence. Keep the
    # compatibility field truthful even for databases that still store ``5``.
    merged["position_monitor_interval_minutes"] = 1
    runtime = get_settings()
    merged["pushover_configured"] = bool(
        (get_runtime_config_value("PUSHOVER_USER_KEY") or runtime.pushover_user_key)
        and (get_runtime_config_value("PUSHOVER_APP_TOKEN") or runtime.pushover_app_token)
    )
    return AppSettings(**merged)


def _read_runtime_config() -> dict:
    try:
        return settings_repository.read_runtime_config()
    except SettingsRepositoryUnavailable:
        return {}


def _runtime_config_item(key: str, definition: dict[str, Any], stored: dict) -> RuntimeConfigItem:
    stored_value = _stored_runtime_value(key, stored)
    env_value = _environment_value(key, definition).strip()
    effective = stored_value or env_value
    if stored_value:
        source = "database"
    elif env_value:
        source = "environment"
    elif definition.get("editable"):
        source = "missing"
    else:
        source = "bootstrap_only"
    return RuntimeConfigItem(
        key=key,
        label=str(definition["label"]),
        category=definition["category"],
        description=str(definition["description"]),
        configured=bool(effective),
        source=source,
        secret=bool(definition.get("secret", True)),
        editable=bool(definition.get("editable", False)),
        restart_required=bool(definition.get("restart_required", False)),
        runtime_applied=bool(definition.get("runtime_applied", False)),
        placeholder=str(definition.get("placeholder") or ""),
        value_preview=_preview_value(effective, secret=bool(definition.get("secret", True))),
    )


def _stored_runtime_value(key: str, stored: dict) -> str:
    if key == "NEON_DATABASE_URL":
        return str(stored.get("NEON_DATABASE_URL") or stored.get("DATABASE_URL") or "").strip()
    return str(stored.get(key) or "").strip()


def _environment_value(key: str, definition: dict[str, Any]) -> str:
    if key in os.environ:
        return str(os.environ.get(key) or "")
    attr = definition.get("attr")
    if attr:
        value = getattr(get_settings(), str(attr), "")
        if isinstance(value, bool):
            return "1" if value else "0"
        return str(value or "")
    return ""


def _preview_value(value: str, *, secret: bool) -> str:
    if not value:
        return ""
    if not secret:
        return value if len(value) <= 80 else f"{value[:32]}...{value[-12:]}"
    if len(value) <= 6:
        return "***"
    return f"{value[:2]}***{value[-4:]}"
