from __future__ import annotations

import os
import re
from datetime import UTC, date, datetime, timedelta
from typing import Any

import requests
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.exc import SQLAlchemyError

from app.core_config import get_settings
from app.db.models import Instrument, IsinMapping, Position, PriceBar
from app.db.session import SessionLocal
from app.repositories import settings as settings_repository
from app.repositories.settings import SettingsRepositoryUnavailable
from app.schemas import (
    AppSettings,
    DataDiagnosticIssue,
    DataDiagnosticsResponse,
    RuntimeConfigItem,
    RuntimeConfigPatch,
    RuntimeConfigResponse,
    RuntimeConfigTestRequest,
    RuntimeConfigTestResponse,
    SettingsPatch,
)


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
    "DATABASE_URL": {
        "label": "Neon / externe Postgres DATABASE_URL",
        "category": "database",
        "description": "Optionale Neon- oder externe Postgres-Verbindung. Vor dem Speichern testen; nach dem Speichern Container neu starten.",
        "secret": True,
        "editable": True,
        "restart_required": True,
        "runtime_applied": False,
        "placeholder": "postgresql+psycopg://...",
        "attr": "database_url",
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
        "description": "Frontend-Bootstrap-Wert; Next.js liest ihn beim Containerstart.",
        "secret": False,
        "editable": False,
        "restart_required": True,
        "runtime_applied": False,
        "placeholder": "1",
    },
    "APP_AUTH_USER": {
        "label": "Frontend Auth User",
        "category": "security",
        "description": "Frontend-Bootstrap-Wert; gehört weiter in die Container-Umgebung.",
        "secret": True,
        "editable": False,
        "restart_required": True,
        "runtime_applied": False,
        "placeholder": "boerse",
    },
    "APP_AUTH_PASSWORD": {
        "label": "Frontend Auth Passwort",
        "category": "security",
        "description": "Frontend-Bootstrap-Wert; gehört weiter in die Container-Umgebung.",
        "secret": True,
        "editable": False,
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
            "Neon/DATABASE_URL wird nach Container-Neustart von Backend, Worker und Scheduler gelesen."
        ),
    )


def update_runtime_config(payload: RuntimeConfigPatch) -> RuntimeConfigResponse:
    stored = _read_runtime_config()
    editable = {key for key, definition in RUNTIME_CONFIG_DEFINITIONS.items() if bool(definition.get("editable"))}
    for key in payload.clear_keys:
        if key in editable:
            stored.pop(key, None)
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
    if key == "DATABASE_URL":
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
    return RuntimeConfigTestResponse(
        key=key,
        ok=False,
        status="unsupported",
        detail="Für diesen Eintrag ist noch kein Verbindungstest hinterlegt.",
        checked_at=checked_at,
        restart_required=bool(definition.get("restart_required", False)),
    )


