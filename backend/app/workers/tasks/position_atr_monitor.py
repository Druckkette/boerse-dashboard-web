from __future__ import annotations

import math
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from app.core_config import get_settings as get_runtime_settings
from app.domain.sell.service import monitor_open_position_atr
from app.repositories import jobs as job_repository
from app.repositories import settings as settings_repository
from app.repositories.settings import SettingsRepositoryUnavailable
from app.schemas import AppSettings
from app.services.settings import get_app_settings, get_runtime_config_bool, get_runtime_config_value
from app.workers.celery_app import celery_app
from app.workers.tasks.common import JobCancelled, raise_if_cancelled
from app.workers.tasks.pushover_test import _send_pushover_message


BERLIN_TZ = ZoneInfo("Europe/Berlin")
MONITOR_RESET_TIME = time(7, 30)


@celery_app.task(bind=True, name="position_atr_monitor", soft_time_limit=50, time_limit=55)
def position_atr_monitor(self, job_id: str | None = None, payload: dict | None = None) -> dict:
    payload = payload or {}
    job = job_repository.get_job(job_id) if job_id else None
    if job is None:
        job = job_repository.create_job(
            "position_atr_monitor",
            payload,
            requested_by=str(payload.get("source") or "scheduler"),
        )

    tickers = _normalize_tickers(payload.get("tickers"))
    job_repository.mark_running(job.job_id, step="Positionsmonitor startet")
    try:
        settings = get_app_settings()
        monitor_settings = settings.model_dump()
        monitor_settings["source_job_id"] = job.job_id
        payload_settings = payload.get("monitor_settings")
        if isinstance(payload_settings, dict):
            monitor_settings.update(payload_settings)
        monitor_settings["source_job_id"] = job.job_id

        requested_by = str(payload.get("source") or job.requested_by or "").lower()
        is_scheduler_run = requested_by == "scheduler"
        if is_scheduler_run and not settings.position_monitor_enabled and not payload.get("force"):
            result = {
                "ok": False,
                "skipped": True,
                "reason": "Positionsmonitor ist in den Settings deaktiviert.",
                "job_type": "position_atr_monitor",
                "records_seen": 0,
                "records_written": 0,
            }
            job_repository.mark_skipped(job.job_id, message=result["reason"], result=result)
            return result

        raise_if_cancelled(job.job_id)
        job_repository.update_progress(
            job.job_id,
            progress=20,
            step="Offene Positionen laden",
            message="Importierte offene Positionen werden aus Postgres gelesen.",
            result={"job_type": "position_atr_monitor", "tickers": tickers},
        )
        raise_if_cancelled(job.job_id)
        job_repository.update_progress(
            job.job_id,
            progress=55,
            step="Live-ATR prüfen",
            message="Yahoo-Live-Kurse werden gesammelt geladen und gegen den Cache-ATR geprüft.",
        )
        result = monitor_open_position_atr(tickers=tickers or None, monitor_settings=monitor_settings)
        if result.get("skipped"):
            job_repository.mark_skipped(job.job_id, message=str(result.get("reason") or "Keine Positionen."), result=result)
            return result
        result = _apply_cooldown_state(result, monitor_settings=monitor_settings, persist_state=False)
        alert_delivery = _deliver_monitor_alerts(result.get("alerts", []), app_settings=settings)
        _finalize_monitor_state(result, alert_delivery=alert_delivery)
        result["alert_delivery"] = alert_delivery
        if isinstance(result.get("last_summary"), dict):
            result["last_summary"]["sent"] = alert_delivery.get("sent", 0)

        raise_if_cancelled(job.job_id)
        job_repository.update_progress(
            job.job_id,
            progress=90,
            step="Monitor-State schreiben",
            message=f"{result.get('records_written', 0)} Positionen live geprüft.",
            result=result,
        )
        job_repository.mark_done(job.job_id, result=result, message="Positionsmonitor aktualisiert.")
        return result
    except JobCancelled:
        job_repository.mark_cancelled(job.job_id)
        return {"ok": False, "cancelled": True, "job_type": "position_atr_monitor"}
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        job_repository.mark_failed(job.job_id, error_message=error, result={"ok": False, "job_type": "position_atr_monitor"})
        raise


