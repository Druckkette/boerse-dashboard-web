"""Persistent stop crossings with configurable rearming and sustained recovery."""

from datetime import UTC, datetime, timedelta
import copy
import logging
import math

from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from app.db.models import AppSetting
from app.db.session import SessionLocal

logger = logging.getLogger(__name__)
RECOVERY_FACTOR = 1.005
RETRY_DELAY = timedelta(minutes=15)


def _preferences(value):
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    if not isinstance(value, dict):
        return None
    return value.get("stop", value)


def _datetime(value):
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed
    except (TypeError, ValueError):
        return None


def stop_transition(
    previous: dict, item: dict, now: datetime, *, preferences=None
) -> tuple[dict, dict | None]:
    price, stop = item.get("price"), item.get("stop")
    if not all(isinstance(v, (int, float)) and math.isfinite(v) and v > 0 for v in (price, stop)):
        return previous, None
    quote = _datetime(item.get("quote_at"))
    if quote is None or not timedelta(0) <= now - quote <= timedelta(minutes=20):
        # A stale or missing quote cannot count as sustained recovery.
        state = copy.deepcopy(previous)
        state.pop("recovery_since", None)
        return state, None
    state = copy.deepcopy(previous)
    policy = _preferences(preferences)
    if state.get("stop") != stop:
        state = {
            "stop": stop,
            "triggered": False,
            "generation": int(state.get("generation", 0)) + 1,
        }
    state["ticker"] = item["ticker"]
    state["identity"] = item["identity"]
    last_seen = _datetime(state.get("last_seen_at"))
    state["last_seen_at"] = now.isoformat()
    repeat = policy.get("repeat", "daily") if policy else "recovery"
    recovery_pct = float(policy.get("recovery_pct", 1)) if policy else (RECOVERY_FACTOR - 1) * 100
    recovery_minutes = int(policy.get("recovery_minutes", 10)) if policy else 0
    recovering = price > stop * (1 + recovery_pct / 100) and (
        not policy or now - quote <= timedelta(minutes=2)
    )
    if recovering:
        # Gaps beyond the quote freshness budget break the recovery streak.
        if last_seen is not None and now - last_seen > timedelta(minutes=2):
            state.pop("recovery_since", None)
        state.setdefault("recovery_since", quote.isoformat())
        since = _datetime(state["recovery_since"])
        if (
            since is not None
            and quote - since >= timedelta(minutes=recovery_minutes)
            and repeat == "recovery"
        ):
            state.update(triggered=False, retry_at=None)
    else:
        state.pop("recovery_since", None)
    if state.get("triggered") and policy:
        last = _datetime(state.get("last_sent_at"))
        from app.services.notification_delivery import _monitor_day

        if repeat == "daily" and last and _monitor_day(last) < _monitor_day(now):
            state["triggered"] = False
        elif (
            repeat == "interval"
            and last
            and now - last >= timedelta(minutes=int(policy.get("repeat_minutes", 60)))
        ):
            state["triggered"] = False
    if price > stop or state.get("triggered"):
        return state, None
    retry = _datetime(state.get("retry_at"))
    if retry is not None and now < retry:
        return state, None
    state["retry_at"] = (now + RETRY_DELAY).isoformat()
    quote_at = item["quote_at"]
    alert = {
        "kind": "stop",
        "ticker": item["ticker"],
        "name": item["name"],
        "current_price": price,
        "stop_price": stop,
        "currency": item["currency"],
        "quote_at": quote_at,
        "stop_identity": item["identity"],
        "alert_id": f"stop:{item['identity']}:{state.get('generation', 0)}:{quote_at}",
    }
    return state, alert


def deliver_stop_alerts(items, sender, *, now=None, preferences=None, additional_alerts=None):
    """Lock stop cycles and pass all alert categories through one dispatch call."""
    now = now or datetime.now(UTC)
    result = {"sent": 0, "accepted": 0, "failed": 0, "checked": 0, "deferred": 0}
    combined = additional_alerts is not None
    additional_alerts = list(additional_alerts or [])
    dispatch_attempted = False
    try:
        with SessionLocal() as db:
            transitions = []
            alerts = list(additional_alerts)
            for item in items:
                key = "stop_alert:" + item["identity"]
                if not db.scalar(
                    text("SELECT pg_try_advisory_xact_lock(hashtext(:key))"), {"key": key}
                ):
                    result["deferred"] += 1
                    continue
                row = db.scalar(select(AppSetting).where(AppSetting.key == key).with_for_update())
                state, alert = stop_transition(
                    row.value_json if row else {}, item, now, preferences=preferences
                )
                if row is None:
                    row = AppSetting(
                        key=key, value_json={}, description="Persistent stop crossing state"
                    )
                    db.add(row)
                transitions.append((row, state, alert))
                result["checked"] += 1
                if alert:
                    alerts.append(alert)
            dispatch_attempted = bool(alerts) or combined
            delivery = sender(alerts) if dispatch_attempted else {}
            result["delivery"] = delivery
            for row, state, alert in transitions:
                if alert:
                    sent = alert["alert_id"] in delivery.get("sent_alert_ids", [])
                    accepted = sent or alert["alert_id"] in delivery.get("accepted_alert_ids", [])
                    if accepted:
                        state.update(triggered=True, last_sent_at=now.isoformat(), retry_at=None)
                        result["accepted"] += 1
                        result["sent"] += int(sent)
                    else:
                        result["failed"] += 1
                row.value_json = state
            db.commit()
    except Exception:
        logger.exception("Stop state unavailable; stop notifications remain unaccepted")
        result["failed"] += 1
        if (additional_alerts or combined) and not dispatch_attempted:
            result["delivery"] = sender(additional_alerts)
    result.setdefault("delivery", {})
    return result


def rearm_stop_alerts(ticker: str) -> dict:
    """Explicitly rearm all current position stop cycles for the selected ticker."""
    ticker = ticker.strip().upper()
    changed = 0
    try:
        with SessionLocal() as db:
            # Take the same per-position lock as delivery before touching each state.
            keys = list(
                db.scalars(select(AppSetting.key).where(AppSetting.key.startswith("stop_alert:")))
            )
            for key in sorted(keys):
                db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": key})
                row = db.scalar(select(AppSetting).where(AppSetting.key == key).with_for_update())
                state = dict(row.value_json or {})
                if state.get("ticker") != ticker:
                    continue
                state.update(
                    triggered=False,
                    retry_at=None,
                    recovery_since=None,
                    generation=int(state.get("generation", 0)) + 1,
                    manually_rearmed_at=datetime.now(UTC).isoformat(),
                )
                row.value_json = state
                changed += 1
            db.commit()
    except SQLAlchemyError as exc:
        from app.repositories.settings import SettingsRepositoryUnavailable

        raise SettingsRepositoryUnavailable(str(exc)) from exc
    return {"ok": True, "ticker": ticker, "count": changed}
