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
from app.services.stocks import get_stock_assessment
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

        signal_alerts = _apply_portfolio_signal_state(
            result,
            monitor_settings=monitor_settings,
        )
        signal_alert_delivery = _deliver_monitor_alerts(signal_alerts, app_settings=settings)
        _finalize_portfolio_signal_state(result, alert_delivery=signal_alert_delivery)
        result["signal_alerts"] = signal_alerts
        result["signal_alert_delivery"] = signal_alert_delivery

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
        else:
            if decision["state_update"] is not None:
                ticker_state[ticker] = decision["state_update"]
        if decision["suppression"] is not None:
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
        "sent_alert_ids": [],
        "errors": [],
    }
    if not alerts:
        result["reason"] = "Keine neuen Positionssignale."
        return result
    if not app_settings.pushover_enabled:
        result.update(skipped=len(alerts), reason="Pushover ist in den Settings deaktiviert.")
        _record_delivery_logs(alerts, status="skipped", detail=result["reason"])
        return result

    runtime = get_runtime_settings()
    user_key = get_runtime_config_value("PUSHOVER_USER_KEY") or runtime.pushover_user_key
    app_token = get_runtime_config_value("PUSHOVER_APP_TOKEN") or runtime.pushover_app_token
    dry_run = get_runtime_config_bool("PUSHOVER_DRY_RUN", runtime.pushover_dry_run)
    result.update(configured=bool(user_key and app_token), dry_run=dry_run)
    if not user_key or not app_token:
        result.update(skipped=len(alerts), reason="PUSHOVER_USER_KEY oder PUSHOVER_APP_TOKEN fehlt.")
        _record_delivery_logs(alerts, status="skipped", detail=result["reason"])
        return result
    if dry_run:
        result.update(skipped=len(alerts), reason="PUSHOVER_DRY_RUN ist aktiv.")
        _record_delivery_logs(alerts, status="skipped", detail=result["reason"])
        return result

    delivery_logs: list[dict[str, Any]] = []
    for alert in alerts:
        try:
            response = _send_pushover_message(
                user_key=user_key,
                app_token=app_token,
                message=_format_monitor_alert_message(alert),
                title=_monitor_alert_title(alert),
                priority=1,
            )
            if int(response.get("status") or 0) != 1:
                raise RuntimeError(f"Pushover hat den Alarm nicht bestätigt: {response}")
            result["sent"] += 1
            result["sent_tickers"].append(str(alert.get("ticker") or "").strip().upper())
            result["sent_alert_ids"].append(str(alert.get("alert_id") or ""))
            delivery_logs.append(_delivery_log_item(alert, status="sent", detail="Pushover hat den Alarm bestätigt."))
        except Exception as exc:  # noqa: BLE001 - alert delivery must not crash the monitor job
            result["failed"] += 1
            detail = f"{type(exc).__name__}: {exc}"
            result["errors"].append(f"{alert.get('ticker', 'UNKNOWN')}: {detail}")
            delivery_logs.append(_delivery_log_item(alert, status="failed", detail=detail))
    _append_delivery_logs(delivery_logs)
    result["ok"] = result["failed"] == 0
    return result


def _record_delivery_logs(alerts: list[dict[str, Any]], *, status: str, detail: str) -> None:
    _append_delivery_logs([_delivery_log_item(alert, status=status, detail=detail) for alert in alerts])


def _delivery_log_item(alert: dict[str, Any], *, status: str, detail: str) -> dict[str, Any]:
    return {
        "timestamp": datetime.now(UTC).isoformat(),
        "ticker": str(alert.get("ticker") or "").strip().upper(),
        "status": status,
        "detail": detail,
        "distance_atr": _float_or_none(alert.get("distance_atr")),
        "threshold_atr": _float_or_none(alert.get("threshold_atr")),
        "reference_label": str(alert.get("reference_label") or alert.get("reference") or ""),
        "kind": str(alert.get("kind") or "atr"),
        "alert_id": str(alert.get("alert_id") or ""),
    }


def _append_delivery_logs(entries: list[dict[str, Any]]) -> None:
    if not entries:
        return
    try:
        settings_repository.append_pushover_delivery_log(entries)
    except SettingsRepositoryUnavailable:
        return