def _normalize_tickers(value: object) -> list[str]:
    if isinstance(value, str):
        raw = value.replace(";", ",").split(",")
    elif isinstance(value, list):
        raw = [str(item) for item in value]
    else:
        raw = []
    return list(dict.fromkeys(item.strip().upper() for item in raw if item and item.strip()))[:80]


def _apply_cooldown_state(
    result: dict[str, Any],
    *,
    monitor_settings: dict[str, Any],
    now: datetime | None = None,
    persist_state: bool = True,
) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    trade_day = _monitor_trade_day(now)
    reset_at = _next_monitor_reset(now)
    state = _read_monitor_state()
    ticker_state = state.get("tickers") if isinstance(state.get("tickers"), dict) else {}
    alerts: list[dict[str, Any]] = []
    suppressed: list[dict[str, Any]] = []

    for item in result.get("items", []):
        if not isinstance(item, dict):
            continue
        ticker = str(item.get("ticker") or "").strip().upper()
        monitor = item.get("monitor")
        if not ticker or not isinstance(monitor, dict):
            continue
        decision = _cooldown_decision(
            ticker=ticker,
            monitor=monitor,
            ticker_state=ticker_state,
            trade_day=trade_day,
            now=now,
            reset_at=reset_at,
            monitor_settings=monitor_settings,
        )
        monitor.update(decision["monitor_update"])
        if decision["allowed"]:
            ticker_state[ticker] = decision["state_update"]
            alerts.append(decision["alert"])
        elif decision["suppression"] is not None:
            if decision["state_update"] is not None:
                ticker_state[ticker] = decision["state_update"]
            suppressed.append(decision["suppression"])

    summary = {
        "checked": int(result.get("records_seen") or 0),
        "alerts": len(alerts),
        "suppressed": len(suppressed),
        "trade_day": trade_day,
        "reset_at": reset_at.isoformat(),
    }
    state.update(
        {
            "version": 1,
            "tickers": ticker_state,
            "last_finished_at": now.isoformat(),
            "last_summary": summary,
        }
    )
    if persist_state:
        _write_monitor_state(result, state)
    else:
        result["_pending_monitor_state"] = state

    result["alerts"] = alerts
    result["alerts_suppressed"] = suppressed
    result["monitor_trade_day"] = trade_day
    result["monitor_cooldown_reset_at"] = reset_at.isoformat()
    result["last_summary"] = summary
    return result


def _finalize_monitor_state(result: dict[str, Any], *, alert_delivery: dict[str, Any]) -> None:
    state = result.pop("_pending_monitor_state", None)
    if not isinstance(state, dict):
        return

    sent_tickers = {
        str(ticker).strip().upper()
        for ticker in alert_delivery.get("sent_tickers", [])
        if str(ticker).strip()
    }
    ticker_state = state.get("tickers") if isinstance(state.get("tickers"), dict) else {}
    for alert in result.get("alerts", []):
        ticker = str(alert.get("ticker") or "").strip().upper() if isinstance(alert, dict) else ""
        if ticker and ticker not in sent_tickers:
            ticker_state.pop(ticker, None)
    state["tickers"] = ticker_state

    summary = state.get("last_summary") if isinstance(state.get("last_summary"), dict) else {}
    summary.update(
        {
            "sent": int(alert_delivery.get("sent") or 0),
            "delivery_failed": int(alert_delivery.get("failed") or 0),
            "delivery_skipped": int(alert_delivery.get("skipped") or 0),
        }
    )
    state["last_summary"] = summary
    _write_monitor_state(result, state)


def _write_monitor_state(result: dict[str, Any], state: dict[str, Any]) -> None:
    try:
        settings_repository.write_position_monitor_state(state)
    except SettingsRepositoryUnavailable as exc:
        result.setdefault("warnings", []).append(f"Positionsmonitor-State konnte nicht gespeichert werden: {exc}")


