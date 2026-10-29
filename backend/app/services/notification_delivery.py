"""Persistent Pushover routing, batching and scheduled summaries.

Detection owns signal transitions; this module owns durable delivery acceptance.
A queued, muted or digested signal is accepted exactly once and does not need to
be rediscovered by the quote monitor. No provider call occurs before state can be
locked in the database.
"""

from __future__ import annotations

import copy
import hashlib
import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from time import monotonic
from zoneinfo import ZoneInfo

from sqlalchemy import select, text

from app.db.models import AppSetting
from app.db.session import SessionLocal

logger = logging.getLogger(__name__)
STATE_KEY = "notification_dispatch_state"
LOG_KEY = "pushover_delivery_log"
MAX_PENDING = 2000
MAX_LOG = 500
MAX_SEEN = 5000


def _mapping(value: Any) -> dict:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return dict(value) if isinstance(value, dict) else {}


def _preferences(settings: Any) -> dict:
    values = _mapping(settings)
    return _mapping(values.get("notification_preferences"))


def _stamp(value: Any) -> datetime | None:
    try:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return result.replace(tzinfo=UTC) if result.tzinfo is None else result
    except (TypeError, ValueError):
        return None


def _clock_inside(now: datetime, start: str, end: str) -> bool:
    current = now.strftime("%H:%M")
    return (
        False
        if start == end
        else start <= current < end
        if start < end
        else current >= start or current < end
    )


def _regular_session(ticker: str, now: datetime) -> bool:
    """Use the instrument exchange calendar, including holidays and early closes."""
    from app.services.market_calendar import _ticker_calendar
    import pandas as pd

    try:
        calendar = _ticker_calendar(ticker)
        for session in calendar.sessions_in_range(
            pd.Timestamp((now - timedelta(days=1)).date()),
            pd.Timestamp((now + timedelta(days=1)).date()),
        ):
            if (
                calendar.session_open(session).to_pydatetime()
                <= now
                < calendar.session_close(session).to_pydatetime()
            ):
                return True
    except Exception:
        logger.exception("Notification exchange calendar unavailable for %s", ticker)
    return False


def _is_escalation(alert: dict) -> bool:
    return str(alert.get("kind") or "atr") == "atr" and (
        alert.get("is_escalation") is True
        or str(alert.get("reason") or "") in {"escalation", "atr_escalation", "2x_atr_escalation"}
        or alert.get("event_type") == "atr_escalation"
        or alert.get("escalated") is True
    )


def _bypass(alert: dict, policy: dict) -> bool:
    return bool(
        (alert.get("kind") == "stop" and policy.get("stop_bypass", True))
        or (_is_escalation(alert) and policy.get("atr_escalation_bypass", True))
    )


def _held_reason(entry: dict, prefs: dict, now: datetime) -> str:
    alert = entry["alert"]
    quiet = prefs.get("quiet", {})
    local_now = now.astimezone(ZoneInfo(prefs.get("timezone", "Europe/Berlin")))
    if (
        quiet.get("enabled")
        and not _bypass(alert, quiet)
        and _clock_inside(local_now, quiet.get("start", "22:00"), quiet.get("end", "07:00"))
    ):
        return "Ruhezeit: für den nächsten erlaubten Versand vorgemerkt."
    session = entry.get("session", "all")
    if (
        session == "regular"
        and not _regular_session(entry.get("ticker", ""), now)
        and not _latest_confirmed_close(entry, now)
    ):
        return "Außerhalb der regulären Börsensitzung vorgemerkt."
    custom = prefs.get("custom_session", {})
    if session == "custom" and not _clock_inside(
        local_now, custom.get("start", "08:00"), custom.get("end", "22:00")
    ):
        return "Außerhalb des eigenen Versandfensters vorgemerkt."
    return ""


def _latest_confirmed_close(entry: dict, now: datetime) -> bool:
    """A closing confirmation necessarily becomes available after market close.

    Choosing regular trading refers to the confirmed regular-session close for
    these events. Quiet hours and custom delivery windows still apply normally.
    """
    if entry.get("category") != "ma":
        return False
    event = (entry.get("alert", {}).get("events") or [{}])[0]
    if event.get("confirmation") != "close":
        return False
    from app.services.market_calendar import completed_ticker_market_session
    try:
        completed = completed_ticker_market_session(entry.get("ticker", ""), now)
        return event.get("observation") == completed.date.isoformat()
    except (ValueError, KeyError, TypeError):
        return False


