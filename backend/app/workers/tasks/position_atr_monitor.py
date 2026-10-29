from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from app.domain.sell.service import monitor_open_position_atr
from app.repositories import jobs as job_repository
from app.repositories import settings as settings_repository
from app.repositories.settings import SettingsRepositoryUnavailable
from app.notification_preferences import NotificationPreferences, merge_preferences
from app.schemas import AppSettings
from app.services.settings import get_app_settings
from app.services.stocks import get_stock_assessment
from app.workers.celery_app import celery_app
from app.workers.tasks.common import JobCancelled, raise_if_cancelled
from app.workers.tasks.pushover_test import _send_pushover_message


BERLIN_TZ = ZoneInfo("Europe/Berlin")
MONITOR_RESET_TIME = time(7, 30)
IMMEDIATE_MA_KEYS = ("sma10", "ema21", "sma50", "sma200")


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

        try:
            monitor_settings["atr_rearm_requests"] = settings_repository.read_atr_rearm_requests()
        except SettingsRepositoryUnavailable:
            monitor_settings["atr_rearm_requests"] = {}
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
        result = monitor_open_position_atr(
            tickers=tickers or None, monitor_settings=monitor_settings
        )
        if result.get("skipped"):
            job_repository.mark_skipped(
                job.job_id, message=str(result.get("reason") or "Keine Positionen."), result=result
            )
            return result
        from app.services.stop_alerts import deliver_stop_alerts

        result = _apply_cooldown_state(
            result, monitor_settings=monitor_settings, persist_state=False
        )
        signal_alerts = _apply_portfolio_signal_state(result, monitor_settings=monitor_settings)
        result["stop_delivery"] = deliver_stop_alerts(
            [
                item["stop_observation"]
                for item in result.get("items", [])
                if item.get("stop_observation")
            ],
            lambda alerts: _deliver_monitor_alerts(
                alerts, app_settings=settings, observations=result.get("items", [])
            ),
            preferences=_preferences(monitor_settings)["stop"],
            additional_alerts=[*result.get("alerts", []), *signal_alerts],
        )
        delivery = result["stop_delivery"].get("delivery", {"accepted_alert_ids": [], "failed": 1})
        _finalize_monitor_state(result, alert_delivery=delivery)
        _finalize_portfolio_signal_state(result, alert_delivery=delivery)
        result["alert_delivery"] = delivery
        result["signal_alerts"] = signal_alerts
        result["signal_alert_delivery"] = delivery
        if isinstance(result.get("last_summary"), dict):
            result["last_summary"]["sent"] = delivery.get("sent", 0)

        raise_if_cancelled(job.job_id)
        job_repository.update_progress(
            job.job_id,
            progress=90,
            step="Monitor-State schreiben",
            message=f"{result.get('records_written', 0)} Positionen live geprüft.",
            result=result,
        )
        job_repository.mark_done(
            job.job_id, result=result, message="Positionsmonitor aktualisiert."
        )
        return result
    except JobCancelled:
        job_repository.mark_cancelled(job.job_id)
        return {"ok": False, "cancelled": True, "job_type": "position_atr_monitor"}
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        job_repository.mark_failed(
            job.job_id,
            error_message=error,
            result={"ok": False, "job_type": "position_atr_monitor"},
        )
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
    state = copy.deepcopy(_read_monitor_state())
    previous_tickers = copy.deepcopy(state.get("tickers", {}))
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
        result["_previous_monitor_tickers"] = previous_tickers

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
        for ticker in alert_delivery.get("accepted_tickers", alert_delivery.get("sent_tickers", []))
        if str(ticker).strip()
    }
    ticker_state = state.get("tickers") if isinstance(state.get("tickers"), dict) else {}
    previous_tickers = result.pop("_previous_monitor_tickers", {})
    accepted_ids = set(alert_delivery.get("accepted_alert_ids") or [])
    for alert in result.get("alerts", []):
        ticker = str(alert.get("ticker") or "").strip().upper() if isinstance(alert, dict) else ""
        accepted = (
            alert.get("alert_id") in accepted_ids
            if "accepted_alert_ids" in alert_delivery
            else ticker in sent_tickers
        )
        if ticker and not accepted:
            if ticker in previous_tickers:
                ticker_state[ticker] = previous_tickers[ticker]
            else:
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
    if isinstance(result.get("_pending_signal_state"), dict):
        result["_pending_signal_state"]["base_state"] = copy.deepcopy(state)
    _write_monitor_state(result, state)


def _write_monitor_state(result: dict[str, Any], state: dict[str, Any]) -> None:
    try:
        settings_repository.write_position_monitor_state(state)
    except SettingsRepositoryUnavailable as exc:
        result.setdefault("warnings", []).append(
            f"Positionsmonitor-State konnte nicht gespeichert werden: {exc}"
        )