def _format_monitor_alert_message(alert: dict[str, Any]) -> str:
    if str(alert.get("kind") or "atr") == "stock_signal":
        return _format_stock_signal_alert_message(alert)
    ticker = str(alert.get("ticker") or "UNKNOWN")
    distance = _float_or_none(alert.get("distance_atr")) or 0.0
    threshold = _float_or_none(alert.get("threshold_atr")) or 0.0
    reference = str(alert.get("reference_label") or alert.get("reference") or "Referenz")
    current_price = alert.get("current_price")
    reference_price = alert.get("reference_price")
    reason = str(alert.get("reason") or "")
    reason_labels = {
        "2x_atr_escalation": "2x ATR Eskalation",
        "monitor_configuration_changed": "Referenz oder ATR-Schwelle geändert",
        "threshold_recrossed": "ATR-Schwelle nach Erholung erneut unterschritten",
    }
    reason_text = reason_labels.get(reason, "ATR-Schwelle neu überschritten")
    return (
        f"{ticker}: ATR-Abstand {distance:.2f} >= {threshold:.2f}\n"
        f"Referenz: {reference}\n"
        f"Aktueller Kurs: {current_price}; Referenzkurs: {reference_price}\n"
        f"Auslöser: {reason_text}"
    )


def _monitor_alert_title(alert: dict[str, Any]) -> str:
    ticker = str(alert.get("ticker") or "Position")
    if str(alert.get("kind") or "atr") != "stock_signal":
        return f"ATR-Alarm {ticker}"
    events = alert.get("events") if isinstance(alert.get("events"), list) else []
    has_warning = any(str(event.get("tone") or "") == "warning" for event in events if isinstance(event, dict))
    return f"Depot-Warnung {ticker}" if has_warning else f"Depot-Update {ticker}"


def _format_stock_signal_alert_message(alert: dict[str, Any]) -> str:
    ticker = str(alert.get("ticker") or "UNKNOWN")
    events = alert.get("events") if isinstance(alert.get("events"), list) else []
    lines = [f"{ticker}: Aktienbewertung hat sich geändert"]
    current_price = _float_or_none(alert.get("current_price"))
    currency = str(alert.get("currency") or "USD")
    if current_price is not None:
        lines.append(f"Kurs: {current_price:.2f} {currency}")
    for event in events[:8]:
        if not isinstance(event, dict):
            continue
        prefix = "WARNUNG" if str(event.get("tone") or "") == "warning" else "ERHOLT" if str(event.get("tone") or "") == "good" else "BEWERTUNG"
        lines.append(f"{prefix}: {str(event.get('label') or '').strip()}")
        detail = str(event.get("detail") or "").strip()
        if detail:
            lines.append(detail)
    as_of = str(alert.get("as_of") or "").strip()
    if as_of:
        lines.append(f"Datenstand: {as_of}")
    return "\n".join(lines)[:1000]