def _format_alert(alert: dict) -> tuple[str, str]:
    if alert.get("kind") == "workspace":
        return str(alert.get("title") or "Dashboard-Hinweis"), str(alert.get("message") or "")[
            :1000
        ]
    from app.workers.tasks.position_atr_monitor import (
        _format_monitor_alert_message,
        _monitor_alert_title,
    )

    return _monitor_alert_title(alert), _format_monitor_alert_message(alert)


def _entry(alert: dict, parent_id: str, *, prefs: dict, now: datetime) -> dict:
    kind = str(alert.get("kind") or "atr")
    event = (alert.get("events") or [{}])[0] if kind == "stock_signal" else {}
    category = (
        str(event.get("category") or ("ma" if event.get("ma_key") else "verdict"))
        if kind == "stock_signal"
        else kind
    )
    policy = prefs.get(category if category in {"stop", "atr"} else "assessment", {})
    if category == "ma":
        policy = prefs.get("ma", {}).get(event.get("ma_key"), {})
    mode = event.get("mode", "immediate")
    if category in {"stop", "atr"}:
        mode = policy.get("mode", mode)
    elif category == "ma":
        event_type = str(event.get("event_type") or "ma_break").removeprefix("ma_")
        mode = policy.get(f"{event_type}_mode", mode)
    elif category in {"score", "verdict"}:
        mode = policy.get(f"{category}_mode", mode)
    # The detector may explicitly mute a direction or classify secondary detail
    # for the digest even when the primary verdict is configured as immediate.
    if event.get("suppression_reason") or event.get("mode") == "off":
        mode = "off"
    elif event.get("event_type") == "assessment_detail" and mode != "off":
        mode = "digest"
    if category in {"score", "verdict"}:
        tone = str(event.get("tone") or "")
        if (tone == "good" and not policy.get("notify_improvements", True)) or (
            tone == "warning" and not policy.get("notify_deteriorations", True)
        ):
            mode = "off"
    identifier = str(event.get("event_id") or alert.get("event_id") or parent_id)
    fingerprint = hashlib.sha256(
        json.dumps(alert, sort_keys=True, default=str).encode()
    ).hexdigest()[:20]
    return {
        "id": identifier or f"signal:{fingerprint}",
        "parent_id": parent_id,
        "ticker": str(alert.get("ticker") or "").upper(),
        "category": category,
        "mode": mode,
        "priority": int(policy.get("priority", event.get("priority", 0))),
        "session": str(policy.get("session", event.get("session", "all"))),
        "limit_key": str(event.get("limit_key") or ""),
        "max_per_day": int(policy.get("max_per_day", event.get("max_per_day", 1000))),
        "at": now.isoformat(),
        "alert": json.loads(json.dumps(alert, default=str)),
    }


def _subject(entry: dict) -> str:
    event = (entry["alert"].get("events") or [{}])[0]
    if entry["category"] == "ma":
        return str(event.get("ma_key") or "ma")
    if event.get("event_type") == "assessment_detail":
        label = str(event.get("label") or "")
        subject = event.get("event_subject") or label.split(":", 1)[0]
        return f"assessment_detail:{subject}"
    return entry["category"]


def _expand_alerts(
    alerts: list[dict], prefs: dict, now: datetime
) -> tuple[list[dict], dict[str, set[str]]]:
    entries, parents = [], {}
    for alert in alerts:
        if not isinstance(alert, dict):
            continue
        parent_id = str(alert.get("alert_id") or "")
        if not parent_id:
            parent_id = hashlib.sha256(
                json.dumps(alert, sort_keys=True, default=str).encode()
            ).hexdigest()[:24]
        parts = alert.get("events") if alert.get("kind") == "stock_signal" else None
        if parts:
            for index, event in enumerate(parts):
                if not isinstance(event, dict):
                    continue
                child = {**alert, "events": [event]}
                entry = _entry(child, parent_id, prefs=prefs, now=now)
                if not event.get("event_id"):
                    entry["id"] = f"{parent_id}:{index}"
                entries.append(entry)
                parents.setdefault(parent_id, set()).add(entry["id"])
        else:
            entry = _entry(alert, parent_id, prefs=prefs, now=now)
            entries.append(entry)
            parents.setdefault(parent_id, set()).add(entry["id"])
    return entries, parents