def _deliver_monitor_alerts(alerts: list[dict[str, Any]], *, app_settings: AppSettings) -> dict[str, Any]:
    result: dict[str, Any] = {
        "ok": True,
        "enabled": bool(getattr(app_settings, "pushover_enabled", False)),
        "configured": False,
        "dry_run": False,
        "sent": 0,
        "failed": 0,
        "skipped": 0,
        "sent_tickers": [],
        "errors": [],
    }
    if not alerts:
        result["reason"] = "Keine neuen ATR-Signale."
        return result
    if not app_settings.pushover_enabled:
        result.update(skipped=len(alerts), reason="Pushover ist in den Settings deaktiviert.")
        return result

    runtime = get_runtime_settings()
    user_key = get_runtime_config_value("PUSHOVER_USER_KEY") or runtime.pushover_user_key
    app_token = get_runtime_config_value("PUSHOVER_APP_TOKEN") or runtime.pushover_app_token
    dry_run = get_runtime_config_bool("PUSHOVER_DRY_RUN", runtime.pushover_dry_run)
    result.update(configured=bool(user_key and app_token), dry_run=dry_run)
    if not user_key or not app_token:
        result.update(skipped=len(alerts), reason="PUSHOVER_USER_KEY oder PUSHOVER_APP_TOKEN fehlt.")
        return result
    if dry_run:
        result.update(skipped=len(alerts), reason="PUSHOVER_DRY_RUN ist aktiv.")
        return result

    for alert in alerts:
        try:
            response = _send_pushover_message(
                user_key=user_key,
                app_token=app_token,
                message=_format_monitor_alert_message(alert),
                title=f"ATR-Alarm {alert.get('ticker', 'Position')}",
                priority=1,
            )
            if int(response.get("status") or 0) != 1:
                raise RuntimeError(f"Pushover hat den Alarm nicht bestätigt: {response}")
            result["sent"] += 1
            result["sent_tickers"].append(str(alert.get("ticker") or "").strip().upper())
        except Exception as exc:  # noqa: BLE001 - alert delivery must not crash the monitor job
            result["failed"] += 1
            result["errors"].append(f"{alert.get('ticker', 'UNKNOWN')}: {type(exc).__name__}: {exc}")
    result["ok"] = result["failed"] == 0
    return result


def _format_monitor_alert_message(alert: dict[str, Any]) -> str:
    ticker = str(alert.get("ticker") or "UNKNOWN")
    distance = _float_or_none(alert.get("distance_atr")) or 0.0
    threshold = _float_or_none(alert.get("threshold_atr")) or 0.0
    reference = str(alert.get("reference_label") or alert.get("reference") or "Referenz")
    current_price = alert.get("current_price")
    reference_price = alert.get("reference_price")
    reason = str(alert.get("reason") or "")
    reason_text = "2x ATR Eskalation" if reason == "2x_atr_escalation" else "ATR-Schwelle neu überschritten"
    return (
        f"{ticker}: ATR-Abstand {distance:.2f} >= {threshold:.2f}\n"
        f"Referenz: {reference}\n"
        f"Aktueller Kurs: {current_price}; Referenzkurs: {reference_price}\n"
        f"Auslöser: {reason_text}"
    )