def _apply_portfolio_signal_state(
    result: dict[str, Any],
    *,
    monitor_settings: dict[str, Any],
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Compare portfolio trend and assessment state without repeating alerts."""

    now = now or datetime.now(UTC)
    state = _read_monitor_state()
    stored_tickers = state.get("signal_tickers") if isinstance(state.get("signal_tickers"), dict) else {}
    pending: dict[str, dict[str, Any]] = {}
    alerts: list[dict[str, Any]] = []
    ma_enabled = bool(monitor_settings.get("position_monitor_ma_alerts_enabled", True))
    assessment_enabled = bool(monitor_settings.get("position_monitor_assessment_alerts_enabled", True))
    interval_minutes = max(
        5,
        min(120, int(_float_or_none(monitor_settings.get("position_monitor_assessment_interval_minutes")) or 15)),
    )

    for item in result.get("items", []):
        if not isinstance(item, dict):
            continue
        ticker = str(item.get("ticker") or "").strip().upper()
        if not ticker:
            continue
        previous = stored_tickers.get(ticker) if isinstance(stored_tickers.get(ticker), dict) else {}
        current = dict(previous)
        events: list[dict[str, str]] = []

        trend = item.get("trend_monitor") if isinstance(item.get("trend_monitor"), dict) else {}
        current_ma = _normalized_ma_state(trend)
        if current_ma:
            if ma_enabled:
                events.extend(_moving_average_events(previous.get("moving_averages"), trend))
            current["moving_averages"] = current_ma
            current["trend_as_of"] = str(trend.get("as_of") or "")
            current["current_price"] = _float_or_none(trend.get("current_price"))
            current["currency"] = str(trend.get("currency") or "USD")

        prior_assessment = previous.get("assessment") if isinstance(previous.get("assessment"), dict) else {}
        if assessment_enabled and _assessment_check_due(
            previous,
            price_as_of=str(item.get("as_of") or ""),
            now=now,
            interval_minutes=interval_minutes,
        ):
            try:
                assessment = get_stock_assessment(ticker)
                summary = _assessment_state(assessment.model_dump(mode="json"))
                if summary.get("source") == "database":
                    if prior_assessment:
                        events.extend(_assessment_events(prior_assessment, summary))
                    current["assessment"] = summary
                    current["assessment_checked_at"] = now.isoformat()
            except Exception as exc:  # noqa: BLE001 - one assessment must not stop live monitoring
                item.setdefault("warnings", []).append(
                    f"Aktienbewertung konnte nicht verglichen werden: {type(exc).__name__}: {exc}"
                )

        current["last_seen_at"] = now.isoformat()
        alert_id = ""
        if events:
            alert_id = f"stock-signal:{ticker}:{int(now.timestamp())}"
            alerts.append(
                {
                    "kind": "stock_signal",
                    "alert_id": alert_id,
                    "ticker": ticker,
                    "current_price": current.get("current_price"),
                    "currency": current.get("currency") or "USD",
                    "as_of": current.get("trend_as_of") or item.get("as_of") or "",
                    "events": events[:12],
                }
            )
        pending[ticker] = {
            "previous": previous,
            "current": current,
            "alert_id": alert_id,
        }

    result["_pending_signal_state"] = {
        "base_state": state,
        "tickers": pending,
        "finished_at": now.isoformat(),
    }
    return alerts


def _finalize_portfolio_signal_state(
    result: dict[str, Any],
    *,
    alert_delivery: dict[str, Any],
) -> None:
    pending = result.pop("_pending_signal_state", None)
    if not isinstance(pending, dict):
        return
    state = pending.get("base_state") if isinstance(pending.get("base_state"), dict) else {}
    pending_tickers = pending.get("tickers") if isinstance(pending.get("tickers"), dict) else {}
    sent_ids = {
        str(value)
        for value in alert_delivery.get("sent_alert_ids", [])
        if str(value)
    }
    next_tickers: dict[str, Any] = {}
    for ticker, transition in pending_tickers.items():
        if not isinstance(transition, dict):
            continue
        alert_id = str(transition.get("alert_id") or "")
        previous = transition.get("previous") if isinstance(transition.get("previous"), dict) else {}
        current = transition.get("current") if isinstance(transition.get("current"), dict) else {}
        if not alert_id or alert_id in sent_ids:
            next_tickers[str(ticker)] = current
        elif previous:
            next_tickers[str(ticker)] = previous
    state["signal_tickers"] = next_tickers
    state["last_signal_finished_at"] = str(pending.get("finished_at") or "")
    try:
        settings_repository.write_position_monitor_state(state)
    except SettingsRepositoryUnavailable as exc:
        result.setdefault("warnings", []).append(f"Warnzeichen-State konnte nicht gespeichert werden: {exc}")


def _normalized_ma_state(trend: dict[str, Any]) -> dict[str, Any]:
    raw = trend.get("moving_averages") if isinstance(trend.get("moving_averages"), dict) else {}
    normalized: dict[str, Any] = {}
    for key, value in raw.items():
        if not isinstance(value, dict) or not isinstance(value.get("above"), bool):
            continue
        normalized[str(key)] = {
            "label": str(value.get("label") or key),
            "value": _float_or_none(value.get("value")),
            "above": bool(value.get("above")),
            "distance_pct": _float_or_none(value.get("distance_pct")),
        }
    return normalized


def _moving_average_events(previous_value: Any, trend: dict[str, Any]) -> list[dict[str, str]]:
    previous = previous_value if isinstance(previous_value, dict) else {}
    raw = trend.get("moving_averages") if isinstance(trend.get("moving_averages"), dict) else {}
    price = _float_or_none(trend.get("current_price"))
    currency = str(trend.get("currency") or "USD")
    events: list[dict[str, str]] = []
    for key in ("sma10", "ema21", "sma50", "sma200"):
        current = raw.get(key) if isinstance(raw.get(key), dict) else {}
        if not isinstance(current.get("above"), bool):
            continue
        prior = previous.get(key) if isinstance(previous.get(key), dict) else {}
        prior_above = prior.get("above") if isinstance(prior.get("above"), bool) else current.get("previous_above")
        if not isinstance(prior_above, bool) or prior_above == current["above"]:
            continue
        label = str(current.get("label") or key)
        average = _float_or_none(current.get("value"))
        distance = _float_or_none(current.get("distance_pct"))
        values = []
        if price is not None:
            values.append(f"Kurs {price:.2f} {currency}")
        if average is not None:
            values.append(f"{label} {average:.2f}")
        if distance is not None:
            values.append(f"Abstand {distance:+.2f}%")
        events.append(
            {
                "tone": "good" if current["above"] else "warning",
                "label": f"{label} zurückerobert" if current["above"] else f"Bruch der {label}",
                "detail": " · ".join(values),
            }
        )
    return events


def _assessment_check_due(
    previous: dict[str, Any],
    *,
    price_as_of: str,
    now: datetime,
    interval_minutes: int,
) -> bool:
    assessment = previous.get("assessment") if isinstance(previous.get("assessment"), dict) else {}
    if not assessment or str(assessment.get("as_of") or "") != price_as_of:
        return True
    checked_at = _parse_datetime(previous.get("assessment_checked_at"))
    return checked_at is None or now - checked_at >= timedelta(minutes=interval_minutes)


def _assessment_state(raw: dict[str, Any]) -> dict[str, Any]:
    checks: dict[str, Any] = {}
    for item in raw.get("checks", []):
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or "").strip()
        if not label:
            continue
        checks[label] = {
            "passed": bool(item.get("passed")),
            "category": str(item.get("category") or ""),
            "severity": str(item.get("severity") or "info"),
            "detail": str(item.get("detail") or ""),
        }
    signals: dict[str, Any] = {}
    for item in raw.get("chart_signals", []):
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or "").strip()
        category = str(item.get("category") or "")
        if label:
            signals[f"{category}:{label}"] = {
                "label": label,
                "category": category,
                "detail": str(item.get("detail") or ""),
            }
    scores = raw.get("scores") if isinstance(raw.get("scores"), dict) else {}
    return {
        "source": str(raw.get("source") or "missing"),
        "as_of": str(raw.get("as_of") or ""),
        "verdict_label": str(raw.get("verdict_label") or ""),
        "verdict_tone": str(raw.get("verdict_tone") or ""),
        "overall_score": int(_float_or_none(scores.get("overall")) or 0),
        "checks": checks,
        "signals": signals,
    }


def _assessment_events(previous: dict[str, Any], current: dict[str, Any]) -> list[dict[str, str]]:
    events: list[dict[str, str]] = []
    previous_checks = previous.get("checks") if isinstance(previous.get("checks"), dict) else {}
    current_checks = current.get("checks") if isinstance(current.get("checks"), dict) else {}
    for label, check in current_checks.items():
        if not isinstance(check, dict) or str(label).startswith("Kurs über "):
            continue
        old = previous_checks.get(label) if isinstance(previous_checks.get(label), dict) else None
        if old is None or bool(old.get("passed")) == bool(check.get("passed")):
            continue
        events.append(
            {
                "tone": "good" if bool(check.get("passed")) else "warning",
                "label": f"Kriterium wieder erfüllt: {label}" if bool(check.get("passed")) else f"Neues Warnzeichen: {label}",
                "detail": str(check.get("detail") or ""),
            }
        )

    previous_signals = previous.get("signals") if isinstance(previous.get("signals"), dict) else {}
    current_signals = current.get("signals") if isinstance(current.get("signals"), dict) else {}
    for key, signal in current_signals.items():
        if not isinstance(signal, dict) or signal.get("category") != "negative" or key in previous_signals:
            continue
        events.append(
            {
                "tone": "warning",
                "label": f"Neues Warnzeichen: {signal.get('label', '')}",
                "detail": str(signal.get("detail") or ""),
            }
        )
    for key, signal in previous_signals.items():
        if not isinstance(signal, dict) or signal.get("category") != "negative" or key in current_signals:
            continue
        events.append(
            {
                "tone": "good",
                "label": f"Warnzeichen beendet: {signal.get('label', '')}",
                "detail": str(signal.get("detail") or ""),
            }
        )

    old_score = int(_float_or_none(previous.get("overall_score")) or 0)
    new_score = int(_float_or_none(current.get("overall_score")) or 0)
    if old_score != new_score:
        events.append(
            {
                "tone": "warning" if new_score < old_score else "good",
                "label": f"Gesamtscore {old_score} → {new_score}",
                "detail": f"Veränderung {new_score - old_score:+d} Punkte.",
            }
        )
    old_verdict = str(previous.get("verdict_label") or "")
    new_verdict = str(current.get("verdict_label") or "")
    if old_verdict and new_verdict and old_verdict != new_verdict:
        events.append(
            {
                "tone": "warning" if str(current.get("verdict_tone") or "") in {"warning", "bad"} else "good",
                "label": f"Bewertung: {old_verdict} → {new_verdict}",
                "detail": "Das zusammengefasste Aktienurteil hat sich geändert.",
            }
        )
    return events[:12]


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value))
        except (TypeError, ValueError):
            return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


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
    previous = ticker_state.get(ticker) if isinstance(ticker_state.get(ticker), dict) else {}
    current_reference = str(monitor.get("reference") or "")
    current_reference_price = _float_or_none(monitor.get("reference_price"))
    if not crossed:
        state_update = None
        if previous:
            state_update = {
                **previous,
                "trade_day": trade_day,
                "threshold_atr": threshold_atr,
                "reference": current_reference,
                "reference_price": current_reference_price,
                "current_price": _float_or_none(monitor.get("current_price")),
                "threshold_crossed": False,
                "escalated_2x": False,
            }
        return {
            "allowed": False,
            "monitor_update": monitor_update,
            "state_update": state_update,
            "alert": None,
            "suppression": None,
        }

    previous_trade_day = str(previous.get("trade_day") or "")
    previous_distance = _float_or_none(previous.get("last_distance_atr"))
    previous_reference_price = _float_or_none(previous.get("reference_price"))
    previous_reference = str(previous.get("reference") or "")
    previous_threshold = _float_or_none(previous.get("threshold_atr"))
    two_x_threshold = threshold_atr * 2
    is_two_x = distance_atr >= two_x_threshold
    previous_two_x = bool(previous.get("escalated_2x"))
    is_new_trade_day = previous_trade_day != trade_day
    reference_mode_changed = bool(previous_reference and previous_reference != current_reference)
    threshold_changed = bool(
        previous_threshold is not None
        and not math.isclose(previous_threshold, threshold_atr, rel_tol=1e-9, abs_tol=1e-9)
    )
    rearmed_after_recovery = bool(previous and previous.get("threshold_crossed") is False)
    reference_changed = (
        previous_reference_price is not None
        and current_reference_price is not None
        and abs(previous_reference_price - current_reference_price)
        > max(0.01, abs(previous_reference_price) * 0.0001)
    )
    distance_deeper = previous_distance is None or distance_atr > previous_distance + 0.25
    fresh_new_trade_day = is_new_trade_day and (not previous_trade_day or reference_changed or distance_deeper)
    configuration_changed = reference_mode_changed or threshold_changed
    allowed = configuration_changed or rearmed_after_recovery or fresh_new_trade_day or (is_two_x and not previous_two_x)
    reason = (
        "monitor_configuration_changed"
        if configuration_changed
        else "threshold_recrossed"
        if rearmed_after_recovery
        else "new_trade_day"
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
        "reference": current_reference,
        "reference_price": current_reference_price,
        "current_price": _float_or_none(monitor.get("current_price")),
        "threshold_crossed": True,
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