def _log(
    entry: dict,
    *,
    status: str,
    detail: str,
    now: datetime,
    title: str = "",
    message: str = "",
    priority: int | None = None,
) -> dict:
    if not title and entry.get("alert") and entry.get("category") != "summary":
        title, message = _format_alert(entry["alert"])
    return {
        "timestamp": now.isoformat(),
        "ticker": entry.get("ticker", ""),
        "status": status,
        "detail": detail,
        "kind": entry.get("category", "system"),
        "alert_id": entry.get("parent_id") or entry.get("id", ""),
        "title": title[:200],
        "message": message[:1000],
        "priority": int(entry.get("priority", 0) if priority is None else priority),
    }


def _empty_result() -> dict:
    return {
        "ok": True,
        "sent": 0,
        "failed": 0,
        "skipped": 0,
        "queued": 0,
        "sent_tickers": [],
        "sent_alert_ids": [],
        "accepted_tickers": [],
        "accepted_alert_ids": [],
        "errors": [],
    }


def _render_group(entries: list[dict]) -> tuple[str, str, int]:
    # A combined message must keep a reached stop or escalation visible first.
    entries = sorted(entries, key=lambda entry: (
        0 if entry["alert"].get("kind") == "stop" else
        1 if _is_escalation(entry["alert"]) else
        2 if entry["alert"].get("kind") == "atr" else 3
    ))
    formatted = [_format_alert(entry["alert"]) for entry in entries]
    ticker = entries[0].get("ticker") or "Depot"
    title = formatted[0][0] if len(entries) == 1 else f"{ticker}: {len(entries)} neue Hinweise"
    if len(entries) > 1 and (entries[0]["alert"].get("kind") == "stop" or _is_escalation(entries[0]["alert"])):
        count = len(entries) - 1
        title = f"{formatted[0][0]} · {count} {'weiterer Hinweis' if count == 1 else 'weitere Hinweise'}"
    message = "\n\n".join(message for _, message in formatted)
    if len(message) > 1000:
        message = message[:930].rsplit("\n", 1)[0] + "\nWeitere Einzelheiten stehen im Dashboard."
    return title, message, max(entry.get("priority", 0) for entry in entries)


def _record_observations(state: dict, observations, now: datetime) -> None:
    """Keep evidence of the latest valid quote, independently of alert routing."""
    if observations is None:
        return
    latest = dict(state.get("latest_observations", {}))
    for item in observations:
        if not isinstance(item, dict) or not item.get("ticker"):
            continue
        monitor = _mapping(item.get("monitor"))
        trend = _mapping(item.get("trend_monitor"))
        stop = _mapping(item.get("stop_observation"))
        quote_at = (
            monitor.get("quote_at")
            or monitor.get("live_quote_at")
            or stop.get("quote_at")
            or trend.get("quote_at")
        )
        quote = _stamp(quote_at)
        if quote is None or not timedelta(0) <= now - quote <= timedelta(minutes=20):
            continue
        record = {
            "observed_at": now.isoformat(),
            "quote_at": quote.isoformat(),
            "monitor": monitor,
            "trend_monitor": trend,
            "stop_observation": stop,
        }
        assessment = item.get("notification_assessment") or item.get("assessment")
        if isinstance(assessment, dict):
            record["assessment"] = assessment
        elif latest.get(str(item["ticker"]).upper(), {}).get("assessment"):
            record["assessment"] = latest[str(item["ticker"]).upper()]["assessment"]
        latest[str(item["ticker"]).upper()] = json.loads(json.dumps(record, default=str))
    state["latest_observations"] = dict(
        sorted(latest.items(), key=lambda pair: pair[1].get("observed_at", ""))[-500:]
    )


