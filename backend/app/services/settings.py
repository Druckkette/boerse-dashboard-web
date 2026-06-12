from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from app.core_config import get_settings
from app.db.models import Instrument, IsinMapping, Position, PriceBar
from app.db.session import SessionLocal
from app.repositories import settings as settings_repository
from app.repositories.settings import SettingsRepositoryUnavailable
from app.schemas import AppSettings, DataDiagnosticIssue, DataDiagnosticsResponse, SettingsPatch


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
    merged["pushover_configured"] = bool(runtime.pushover_user_key and runtime.pushover_app_token)
    return AppSettings(**merged)


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