def _cooldown_decision(
    *,
    ticker: str,
    monitor: dict[str, Any],
    ticker_state: dict[str, Any],
    trade_day: str,
    now: datetime,
    reset_at: datetime,
    monitor_settings: dict[str, Any],
) -> dict[str, Any]:
    distance_atr = _float_or_none(monitor.get("distance_atr"))
    threshold_atr = _float_or_none(monitor.get("threshold_atr")) or _float_or_none(
        monitor_settings.get("position_monitor_threshold_atr")
    ) or 1.5
    crossed = bool(monitor.get("threshold_crossed")) and distance_atr is not None
    monitor_update: dict[str, Any] = {
        "cooldown_trade_day": trade_day,
        "cooldown_reset_at": reset_at.isoformat(),
        "alert_allowed": False,
        "alert_reason": "threshold_not_crossed",
    }
    if not crossed:
        return {
            "allowed": False,
            "monitor_update": monitor_update,
            "state_update": None,
            "alert": None,
            "suppression": None,
        }

    previous = ticker_state.get(ticker) if isinstance(ticker_state.get(ticker), dict) else {}
    previous_trade_day = str(previous.get("trade_day") or "")
    previous_distance = _float_or_none(previous.get("last_distance_atr"))
    previous_reference_price = _float_or_none(previous.get("reference_price"))
    current_reference_price = _float_or_none(monitor.get("reference_price"))
    two_x_threshold = threshold_atr * 2
    is_two_x = distance_atr >= two_x_threshold
    previous_two_x = bool(previous.get("escalated_2x"))
    is_new_trade_day = previous_trade_day != trade_day
    reference_changed = (
        previous_reference_price is not None
        and current_reference_price is not None
        and abs(previous_reference_price - current_reference_price)
        > max(0.01, abs(previous_reference_price) * 0.0001)
    )
    distance_deeper = previous_distance is None or distance_atr > previous_distance + 0.25
    fresh_new_trade_day = is_new_trade_day and (not previous_trade_day or reference_changed or distance_deeper)
    allowed = fresh_new_trade_day or (is_two_x and not previous_two_x)
    reason = (
        "new_trade_day"
        if fresh_new_trade_day
        else "2x_atr_escalation"
        if allowed
        else "new_trade_day_no_new_loss"
        if is_new_trade_day
        else "cooldown_same_trade_day"
    )

    state_update = {
        "trade_day": trade_day,
        "last_alert_at": now.isoformat() if allowed else str(previous.get("last_alert_at") or ""),
        "last_distance_atr": distance_atr,
        "threshold_atr": threshold_atr,
        "reference": str(monitor.get("reference") or ""),
        "reference_price": current_reference_price,
        "current_price": _float_or_none(monitor.get("current_price")),
        "escalated_2x": is_two_x or previous_two_x,
    }
    monitor_update.update(
        {
            "alert_allowed": allowed,
            "alert_reason": reason,
            "alert_escalation_2x": is_two_x,
            "last_alert_trade_day": previous_trade_day,
        }
    )
    alert_payload = {
        "ticker": ticker,
        "distance_atr": round(distance_atr, 4),
        "threshold_atr": round(threshold_atr, 4),
        "reference": str(monitor.get("reference") or ""),
        "reference_label": str(monitor.get("reference_label") or ""),
        "current_price": monitor.get("current_price"),
        "reference_price": monitor.get("reference_price"),
        "atr_value": monitor.get("atr_value"),
        "trade_day": trade_day,
        "reason": reason,
    }
    if allowed:
        return {
            "allowed": True,
            "monitor_update": monitor_update,
            "state_update": state_update,
            "alert": alert_payload,
            "suppression": None,
        }
    return {
        "allowed": False,
        "monitor_update": monitor_update,
        "state_update": state_update if is_new_trade_day else None,
        "alert": None,
        "suppression": {
            **alert_payload,
            "reason": reason,
            "next_reset_at": reset_at.isoformat(),
        },
    }


def _monitor_trade_day(now: datetime | None = None) -> str:
    local_now = (now or datetime.now(UTC)).astimezone(BERLIN_TZ)
    effective_day = local_now.date()
    if local_now.timetz().replace(tzinfo=None) < MONITOR_RESET_TIME:
        effective_day -= timedelta(days=1)
    return _previous_weekday(effective_day).isoformat()


def _next_monitor_reset(now: datetime | None = None) -> datetime:
    local_now = (now or datetime.now(UTC)).astimezone(BERLIN_TZ)
    reset_day = local_now.date()
    reset_today = datetime.combine(reset_day, MONITOR_RESET_TIME, BERLIN_TZ)
    if local_now >= reset_today:
        reset_day += timedelta(days=1)
    while reset_day.weekday() >= 5:
        reset_day += timedelta(days=1)
    return datetime.combine(reset_day, MONITOR_RESET_TIME, BERLIN_TZ).astimezone(UTC)


def _previous_weekday(value: date) -> date:
    while value.weekday() >= 5:
        value -= timedelta(days=1)
    return value


def _read_monitor_state() -> dict[str, Any]:
    try:
        payload = settings_repository.read_position_monitor_state()
    except SettingsRepositoryUnavailable:
        return {}
    return payload if isinstance(payload, dict) else {}


def _float_or_none(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None