def _monitor_day(now: datetime) -> str:
    day = (now.astimezone(ZoneInfo("Europe/Berlin")) - timedelta(hours=7, minutes=30)).date()
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return day.isoformat()


def _dispatch_state(
    state: dict,
    alerts: list[dict],
    *,
    prefs: dict,
    now: datetime,
    sender,
    flush: bool = False,
    observations=None,
) -> tuple[dict, dict, list[dict]]:
    """Plan and deliver with an exclusively locked, writable state dictionary."""
    state = copy.deepcopy(state)
    result, logs = _empty_result(), []
    _record_observations(state, observations, now)
    local_now = now.astimezone(ZoneInfo(prefs.get("timezone", "Europe/Berlin")))
    today = local_now.date().isoformat()
    monitor_day = _monitor_day(now)
    if state.get("day") != monitor_day:
        state.update(day=monitor_day, counts={})
    if state.get("summary_day") != today:
        state.update(summary_day=today, sent_today=[])
    pending = list(state.get("pending", []))
    seen = list(state.get("seen", []))
    seen_ids = {item["id"] for item in seen}
    pending_ids = {item["id"] for item in pending}
    event_counts = state.setdefault("event_counts", {})
    if state.get("event_count_day") != monitor_day:
        event_counts.clear()
        state["event_count_day"] = monitor_day
    new_entries, parents = _expand_alerts(alerts, prefs, now)
    accepted = set(seen_ids) | pending_ids
    newly_added = set()
    for entry in new_entries:
        if entry["id"] in accepted:
            continue
        if entry["mode"] == "off":
            accepted.add(entry["id"])
            seen.append({"id": entry["id"], "at": now.isoformat()})
            logs.append(
                _log(
                    entry,
                    status="suppressed",
                    detail="Für diese Meldungsart ist Pushover ausgeschaltet.",
                    now=now,
                )
            )
            result["skipped"] += 1
        elif len(pending) >= MAX_PENDING:
            result["failed"] += 1
            result["errors"].append(
                "Versandwarteschlange ist voll; Signal bleibt zur erneuten Prüfung offen."
            )
        else:
            # Keep the latest unsent transition for one MA/assessment subject.
            # Otherwise an old break could arrive after a newer recovery.
            if entry["category"] in {"ma", "score", "verdict"}:
                subject = _subject(entry)
                superseded = [
                    old
                    for old in pending
                    if old["ticker"] == entry["ticker"]
                    and old["category"] == entry["category"]
                    and _subject(old) == subject
                ]
                superseded_ids = {old["id"] for old in superseded}
                for old in superseded:
                    seen.append({"id": old["id"], "at": now.isoformat()})
                    logs.append(
                        _log(
                            old,
                            status="suppressed",
                            detail="Durch die neuere Entwicklung derselben Meldungsart ersetzt.",
                            now=now,
                        )
                    )
                pending = [old for old in pending if old["id"] not in superseded_ids]
            pending.append(entry)
            newly_added.add(entry["id"])
            accepted.add(entry["id"])
            if entry["mode"] == "digest":
                logs.append(
                    _log(
                        entry, status="digest", detail="Für die Tagesübersicht vorgemerkt.", now=now
                    )
                )
                result["queued"] += 1
    grouping = prefs.get("grouping", {})
    counts = state.get("counts", {})
    last_sent = state.setdefault("last_sent", {})
    available: dict[str, list[dict]] = {}
    summary_enabled = prefs.get("summary", {}).get("enabled", True)
    for entry in pending:
        # Preference changes apply to already queued alerts as well.
        refreshed = _entry(entry["alert"], entry.get("parent_id", ""), prefs=prefs, now=now)
        for key in ("mode", "priority", "session", "limit_key", "max_per_day"):
            entry[key] = refreshed[key]
        if entry.get("digest_reason") and entry["mode"] != "off":
            entry["mode"] = "digest"
        if entry["mode"] != "immediate":
            continue
        retry = _stamp(entry.get("retry_at"))
        if retry is not None and now < retry:
            continue
        reason = _held_reason(entry, prefs, now)
        if (
            not reason
            and entry.get("limit_key")
            and entry["max_per_day"] > 0
            and event_counts.get(entry["limit_key"], 0) >= entry["max_per_day"]
        ):
            reason = "Tageslimit dieser Meldungsart erreicht; für die Tagesübersicht vorgemerkt."
            entry.update(cap_held=monitor_day, digest_reason="daily_limit", mode="digest")
        ticker = entry.get("ticker") or "System"
        bypass = _bypass(entry["alert"], grouping)
        if not reason and grouping.get("enabled", True) and not bypass:
            last = _stamp(last_sent.get(ticker))
            if last and now < last + timedelta(minutes=int(grouping.get("window_minutes", 30))):
                reason = "Mit weiteren Hinweisen innerhalb des Bündelungsfensters vorgemerkt."
        if (
            not reason
            and not bypass
            and int(grouping.get("max_immediate_per_ticker_day", 3)) > 0
            and counts.get(ticker, 0) >= int(grouping.get("max_immediate_per_ticker_day", 3))
        ):
            reason = "Tageslimit erreicht; für die Tagesübersicht vorgemerkt."
            entry.update(cap_held=monitor_day, digest_reason="daily_limit", mode="digest")
        if reason:
            if reason.startswith("Außerhalb") and entry["category"] in {"ma", "score", "verdict"}:
                entry.update(mode="digest", digest_reason="session")
                reason = "Außerhalb des Versandfensters erkannt; nur in der Tagesübersicht."
            if entry["id"] in newly_added:
                logs.append(_log(entry, status="queued", detail=reason, now=now))
                result["queued"] += 1
            continue
        key = ticker if grouping.get("enabled", True) else entry["id"]
        available.setdefault(key, []).append(entry)
    sent_entry_ids = set()
    started = monotonic()
    for entries in available.values():
        if monotonic() - started >= 8:
            result["queued"] += len(entries)
            for entry in entries:
                if entry["id"] in newly_added:
                    logs.append(
                        _log(
                            entry,
                            status="queued",
                            detail="Für den nächsten Versandlauf vorgemerkt.",
                            now=now,
                        )
                    )
            continue
        ticker = entries[0].get("ticker") or "System"
        maximum = int(grouping.get("max_immediate_per_ticker_day", 3))
        if (
            maximum > 0
            and counts.get(ticker, 0) >= maximum
            and not any(_bypass(entry["alert"], grouping) for entry in entries)
        ):
            for entry in entries:
                entry.update(cap_held=monitor_day, digest_reason="daily_limit", mode="digest")
                logs.append(
                    _log(
                        entry,
                        status="queued",
                        detail="Tageslimit erreicht; für die Tagesübersicht vorgemerkt.",
                        now=now,
                    )
                )
            continue
        entries_to_send = [
            entry
            for entry in entries
            if not (
                entry.get("limit_key")
                and entry["max_per_day"] > 0
                and event_counts.get(entry["limit_key"], 0) >= entry["max_per_day"]
            )
        ]
        for entry in entries:
            if entry not in entries_to_send:
                entry.update(cap_held=monitor_day, digest_reason="daily_limit", mode="digest")
                logs.append(
                    _log(
                        entry,
                        status="queued",
                        detail="Tageslimit dieser Meldungsart erreicht; für die Tagesübersicht vorgemerkt.",
                        now=now,
                    )
                )
        entries = entries_to_send
        if not entries:
            continue
        title, message, priority = _render_group(entries)
        try:
            response = sender(title=title, message=message, priority=priority)
            if int(response.get("status", 0)) != 1:
                raise RuntimeError("Pushover hat den Versand nicht bestätigt.")
        except Exception as exc:
            result["failed"] += 1
            result["errors"].append(f"{type(exc).__name__}: {exc}")
            for entry in entries:
                # Bound failed retries to avoid a provider outage hammering the API.
                entry["retry_at"] = (now + timedelta(minutes=5)).isoformat()
                logs.append(
                    _log(
                        entry,
                        status="failed",
                        detail=f"Versand fehlgeschlagen: {type(exc).__name__}",
                        now=now,
                        title=title,
                        message=message,
                        priority=priority,
                    )
                )
            continue
        result["sent"] += 1
        ticker = entries[0].get("ticker") or "System"
        counts[ticker] = counts.get(ticker, 0) + 1
        last_sent[ticker] = now.isoformat()
        for entry in entries:
            sent_entry_ids.add(entry["id"])
            if entry.get("limit_key"):
                event_counts[entry["limit_key"]] = event_counts.get(entry["limit_key"], 0) + 1
            seen.append({"id": entry["id"], "at": now.isoformat()})
            state["sent_today"].append(entry)
            result["sent_alert_ids"].append(entry["parent_id"])
            result["sent_tickers"].append(entry["ticker"])
            logs.append(
                _log(
                    entry,
                    status="sent",
                    detail=(
                        f"Gemeinsam mit {len(entries)} Hinweisen als eine Nachricht zugestellt."
                        if len(entries) > 1
                        else "Pushover hat den Versand bestätigt."
                    ),
                    now=now,
                    title=title,
                    message=message,
                    priority=priority,
                )
            )
    off_ids = {entry["id"] for entry in pending if entry["mode"] == "off"}
    for entry in pending:
        if entry["id"] in off_ids:
            seen.append({"id": entry["id"], "at": now.isoformat()})
            logs.append(
                _log(
                    entry,
                    status="suppressed",
                    detail="Wartende Meldung nach Änderung der Einstellung ausgeschaltet.",
                    now=now,
                )
            )
    pending = [entry for entry in pending if entry["id"] not in sent_entry_ids | off_ids]
    summary = prefs.get("summary", {})
    # A disabled summary is a log-only choice, not an unbounded delivery queue.
    summary_categories = set(summary.get("categories", ["ma", "score", "verdict", "stop", "atr"]))
    log_only = {
        entry["id"] for entry in pending
        if entry["mode"] == "digest"
        and (not summary_enabled or entry["category"] not in summary_categories)
    }
    for entry in pending:
        if entry["id"] in log_only:
            seen.append({"id": entry["id"], "at": now.isoformat()})
            logs.append(_log(entry, status="suppressed", now=now,
                             detail="Tagesübersicht oder Kategorie ausgeschaltet; der Hinweis bleibt nur im Protokoll."))
    pending = [entry for entry in pending if entry["id"] not in log_only]
    scheduled = summary.get("time", "22:45")
    waiting = state.get("summary_waiting")
    if (
        flush
        and summary_enabled
        and not waiting
        and local_now.strftime("%H:%M") >= scheduled
        and state.get("summary_slot") != f"{today}:{scheduled}"
    ):
        hour, minute = map(int, scheduled.split(":"))
        cutoff = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        waiting = {
            "slot": f"{today}:{scheduled}",
            "date": today,
            "cutoff": cutoff.isoformat(),
            "sent_entries": copy.deepcopy(state["sent_today"]),
            "snapshots": copy.deepcopy(state.get("latest_observations", {})),
        }
        state["summary_waiting"] = waiting
    summary_retry = _stamp(state.get("summary_retry_at"))
    summary_due = (
        flush
        and summary_enabled
        and bool(waiting)
        and (summary_retry is None or now >= summary_retry)
    )
    if summary_due:
        due_date = waiting["date"]
        due_slot = waiting["slot"]
        cutoff = _stamp(waiting["cutoff"])
        summary_categories = set(
            summary.get("categories", ["ma", "score", "verdict", "stop", "atr"])
        )
        digest_entries = [
            entry
            for entry in pending
            if entry["category"] in summary_categories
            and (_stamp(entry.get("at")) or now) <= cutoff
            and entry["mode"] != "off"
            and (
                entry["mode"] == "digest"
                or bool(entry.get("cap_held"))
                or entry.get("digest_reason")
            )
        ]
        if summary.get("include_sent"):
            digest_entries += [
                entry
                for entry in waiting.get("sent_entries", [])
                if entry["category"] in summary_categories
                and (_stamp(entry.get("at")) or now) <= cutoff
            ]
        if not summary.get("only_changes", True):
            from app.services.notification_snapshot import snapshot_summary_entries

            existing_entries = list(digest_entries)
            if not summary.get("include_sent"):
                existing_entries.extend(waiting.get("sent_entries", []))
            digest_entries.extend(
                snapshot_summary_entries(
                    {
                        ticker: snapshot
                        for ticker, snapshot in waiting.get("snapshots", {}).items()
                        if (_stamp(snapshot.get("observed_at")) or now) <= cutoff
                    },
                    prefs,
                    now,
                    existing_entries=existing_entries,
                )
            )
        # Daily summaries respect quiet hours, but are not tied to quote sessions.
        summary_entry = {
            "ticker": "",
            "category": "summary",
            "id": f"summary:{due_slot}",
            "parent_id": f"summary:{due_slot}",
            "alert": {"kind": "summary"},
            "session": "all",
            "priority": int(summary.get("priority", 0)),
        }
        if not _held_reason(summary_entry, prefs, now):
            if digest_entries or not summary.get("only_changes", True):
                title, message = _render_summary(digest_entries, summary, due_date)
                priority = int(summary.get("priority", 0))
                try:
                    response = sender(title=title, message=message, priority=priority)
                    if int(response.get("status", 0)) != 1:
                        raise RuntimeError("Pushover hat die Tagesübersicht nicht bestätigt.")
                except Exception as exc:
                    result["failed"] += 1
                    state["summary_retry_at"] = (now + timedelta(minutes=5)).isoformat()
                    result["errors"].append(f"{type(exc).__name__}: {exc}")
                    logs.append(
                        _log(
                            summary_entry,
                            status="failed",
                            detail="Tagesübersicht wird beim nächsten Lauf erneut versucht.",
                            now=now,
                            title=title,
                            message=message,
                            priority=priority,
                        )
                    )
                else:
                    result["sent"] += 1
                    ids = {entry["id"] for entry in digest_entries}
                    for entry in pending:
                        if entry["id"] in ids:
                            seen.append({"id": entry["id"], "at": now.isoformat()})
                            result["sent_alert_ids"].append(entry["parent_id"])
                            result["sent_tickers"].append(entry["ticker"])
                    pending = [entry for entry in pending if entry["id"] not in ids]
                    state["summary_slot"] = due_slot
                    state.pop("summary_waiting", None)
                    state.pop("summary_retry_at", None)
                    logs.append(
                        _log(
                            summary_entry,
                            status="sent",
                            detail="Tagesübersicht zugestellt.",
                            now=now,
                            title=title,
                            message=message,
                            priority=priority,
                        )
                    )
            else:
                state["summary_slot"] = due_slot
                state.pop("summary_waiting", None)
                state.pop("summary_retry_at", None)
                logs.append(
                    _log(
                        summary_entry,
                        status="skipped",
                        detail="Keine neuen Änderungen für die Tagesübersicht.",
                        now=now,
                    )
                )
    state["event_counts"] = event_counts
    # Accepted means ownership moved durably to this dispatcher, including retries.
    for parent_id, children in parents.items():
        if children <= accepted:
            result["accepted_alert_ids"].append(parent_id)
    result["accepted_tickers"] = [
        entry["ticker"]
        for entry in new_entries
        if entry["parent_id"] in result["accepted_alert_ids"]
    ]
    for key in ("accepted_alert_ids", "accepted_tickers", "sent_alert_ids", "sent_tickers"):
        result[key] = list(dict.fromkeys(result[key]))
    state.update(
        pending=pending,
        seen=seen[-MAX_SEEN:],
        counts=counts,
        sent_today=state["sent_today"][-MAX_PENDING:],
    )
    result["ok"] = not result["failed"]
    return state, result, logs