def get_runtime_config_value(key: str) -> str:
    definition = RUNTIME_CONFIG_DEFINITIONS.get(key)
    if not definition:
        return ""
    stored = _read_runtime_config()
    stored_value = str(stored.get(key) or "").strip()
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
            "https://financialmodelingprep.com/api/v3/profile/AAPL",
            params={"apikey": value},
            timeout=12,
        )
        if response.status_code != 200:
            return RuntimeConfigTestResponse(
                key=key,
                ok=False,
                status="failed",
                detail=f"FMP antwortet mit HTTP {response.status_code}.",
                checked_at=checked_at,
            )
        payload = response.json()
        ok = isinstance(payload, list) and bool(payload) and "symbol" in payload[0]
        return RuntimeConfigTestResponse(
            key=key,
            ok=ok,
            status="ok" if ok else "invalid",
            detail="FMP API Key funktioniert." if ok else "FMP-Antwort hatte nicht das erwartete Profilformat.",
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
            "DATABASE_URL",
            "SEC_USER_AGENT",
            "FMP_API_KEY",
            "PUSHOVER_USER_KEY",
            "PUSHOVER_APP_TOKEN",
            "PUSHOVER_DRY_RUN",
        )
        if str(stored.get(key) or "").strip()
    }
    if runtime_values.get("DATABASE_URL"):
        runtime_values["DATABASE_URL"] = _normalize_database_url(runtime_values["DATABASE_URL"])
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
    today = date.today()
    stale_before = today - timedelta(days=7)
    try:
        with SessionLocal() as db:
            positions = db.execute(
                select(Position.ticker, Position.instrument_id)
                .where(Position.is_open.is_(True))
                .order_by(Position.ticker.asc())
            ).all()
            latest_price_rows = db.execute(
                select(Instrument.ticker, func.max(PriceBar.date))
                .join(PriceBar, PriceBar.instrument_id == Instrument.id)
                .where(PriceBar.close.is_not(None))
                .group_by(Instrument.ticker)
            ).all()
            latest_by_ticker = {str(ticker).upper(): price_date for ticker, price_date in latest_price_rows}
            open_tickers = sorted({str(ticker).upper() for ticker, _ in positions if ticker})
            missing_price_tickers = [ticker for ticker in open_tickers if ticker not in latest_by_ticker]
            stale_price_tickers = [
                ticker
                for ticker in open_tickers
                if ticker in latest_by_ticker and latest_by_ticker[ticker] and latest_by_ticker[ticker] < stale_before
            ]
            missing_yahoo_tickers = _missing_yahoo_symbols(db, open_tickers)
            isin_mappings_count = int(db.scalar(select(func.count()).select_from(IsinMapping)) or 0)
    except SQLAlchemyError as exc:
        return DataDiagnosticsResponse(
            as_of=today.isoformat(),
            health_tone="bad",
            summary="Datenbank-Diagnose nicht verfügbar.",
            issues=[
                DataDiagnosticIssue(
                    key="database_unavailable",
                    label="Datenbank nicht erreichbar",
                    severity="critical",
                    detail=f"{type(exc).__name__}: {exc}",
                )
            ],
        )

    issues: list[DataDiagnosticIssue] = []
    if not open_tickers:
        issues.append(
            DataDiagnosticIssue(
                key="no_open_positions",
                label="Kein Depot importiert",
                severity="info",
                detail="Es sind keine offenen Positionen gespeichert. Importiere dein Depot über Portfolio > Imports.",
            )
        )
    if missing_price_tickers:
        issues.append(
            DataDiagnosticIssue(
                key="missing_price_cache",
                label="Kursdaten fehlen",
                severity="critical",
                detail=f"{len(missing_price_tickers)} offene Positionen haben noch keinen Price-Cache.",
                tickers=missing_price_tickers,
                action_label="Fehlende Kurse laden",
                job_type="refresh_prices",
                job_payload={"mode": "manual", "range": "1y", "tickers": missing_price_tickers},
            )
        )
    if stale_price_tickers:
        issues.append(
            DataDiagnosticIssue(
                key="stale_price_cache",
                label="Kursdaten veraltet",
                severity="warning",
                detail=f"{len(stale_price_tickers)} offene Positionen sind älter als 7 Tage.",
                tickers=stale_price_tickers,
                action_label="Veraltete Kurse aktualisieren",
                job_type="refresh_prices",
                job_payload={"mode": "manual", "range": "6m", "tickers": stale_price_tickers},
            )
        )
    if missing_yahoo_tickers:
        issues.append(
            DataDiagnosticIssue(
                key="missing_yahoo_symbol",
                label="Yahoo-Symbol fehlt",
                severity="warning",
                detail="Für diese Instrumente ist kein Yahoo-Symbol gepflegt. Prüfe Ticker-/ISIN-Mapping im Importbereich.",
                tickers=missing_yahoo_tickers,
            )
        )
    if isin_mappings_count == 0 and open_tickers:
        issues.append(
            DataDiagnosticIssue(
                key="no_isin_mappings",
                label="Keine ISIN-Mappings gespeichert",
                severity="info",
                detail="Trade-Republic-Imports funktionieren robuster, wenn ISIN-zu-Yahoo-Mappings gespeichert sind.",
            )
        )
    if not issues:
        issues.append(
            DataDiagnosticIssue(
                key="data_ready",
                label="Datenbasis bereit",
                severity="info",
                detail="Offene Positionen, Price Cache und gespeicherte Mappings sehen konsistent aus.",
            )
        )

    critical_count = sum(issue.severity == "critical" for issue in issues)
    warning_count = sum(issue.severity == "warning" for issue in issues)
    tone = "bad" if critical_count else "warning" if warning_count else "good"
    summary = _data_diagnostics_summary(critical_count, warning_count, len(open_tickers))
    return DataDiagnosticsResponse(
        as_of=today.isoformat(),
        health_tone=tone,
        summary=summary,
        open_positions_count=len(open_tickers),
        price_cache_tickers_count=len(latest_by_ticker),
        missing_price_count=len(missing_price_tickers),
        stale_price_count=len(stale_price_tickers),
        missing_yahoo_symbol_count=len(missing_yahoo_tickers),
        isin_mappings_count=isin_mappings_count,
        issues=issues,
    )


def _settings_from_values(values: dict) -> AppSettings:
    merged = DEFAULT_SETTINGS.model_dump()
    merged.update({key: value for key, value in values.items() if key in merged})
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
    stored_value = str(stored.get(key) or "").strip()
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


def _missing_yahoo_symbols(db, tickers: list[str]) -> list[str]:
    if not tickers:
        return []
    instruments = db.scalars(select(Instrument).where(Instrument.ticker.in_(tickers))).all()
    return sorted(
        {
            str(instrument.ticker).upper()
            for instrument in instruments
            if instrument.ticker and not str(instrument.yahoo_symbol or "").strip()
        }
    )


def _data_diagnostics_summary(critical_count: int, warning_count: int, open_positions_count: int) -> str:
    if open_positions_count == 0:
        return "Noch kein Depot importiert; Datenjobs können erst danach gezielt prüfen."
    if critical_count:
        return f"{critical_count} kritische Datenlücken. Starte die vorgeschlagenen Refresh-Jobs."
    if warning_count:
        return f"{warning_count} Warnungen. Die App läuft, aber einzelne Daten sollten aktualisiert werden."
    return "Datenbasis konsistent. Keine akuten Price-Cache- oder Mapping-Lücken erkannt."