def _deliver_monitor_alerts(
    alerts: list[dict[str, Any]],
    *,
    app_settings: AppSettings,
    observations: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    from app.services.notification_delivery import deliver_notifications

    return deliver_notifications(
        alerts,
        app_settings=app_settings,
        send_message=_send_pushover_message,
        observations=observations,
    )


def _preferences(settings: dict[str, Any]) -> dict[str, Any]:
    defaults = NotificationPreferences().model_dump()
    raw = settings.get("notification_preferences")
    if hasattr(raw, "model_dump"):
        raw = raw.model_dump()
    return merge_preferences(defaults, raw) if isinstance(raw, dict) else defaults


def _event_identity(ticker: str, event: dict[str, Any], observation: str) -> str:
    content = json.dumps(
        [ticker, event.get("event_type"), event.get("ma_key"), event.get("label"), observation],
        ensure_ascii=False,
        sort_keys=True,
    )
    return "signal:" + hashlib.sha256(content.encode()).hexdigest()[:28]


def _fresh_quote_at(monitor: dict[str, Any], now: datetime) -> datetime | None:
    quote_at = _parse_datetime(monitor.get("quote_at") or monitor.get("live_quote_at"))
    if quote_at is None or not timedelta(0) <= now - quote_at <= timedelta(minutes=20):
        return None
    return quote_at


def _german_number(value: Any, digits: int = 2) -> str:
    number = _float_or_none(value)
    if number is None:
        return "unbekannt"
    return f"{number:,.{digits}f}".replace(",", "_").replace(".", ",").replace("_", ".")


def _prose(value: Any) -> str:
    text = str(value or "")
    for old, new in (
        (">=", "mindestens "),
        ("<=", "höchstens "),
        ("≥", "mindestens "),
        ("≤", "höchstens "),
        ("→", " auf "),
        (">", "über "),
        ("<", "unter "),
        ("=", " beträgt "),
    ):
        text = text.replace(old, new)
    text = re.sub(r"(?<=\d)\.(?=\d)", ",", text)
    return re.sub(r" {2,}", " ", text).strip()


def _signal_label_prose(event: dict[str, Any]) -> str:
    raw = str(event.get("label") or "")
    subject = _prose(_notification_event_label(raw))
    if raw.startswith("Warnzeichen beendet:"):
        return f"Das Warnzeichen „{subject}“ ist entfallen"
    if raw.startswith("Kriterium wieder erfüllt:"):
        return f"Das Kriterium „{subject}“ ist wieder erfüllt"
    if raw.startswith("Kriterium jetzt bewertbar:"):
        return f"Das Kriterium „{subject}“ lässt sich wieder bewerten"
    if "derzeit nicht bewertbar:" in raw:
        return f"„{subject}“ lässt sich derzeit nicht bewerten"
    if raw.startswith("Neues Warnzeichen:"):
        return f"Neues Warnzeichen: {subject}"
    return _prose(raw)


def _format_monitor_alert_message(alert: dict[str, Any]) -> str:
    ticker = str(alert.get("ticker") or "Deine Position")
    if alert.get("kind") == "stop":
        return (
            f"{alert.get('name') or ticker} hat deinen Stopp erreicht.\n"
            f"Der Kurs liegt bei {_german_number(alert.get('current_price'))} {alert.get('currency', 'USD')}. "
            f"Dein Stopp liegt bei {_german_number(alert.get('stop_price'))} {alert.get('currency', 'USD')}."
        )
    if alert.get("kind") == "stock_signal_summary":
        return _format_stock_signal_summary_message(alert)
    if alert.get("kind") == "stock_signal":
        return _format_stock_signal_alert_message(alert)
    reference = {
        "previous_close": "dem Vortagesschluss",
        "entry_price": "deinem Einstand",
        "high_since_buy": "dem Höchstkurs seit deinem Kauf",
        "close_since_buy": "dem höchsten Schlusskurs seit deinem Kauf",
    }.get(str(alert.get("reference") or ""), "deinem Referenzkurs")
    reason = str(alert.get("reason") or "")
    lead = (
        f"Der Kursrückgang bei {ticker} hat sich deutlich verstärkt."
        if reason == "atr_escalation"
        else f"{ticker} hat deine Verlustschwelle erreicht."
    )
    return (
        f"{lead}\nDer Kurs liegt {_german_number(alert.get('distance_atr'))} ATR unter {reference}. "
        f"Deine Warnschwelle liegt bei {_german_number(alert.get('threshold_atr'))} ATR.\n"
        f"Aktueller Kurs: {_german_number(alert.get('current_price'))} USD. "
        f"Referenzkurs: {_german_number(alert.get('reference_price'))} USD.\n"
        "ATR beschreibt die übliche tägliche Kursschwankung."
    )


def _monitor_alert_title(alert: dict[str, Any]) -> str:
    ticker = str(alert.get("ticker") or "Depot")
    if alert.get("kind") == "stop":
        return f"{ticker} · Dein Stopp ist erreicht"
    if alert.get("kind") == "stock_signal_summary":
        return "Dein Depot · Die wichtigsten Veränderungen"
    if alert.get("kind") != "stock_signal":
        return (
            f"{ticker} · Kursrückgang verstärkt"
            if alert.get("reason") == "atr_escalation"
            else f"{ticker} · Verlustschwelle erreicht"
        )
    events = [event for event in alert.get("events", []) if isinstance(event, dict)]
    if len(events) == 1:
        return f"{ticker} · {_signal_label_prose(events[0])}"[:120]
    warning = any(event.get("tone") == "warning" for event in events)
    return f"{ticker} · Neue Warnzeichen" if warning else f"{ticker} · Neue Entwicklung"


def _format_stock_signal_alert_message(alert: dict[str, Any]) -> str:
    ticker = str(alert.get("ticker") or "Deine Position")
    lines: list[str] = []
    price = _float_or_none(alert.get("current_price"))
    if price is not None:
        lines.append(
            f"{ticker} steht bei {_german_number(price)} {alert.get('currency') or 'USD'}."
        )
    for event in alert.get("events", [])[:8]:
        if not isinstance(event, dict):
            continue
        label = _signal_label_prose(event)
        detail = _prose(event.get("detail"))
        lines.append(label.rstrip(".") + "." + (f" {detail}" if detail else ""))
    return "\n\n".join(lines)[:1000]


def _format_stock_signal_summary_message(alert: dict[str, Any]) -> str:
    lines = ["Die wichtigsten Veränderungen in deinem Depot:"]
    lines.extend(_prose(entry) for entry in alert.get("entries", []) if str(entry).strip())
    if len(lines) == 1:
        lines.append("Heute gibt es keine neuen relevanten Veränderungen.")
    omitted = int(_float_or_none(alert.get("omitted_entries")) or 0)
    if omitted:
        lines.append(f"Weitere {omitted} Hinweise findest du im Dashboard.")
    return "\n".join(lines)[:1000]


def _apply_portfolio_signal_state(
    result: dict[str, Any],
    *,
    monitor_settings: dict[str, Any],
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Detect changes independently of whether their route is immediate, digest or off."""
    now = now or datetime.now(UTC)
    state = copy.deepcopy(_read_monitor_state())
    stored_tickers = (
        state.get("signal_tickers") if isinstance(state.get("signal_tickers"), dict) else {}
    )
    pending: dict[str, dict[str, Any]] = {}
    alerts: list[dict[str, Any]] = []
    preferences = _preferences(monitor_settings)
    assessment_rule = preferences["assessment"]
    interval_minutes = max(
        5,
        min(
            120,
            int(
                _float_or_none(monitor_settings.get("position_monitor_assessment_interval_minutes"))
                or 15
            ),
        ),
    )

    for item in result.get("items", []):
        if not isinstance(item, dict):
            continue
        ticker = str(item.get("ticker") or "").strip().upper()
        if not ticker:
            continue
        previous = (
            stored_tickers.get(ticker) if isinstance(stored_tickers.get(ticker), dict) else {}
        )
        current = copy.deepcopy(previous)
        trend = item.get("trend_monitor") if isinstance(item.get("trend_monitor"), dict) else {}
        monitor = item.get("monitor") if isinstance(item.get("monitor"), dict) else {}
        events = _update_moving_average_signal_state(
            previous=previous,
            current=current,
            trend=trend,
            monitor=monitor,
            now=now,
            closed_trend=item.get("closed_trend_monitor"),
            preferences=preferences["ma"],
        )
        current_ma = _normalized_ma_state(trend)
        if current_ma:
            current["moving_averages"] = current_ma
            current["trend_as_of"] = str(trend.get("as_of") or "")
            current["current_price"] = _float_or_none(trend.get("current_price"))
            current["currency"] = str(trend.get("currency") or "USD")

        prior = previous.get("assessment") if isinstance(previous.get("assessment"), dict) else {}
        if _assessment_check_due(
            previous,
            price_as_of=str(item.get("as_of") or ""),
            now=now,
            interval_minutes=interval_minutes,
        ):
            try:
                summary = _assessment_state(get_stock_assessment(ticker).model_dump(mode="json"))
                if summary.get("source") == "database":
                    if prior:
                        for event in _assessment_events(prior, summary, include_score=False):
                            is_verdict = event.get("event_type") == "verdict"
                            event.update(
                                category="verdict",
                                event_type="verdict" if is_verdict else "assessment_detail",
                                mode=assessment_rule["verdict_mode"]
                                if is_verdict
                                else (
                                    "off" if assessment_rule["verdict_mode"] == "off" else "digest"
                                ),
                                priority=assessment_rule["priority"],
                                session=assessment_rule["session"],
                                observation=str(summary.get("as_of") or ""),
                            )
                            _apply_assessment_direction(event, assessment_rule)
                            events.append(event)
                    score = int(_float_or_none(summary.get("overall_score")) or 0)
                    anchor_value = _float_or_none(current.get("score_notification_anchor"))
                    if anchor_value is None:
                        anchor_value = _float_or_none(prior.get("overall_score"))
                    anchor = int(score if anchor_value is None else anchor_value)
                    delta = score - anchor
                    if abs(delta) >= assessment_rule["score_min_change"]:
                        score_event = {
                            "tone": "warning" if delta < 0 else "good",
                            "category": "score",
                            "event_type": "score",
                            "label": f"Gesamtscore von {anchor} auf {score} {'gefallen' if delta < 0 else 'gestiegen'}",
                            "detail": f"Der Score hat sich seit der letzten erfassten Änderung um {abs(delta)} Punkte {'verschlechtert' if delta < 0 else 'verbessert'}.",
                            "mode": assessment_rule["score_mode"],
                            "priority": assessment_rule["priority"],
                            "session": assessment_rule["session"],
                            "observation": str(summary.get("as_of") or ""),
                        }
                        _apply_assessment_direction(score_event, assessment_rule)
                        events.append(score_event)
                        current["score_notification_anchor"] = score
                    else:
                        current["score_notification_anchor"] = anchor
                    current["assessment"] = summary
                    current["assessment_checked_at"] = now.isoformat()
                    item["notification_assessment"] = summary
            except Exception as exc:  # noqa: BLE001 - one unavailable assessment must not stop monitoring
                item.setdefault("warnings", []).append(
                    f"Aktienbewertung konnte nicht verglichen werden: {type(exc).__name__}: {exc}"
                )

        current["last_seen_at"] = now.isoformat()
        for event in events:
            event["event_id"] = _event_identity(ticker, event, str(event.pop("observation", "")))
            if event.get("category") == "ma":
                event["limit_key"] = f"ma:{ticker}:{event.get('ma_key')}"
        alert_id = ""
        if events:
            identities = ":".join(event["event_id"] for event in events)
            alert_id = (
                f"stock-signal:{ticker}:" + hashlib.sha256(identities.encode()).hexdigest()[:24]
            )
            alerts.append(
                {
                    "kind": "stock_signal",
                    "alert_id": alert_id,
                    "ticker": ticker,
                    "name": item.get("name") or ticker,
                    "current_price": current.get("current_price"),
                    "currency": current.get("currency") or "USD",
                    "as_of": current.get("trend_as_of") or item.get("as_of") or "",
                    "events": events,
                }
            )
        pending[ticker] = {"previous": previous, "current": current, "alert_id": alert_id}

    result["_pending_signal_state"] = {
        "base_state": state,
        "tickers": pending,
        "finished_at": now.isoformat(),
    }
    return alerts


def _apply_assessment_direction(event: dict[str, Any], rule: dict[str, Any]) -> None:
    if (event.get("tone") == "good" and not rule["notify_improvements"]) or (
        event.get("tone") == "warning" and not rule["notify_deteriorations"]
    ):
        event["mode"] = "off"
        event["suppression_reason"] = "direction_disabled"


def _finalize_portfolio_signal_state(
    result: dict[str, Any], *, alert_delivery: dict[str, Any]
) -> None:
    pending = result.pop("_pending_signal_state", None)
    if not isinstance(pending, dict):
        return
    state = pending.get("base_state") if isinstance(pending.get("base_state"), dict) else {}
    accepted_ids = set(
        alert_delivery.get("accepted_alert_ids", alert_delivery.get("sent_alert_ids", []))
    )
    next_tickers = dict(state.get("signal_tickers") or {})
    for ticker, transition in pending.get("tickers", {}).items():
        if not isinstance(transition, dict):
            continue
        alert_id = str(transition.get("alert_id") or "")
        previous = (
            transition.get("previous") if isinstance(transition.get("previous"), dict) else {}
        )
        if not alert_id or alert_id in accepted_ids:
            next_tickers[ticker] = transition["current"]
        elif previous:
            next_tickers[ticker] = previous
    state["signal_tickers"] = next_tickers
    state["last_signal_finished_at"] = str(pending.get("finished_at") or "")
    try:
        settings_repository.write_position_monitor_state(state)
    except SettingsRepositoryUnavailable as exc:
        result.setdefault("warnings", []).append(
            f"Warnzeichen-State konnte nicht gespeichert werden: {exc}"
        )


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


MA_LABELS = {
    "sma10": "10-Tage-Linie",
    "ema21": "21-Tage-Linie (EMA)",
    "sma50": "50-Tage-Linie",
    "sma200": "200-Tage-Linie",
}


def _confirm_observation(
    state: dict[str, Any],
    *,
    prefix: str,
    target: str,
    observed_at: datetime,
    minutes: int,
    close: bool = False,
) -> bool:
    if close:
        return True
    since = _parse_datetime(state.get(f"{prefix}_since"))
    last = _parse_datetime(state.get("last_observation_at"))
    contiguous = last is None or observed_at - last <= timedelta(minutes=3)
    if (
        state.get(f"{prefix}_zone") != target
        or since is None
        or since > observed_at
        or not contiguous
    ):
        since, count = observed_at, 1
    else:
        count = int(state.get(f"{prefix}_count") or 0) + 1
    state.update(
        {f"{prefix}_zone": target, f"{prefix}_since": since.isoformat(), f"{prefix}_count": count}
    )
    return count >= 2 and observed_at - since >= timedelta(minutes=minutes)


def _clear_confirmation(state: dict[str, Any], prefix: str) -> None:
    state.update({f"{prefix}_zone": "", f"{prefix}_since": "", f"{prefix}_count": 0})


def _update_moving_average_signal_state(
    *,
    previous: dict[str, Any],
    current: dict[str, Any],
    trend: dict[str, Any],
    monitor: dict[str, Any],
    now: datetime,
    digest: dict[str, Any] | None = None,
    closed_trend: dict[str, Any] | None = None,
    preferences: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    rules = preferences or NotificationPreferences().model_dump()["ma"]
    state_by_ma = copy.deepcopy(current.get("ma_alert_state") or {})
    events: list[dict[str, Any]] = []
    for key in IMMEDIATE_MA_KEYS:
        rule = rules[key]
        is_close = rule["confirmation"] == "close"
        selected = closed_trend if is_close else trend
        if not isinstance(selected, dict) or (is_close and not selected.get("is_final")):
            continue
        raw = selected.get("moving_averages") or {}
        value = raw.get(key) if isinstance(raw.get(key), dict) else {}
        distance_pct = _float_or_none(value.get("distance_pct"))
        if distance_pct is None or not isinstance(value.get("above"), bool):
            continue
        price = _float_or_none(selected.get("current_price"))
        if price is None or price <= 0:
            continue
        if is_close:
            observation = str(selected.get("as_of") or "")
            try:
                observed_at = datetime.combine(date.fromisoformat(observation), time(), UTC)
            except ValueError:
                continue
        else:
            observed_at = _fresh_quote_at(
                {"quote_at": selected.get("quote_at") or monitor.get("live_quote_at")}, now
            )
            if observed_at is None:
                continue
            observation = observed_at.isoformat()
        ma_state = copy.deepcopy(state_by_ma.get(key) or {})
        previous_observation = str(ma_state.get("last_observation") or "")
        last_at = _parse_datetime(ma_state.get("last_observation_at"))
        if ma_state.get("confirmation_kind") == rule["confirmation"] and (
            previous_observation == observation or (last_at is not None and observed_at <= last_at)
        ):
            continue
        if ma_state.get("confirmation_kind") != rule["confirmation"]:
            _clear_confirmation(ma_state, "candidate")
            _clear_confirmation(ma_state, "worsening")
        atr_value = _float_or_none(monitor.get("atr_value"))
        atr_pct = _float_or_none(selected.get("atr_pct"))
        normalized_price = _float_or_none(monitor.get("current_price"))
        if atr_pct is None and atr_value is not None and atr_value > 0 and normalized_price:
            # Both monitor values are normalized to USD; the trend price may
            # instead be quoted in EUR, GBP or another listing currency.
            atr_pct = atr_value / normalized_price * 100
        if atr_pct is not None and atr_pct <= 0:
            atr_pct = None
        if rule["distance_unit"] == "atr" and atr_pct is None:
            continue
        threshold_pct = (
            rule["min_distance"] * atr_pct
            if rule["distance_unit"] == "atr"
            else rule["min_distance"]
        )
        distance_atr = abs(distance_pct) / atr_pct if atr_pct else None
        zone = (
            "below"
            if distance_pct <= -threshold_pct
            else "above"
            if distance_pct >= threshold_pct
            else "neutral"
        )
        if not ma_state.get("initialized"):
            # Establish a baseline without sending every pre-existing condition.
            ma_state.update(
                initialized=True,
                stable_zone=zone if zone != "neutral" else ("above" if value["above"] else "below"),
                last_warning_distance_atr=distance_atr if zone == "below" else None,
            )
        else:
            stable_zone = str(ma_state.get("stable_zone") or "neutral")
            if zone not in {"neutral", stable_zone}:
                if _confirm_observation(
                    ma_state,
                    prefix="candidate",
                    target=zone,
                    observed_at=observed_at,
                    minutes=rule["confirmation_minutes"],
                    close=is_close,
                ):
                    recovering = zone == "above"
                    events.append(
                        _ma_event(
                            key,
                            "ma_recovery" if recovering else "ma_break",
                            rule,
                            value,
                            selected,
                            distance_pct,
                            distance_atr,
                            observation,
                        )
                    )
                    ma_state.update(
                        stable_zone=zone,
                        last_warning_distance_atr=distance_atr if zone == "below" else None,
                    )
                    _clear_confirmation(ma_state, "candidate")
                    _clear_confirmation(ma_state, "worsening")
            else:
                _clear_confirmation(ma_state, "candidate")
                anchor = _float_or_none(ma_state.get("last_warning_distance_atr"))
                worsening = (
                    zone == "below"
                    and distance_atr is not None
                    and anchor is not None
                    and distance_atr >= anchor + rule["worsening_atr"]
                )
                if worsening and _confirm_observation(
                    ma_state,
                    prefix="worsening",
                    target="below",
                    observed_at=observed_at,
                    minutes=rule["confirmation_minutes"],
                    close=is_close,
                ):
                    events.append(
                        _ma_event(
                            key,
                            "ma_worsening",
                            rule,
                            value,
                            selected,
                            distance_pct,
                            distance_atr,
                            observation,
                        )
                    )
                    ma_state["last_warning_distance_atr"] = distance_atr
                    _clear_confirmation(ma_state, "worsening")
                elif not worsening:
                    _clear_confirmation(ma_state, "worsening")
        ma_state.update(
            last_observation=observation,
            last_observation_at=observed_at.isoformat(),
            confirmation_kind=rule["confirmation"],
            current_zone=zone,
            current_distance_pct=distance_pct,
            current_distance_atr=distance_atr,
            threshold_pct=threshold_pct,
            atr_pct=atr_pct,
            updated_at=now.isoformat(),
        )
        state_by_ma[key] = ma_state
    current["ma_alert_state"] = state_by_ma
    return events


def _ma_event(
    key: str,
    event_type: str,
    rule: dict[str, Any],
    value: dict[str, Any],
    trend: dict[str, Any],
    distance_pct: float,
    distance_atr: float | None,
    observation: str,
) -> dict[str, Any]:
    label = MA_LABELS[key]
    recovering = event_type == "ma_recovery"
    suffix = (
        "zurückerobert"
        if recovering
        else "weiter unterschritten"
        if event_type == "ma_worsening"
        else "unterschritten"
    )
    mode_key = (
        "recovery_mode"
        if recovering
        else "worsening_mode"
        if event_type == "ma_worsening"
        else "break_mode"
    )
    confirmation = (
        "Der Schlusskurs bestätigt das Signal"
        if rule["confirmation"] == "close"
        else f"Das Signal wurde über {rule['confirmation_minutes']} Minuten bestätigt"
    )
    detail = (
        f"{confirmation}. Der Kurs liegt {_german_number(abs(distance_pct))} Prozent "
        f"{'über' if recovering else 'unter'} der Linie bei {_german_number(value.get('value'))} {trend.get('currency') or 'USD'}."
    )
    if distance_atr is not None:
        detail += f" Das entspricht {_german_number(distance_atr)} ATR."
    return {
        "category": "ma",
        "event_type": event_type,
        "ma_key": key,
        "tone": "good" if recovering else "warning",
        "label": f"{label} {suffix}",
        "detail": detail,
        "mode": rule[mode_key],
        "priority": rule["priority"],
        "session": rule["session"],
        "max_per_day": rule["max_per_day"],
        "confirmation": rule["confirmation"],
        "observation": observation,
    }


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
    signal_states: dict[str, Any] = {}
    raw_states = (
        raw.get("chart_signal_states") if isinstance(raw.get("chart_signal_states"), dict) else {}
    )
    for label, item in raw_states.items():
        if not isinstance(item, dict):
            continue
        signal_states[str(label)] = {
            "active": bool(item.get("active")),
            "available": bool(item.get("available")),
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
        "signal_states": signal_states,
    }


def _assessment_events(
    previous: dict[str, Any],
    current: dict[str, Any],
    *,
    include_score: bool = True,
) -> list[dict[str, str]]:
    events: list[dict[str, str]] = []
    previous_checks = previous.get("checks") if isinstance(previous.get("checks"), dict) else {}
    current_checks = current.get("checks") if isinstance(current.get("checks"), dict) else {}
    for label, check in current_checks.items():
        if not isinstance(check, dict) or str(label).startswith("Kurs über "):
            continue
        old = previous_checks.get(label) if isinstance(previous_checks.get(label), dict) else None
        if old is None:
            continue
        old_detail = str(old.get("detail") or "")
        current_detail = str(check.get("detail") or "")
        old_available = _assessment_detail_available(old_detail)
        current_available = _assessment_detail_available(current_detail)
        if (
            bool(old.get("passed")) == bool(check.get("passed"))
            and old_available == current_available
        ):
            continue
        if not current_available:
            if not old_available:
                continue
            events.append(
                {
                    "tone": "neutral",
                    "label": f"Kriterium derzeit nicht bewertbar: {label}",
                    "detail": _transition_detail(old_detail, current_detail),
                }
            )
            continue
        events.append(
            {
                "tone": "good" if bool(check.get("passed")) else "warning",
                "label": (
                    f"Kriterium jetzt bewertbar: {label}"
                    if not old_available
                    else f"Kriterium wieder erfüllt: {label}"
                    if bool(check.get("passed"))
                    else f"Neues Warnzeichen: {label}"
                ),
                "detail": _transition_detail(old_detail, current_detail),
            }
        )

    previous_signals = previous.get("signals") if isinstance(previous.get("signals"), dict) else {}
    current_signals = current.get("signals") if isinstance(current.get("signals"), dict) else {}
    previous_signal_states = (
        previous.get("signal_states") if isinstance(previous.get("signal_states"), dict) else {}
    )
    current_signal_states = (
        current.get("signal_states") if isinstance(current.get("signal_states"), dict) else {}
    )
    for key, signal in current_signals.items():
        if (
            not isinstance(signal, dict)
            or signal.get("category") != "negative"
            or key in previous_signals
        ):
            continue
        label = str(signal.get("label") or "")
        previous_state = (
            previous_signal_states.get(label)
            if isinstance(previous_signal_states.get(label), dict)
            else {}
        )
        current_state = (
            current_signal_states.get(label)
            if isinstance(current_signal_states.get(label), dict)
            else {}
        )
        previous_detail = str(previous_state.get("detail") or "")
        current_detail = str(current_state.get("detail") or signal.get("detail") or "")
        events.append(
            {
                "tone": "warning",
                "label": f"Neues Warnzeichen: {label}",
                "detail": (
                    _transition_detail(previous_detail, current_detail)
                    if previous_detail
                    else f"Aktuell: {current_detail}"
                ),
            }
        )
    for key, signal in previous_signals.items():
        if (
            not isinstance(signal, dict)
            or signal.get("category") != "negative"
            or key in current_signals
        ):
            continue
        label = str(signal.get("label") or "")
        current_state = (
            current_signal_states.get(label)
            if isinstance(current_signal_states.get(label), dict)
            else {}
        )
        previous_state = (
            previous_signal_states.get(label)
            if isinstance(previous_signal_states.get(label), dict)
            else {}
        )
        previous_detail = str(previous_state.get("detail") or signal.get("detail") or "")
        current_detail = str(current_state.get("detail") or "")
        if not current_state or not bool(current_state.get("available")):
            events.append(
                {
                    "tone": "neutral",
                    "label": f"Warnzeichen derzeit nicht bewertbar: {label}",
                    "detail": _transition_detail(
                        previous_detail, current_detail or "Aktuelle Daten fehlen."
                    ),
                }
            )
            continue
        if current_state and bool(current_state.get("active")):
            continue
        events.append(
            {
                "tone": "good",
                "label": f"Warnzeichen beendet: {label}",
                "detail": _transition_detail(
                    previous_detail,
                    current_detail or "Auslöseschwelle aktuell nicht mehr erfüllt.",
                ),
            }
        )

    old_score = int(_float_or_none(previous.get("overall_score")) or 0)
    new_score = int(_float_or_none(current.get("overall_score")) or 0)
    if include_score and old_score != new_score:
        events.append(
            {
                "tone": "warning" if new_score < old_score else "good",
                "event_type": "score",
                "label": f"Gesamtscore von {old_score} auf {new_score} {'gefallen' if new_score < old_score else 'gestiegen'}",
                "detail": f"Der Score hat sich um {abs(new_score - old_score)} Punkte verändert.",
            }
        )
    old_verdict = str(previous.get("verdict_label") or "")
    new_verdict = str(current.get("verdict_label") or "")
    if old_verdict and new_verdict and old_verdict != new_verdict:
        tone = _verdict_change_tone(previous, current)
        events.append(
            {
                "tone": tone,
                "event_type": "verdict",
                "label": f"Bewertung von „{old_verdict}“ auf „{new_verdict}“ geändert",
                "detail": "Die Gesamtbewertung hat sich verbessert."
                if tone == "good"
                else "Die Gesamtbewertung hat sich verschlechtert."
                if tone == "warning"
                else "Die Gesamtbewertung hat sich verändert; daraus ergibt sich keine eindeutige Richtung.",
            }
        )
    return events


def _verdict_change_tone(previous: dict[str, Any], current: dict[str, Any]) -> str:
    # Compare the transition rather than labelling every still-imperfect result
    # a new warning. In particular, leaving the 200-day blocker is an improvement.
    ranks = {
        "Mindestpreis nicht erreicht": 0,
        "Volumen nicht erreicht": 0,
        "Unter 200 Tage": 0,
        "Zu schwach": 1,
        "Überdehnt": 2,
        "Beobachten": 2,
        "Attraktiv": 3,
        "Stark": 3,
    }
    old_rank = ranks.get(str(previous.get("verdict_label") or ""))
    new_rank = ranks.get(str(current.get("verdict_label") or ""))
    if old_rank is None or new_rank is None:
        tones = {"bad": 0, "warning": 1, "neutral": 1, "good": 2}
        old_rank = tones.get(str(previous.get("verdict_tone") or ""), 1)
        new_rank = tones.get(str(current.get("verdict_tone") or ""), 1)
    return "good" if new_rank > old_rank else "warning" if new_rank < old_rank else "neutral"


def _transition_detail(previous: str, current: str) -> str:
    old = previous.strip()
    new = current.strip()
    if old and new and old != new:
        return f"Vorher: {old} · Aktuell: {new}"
    if new:
        return f"Aktuell: {new}"
    if old:
        return f"Vorher: {old} · Aktuelle Auslöseschwelle nicht mehr erfüllt."
    return "Aktuelle Auslöseschwelle nicht mehr erfüllt."


def _assessment_detail_available(detail: str) -> bool:
    clean = detail.strip().lower()
    if not clean or clean == "n/a":
        return False
    unavailable_markers = (
        "nicht verfügbar",
        "nicht auswertbar",
        "noch kein",
        "keine eps-",
        "keine umsatz-",
        "keine roe-",
        "keine gespeicherten",
    )
    if any(marker in clean for marker in unavailable_markers):
        return False
    return not any(f"nur {count}/3" in clean for count in range(3))


def _notification_event_label(label: str) -> str:
    clean = label.strip()
    prefixes = (
        "Neues Warnzeichen: ",
        "Warnzeichen beendet: ",
        "Warnzeichen derzeit nicht bewertbar: ",
        "Kriterium wieder erfüllt: ",
        "Kriterium jetzt bewertbar: ",
        "Kriterium derzeit nicht bewertbar: ",
    )
    for prefix in prefixes:
        if clean.startswith(prefix):
            return clean.removeprefix(prefix)
    return clean


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
    rule = _preferences(monitor_settings)["atr"]
    threshold = (
        _float_or_none(monitor.get("threshold_atr"))
        or _float_or_none(monitor_settings.get("position_monitor_threshold_atr"))
        or 1.5
    )
    distance = _float_or_none(monitor.get("distance_atr"))
    quote_at = _fresh_quote_at(monitor, now)
    previous = ticker_state.get(ticker) if isinstance(ticker_state.get(ticker), dict) else {}
    update = {
        "cooldown_trade_day": trade_day,
        "cooldown_reset_at": reset_at.isoformat(),
        "alert_allowed": False,
        "alert_reason": "no_fresh_quote",
    }
    decision = {
        "allowed": False,
        "monitor_update": update,
        "state_update": None,
        "alert": None,
        "suppression": None,
    }
    if (
        distance is None
        or quote_at is None
        or (_float_or_none(monitor.get("current_price")) or 0) <= 0
    ):
        # A missing observation is never evidence of a recovery.
        return decision
    last_observation = _parse_datetime(previous.get("last_observation_at"))
    if last_observation is not None and quote_at <= last_observation:
        update["alert_reason"] = "quote_already_observed"
        return decision
    current = copy.deepcopy(previous)
    current.update(
        trade_day=trade_day,
        threshold_atr=threshold,
        reference=str(monitor.get("reference") or ""),
        reference_price=_float_or_none(monitor.get("reference_price")),
        current_price=_float_or_none(monitor.get("current_price")),
    )
    last_alert_at = _parse_datetime(previous.get("last_alert_at"))
    crossed = distance >= threshold
    active = bool(previous.get("threshold_crossed", last_alert_at is not None))
    # Recovery must be separated from the trigger threshold. This also guards
    # configurations where a user accidentally puts recovery above the trigger.
    recovery_level = min(rule["recovery_atr"], max(0.0, threshold - 0.05))
    if distance <= recovery_level:
        if active and _confirm_observation(
            current,
            prefix="recovery",
            target="recovered",
            observed_at=quote_at,
            minutes=rule["recovery_minutes"],
        ):
            current.update(
                threshold_crossed=False, escalated_2x=False, recovered_at=quote_at.isoformat()
            )
            _clear_confirmation(current, "recovery")
        update["alert_reason"] = (
            "recovery_pending" if current.get("threshold_crossed") else "threshold_not_crossed"
        )
    else:
        _clear_confirmation(current, "recovery")
        update["alert_reason"] = "threshold_not_crossed" if not crossed else "repeat_suppressed"
    current["last_observation_at"] = quote_at.isoformat()
    decision["state_update"] = current
    if not crossed:
        return decision

    rearm_requests = monitor_settings.get("atr_rearm_requests") or {}
    rearm_at = (
        _parse_datetime(rearm_requests.get(ticker)) if isinstance(rearm_requests, dict) else None
    )
    manually_rearmed = rearm_at is not None and (last_alert_at is None or rearm_at > last_alert_at)
    last_day = str(
        previous.get("last_alert_trade_day")
        or (_monitor_trade_day(last_alert_at) if last_alert_at is not None else "")
        or previous.get("trade_day")
        or ""
    )
    repeat = rule["repeat"]
    interval_due = last_alert_at is not None and now - last_alert_at >= timedelta(
        minutes=rule["repeat_minutes"]
    )
    recovered = _parse_datetime(previous.get("recovered_at"))
    after_recovery = (
        previous.get("threshold_crossed") is False
        and recovered is not None
        and (last_alert_at is None or recovered > last_alert_at)
    )
    escalation = (
        rule["escalation_enabled"]
        and distance >= max(threshold, rule["escalation_atr"])
        and not bool(previous.get("escalated_2x"))
    )
    allowed = (
        last_alert_at is None
        or manually_rearmed
        or escalation
        or (repeat == "daily" and last_day != trade_day)
        or (repeat == "interval" and interval_due)
        or (repeat == "recovery" and after_recovery)
    )
    reason = (
        "atr_escalation"
        if escalation
        else "manual_rearm"
        if manually_rearmed
        else "initial_breach"
        if last_alert_at is None
        else "confirmed_recovery"
        if after_recovery
        else "interval_repeat"
        if repeat == "interval"
        else "daily_repeat"
    )
    update.update(
        alert_allowed=allowed,
        alert_reason=reason if allowed else "repeat_suppressed",
        alert_escalation_2x=escalation,
    )
    if allowed:
        current.update(
            last_alert_at=now.isoformat(),
            last_alert_trade_day=trade_day,
            last_distance_atr=distance,
            threshold_crossed=True,
            escalated_2x=escalation or bool(current.get("escalated_2x")),
        )
        alert = {
            "kind": "atr",
            "ticker": ticker,
            "distance_atr": round(distance, 4),
            "threshold_atr": threshold,
            "reference": monitor.get("reference"),
            "reference_label": monitor.get("reference_label"),
            "current_price": monitor.get("current_price"),
            "reference_price": monitor.get("reference_price"),
            "atr_value": monitor.get("atr_value"),
            "trade_day": trade_day,
            "reason": reason,
            "category": "atr",
            "event_type": "atr_escalation" if escalation else "atr",
            "mode": rule["mode"],
            "priority": rule["priority"],
            "session": rule["session"],
            "quote_at": quote_at.isoformat(),
        }
        identity = json.dumps(
            [ticker, reason, quote_at.isoformat(), threshold, monitor.get("reference")]
        )
        alert["alert_id"] = "atr:" + hashlib.sha256(identity.encode()).hexdigest()[:28]
        decision.update(allowed=True, alert=alert)
    else:
        decision["suppression"] = {
            "ticker": ticker,
            "distance_atr": distance,
            "reason": "repeat_suppressed",
            "next_reset_at": reset_at.isoformat(),
        }
    return decision


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