def _render_summary(entries: list[dict], summary: dict, today: str) -> tuple[str, str]:
    by_ticker: dict[str, list[dict]] = {}
    for entry in entries:
        by_ticker.setdefault(entry.get("ticker") or "Depot", []).append(entry)
    title = "Deine Depotübersicht"
    day = datetime.fromisoformat(today).strftime("%d.%m.%Y")
    lines = [
        f"Deine Übersicht vom {day}",
        "Seit der letzten Tagesübersicht:"
        if summary.get("only_changes", True)
        else "Neue und weiterhin aktive Hinweise:",
    ]
    maximum = int(summary.get("max_tickers", 5))
    for ticker, group in list(by_ticker.items())[:maximum]:
        lines.append(f"\n{ticker}")
        for entry in group:
            event = (entry["alert"].get("events") or [{}])[0]
            if event.get("label"):
                from app.workers.tasks.position_atr_monitor import _prose

                lines.append(f"• {_prose(event['label'])}")
            else:
                lines.append("• " + _format_alert(entry["alert"])[0])
    omitted = max(0, len(by_ticker) - maximum)
    if omitted:
        lines.append(
            "\nEine weitere Aktie findest du im Dashboard."
            if omitted == 1
            else f"\nWeitere {omitted} Aktien findest du im Dashboard."
        )
    if not entries:
        lines.append("Heute gibt es keine neuen relevanten Änderungen.")
    message = "\n".join(lines)
    if len(message) > 1000:
        message = message[:930].rsplit("\n", 1)[0] + "\nWeitere Einzelheiten stehen im Dashboard."
    return title, message


def _deliver(
    alerts: list[dict], *, app_settings, now=None, send_message=None, flush=False, observations=None
) -> dict:
    from app.core_config import get_settings
    from app.services.settings import get_runtime_config_bool, get_runtime_config_value
    from app.workers.tasks.pushover_test import _send_pushover_message

    now = now or datetime.now(UTC)
    now = now.replace(tzinfo=UTC) if now.tzinfo is None else now
    values = _mapping(app_settings)
    result = _empty_result()
    if not values.get("pushover_enabled"):
        result.update(skipped=len(alerts), reason="Pushover ist ausgeschaltet.")
        return result
    runtime = get_settings()
    user = get_runtime_config_value("PUSHOVER_USER_KEY") or runtime.pushover_user_key
    token = get_runtime_config_value("PUSHOVER_APP_TOKEN") or runtime.pushover_app_token
    dry_run = get_runtime_config_bool("PUSHOVER_DRY_RUN", runtime.pushover_dry_run)
    if dry_run or not user or not token:
        result.update(skipped=len(alerts), reason="Testmodus aktiv oder Pushover-Zugang fehlt.")
        return result
    callback = send_message or _send_pushover_message

    def sender(**kwargs):
        return callback(user_key=user, app_token=token, **kwargs)

    try:
        with SessionLocal() as db:
            db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": STATE_KEY})
            row = db.scalar(select(AppSetting).where(AppSetting.key == STATE_KEY).with_for_update())
            state, result, logs = _dispatch_state(
                row.value_json if row else {},
                alerts,
                prefs=_preferences(app_settings),
                now=now,
                sender=sender,
                flush=flush,
                observations=observations,
            )
            if row is None:
                row = AppSetting(
                    key=STATE_KEY,
                    description="Persistent notification queues, limits and acceptance state",
                )
                db.add(row)
            row.value_json = state
            if logs:
                log_row = db.scalar(
                    select(AppSetting).where(AppSetting.key == LOG_KEY).with_for_update()
                )
                if log_row is None:
                    log_row = AppSetting(
                        key=LOG_KEY,
                        description="Bounded notification delivery and suppression history",
                    )
                    db.add(log_row)
                previous = (log_row.value_json or {}).get("entries", [])
                log_row.value_json = {"entries": [*reversed(logs), *previous][:MAX_LOG]}
            db.commit()
        return result
    except Exception as exc:
        logger.exception("Notification dispatch state unavailable")
        result = _empty_result()
        result.update(
            ok=False,
            failed=len(alerts),
            reason="Versandzustand konnte nicht sicher gespeichert werden.",
            errors=[f"{type(exc).__name__}: {exc}"],
        )
        return result


def deliver_notifications(
    alerts, *, app_settings, now=None, send_message=None, observations=None
) -> dict:
    return _deliver(
        list(alerts),
        app_settings=app_settings,
        now=now,
        send_message=send_message,
        observations=observations,
    )


def flush_notifications(*, app_settings, now=None, send_message=None) -> dict:
    return _deliver([], app_settings=app_settings, now=now, send_message=send_message, flush=True)
