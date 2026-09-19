"""Persistent stop-crossing alerts, separate from the ATR daily cooldown."""
from datetime import UTC, datetime, timedelta
import logging
import math
from time import monotonic

from sqlalchemy import select, text
from app.db.models import AppSetting
from app.db.session import SessionLocal

logger = logging.getLogger(__name__)
RECOVERY_FACTOR = 1.005
RETRY_DELAY = timedelta(minutes=15)


def stop_transition(previous: dict, item: dict, now: datetime) -> tuple[dict, dict | None]:
    price, stop = item.get("price"), item.get("stop")
    if not all(isinstance(v, (int, float)) and math.isfinite(v) and v > 0 for v in (price, stop)):
        return previous, None
    quote_at = item.get("quote_at")
    if not quote_at:
        return previous, None
    quote = datetime.fromisoformat(quote_at.replace("Z", "+00:00"))
    quote = quote.replace(tzinfo=UTC) if quote.tzinfo is None else quote
    if not timedelta(0) <= now - quote <= timedelta(minutes=20):
        return previous, None
    state = dict(previous)
    if state.get("stop") != stop:
        state = {"stop": stop, "triggered": False, "generation": int(state.get("generation", 0)) + 1}
    if price > stop * RECOVERY_FACTOR:
        state.update(triggered=False, retry_at=None)
    if price > stop or state.get("triggered"):
        return state, None
    if state.get("retry_at") and now < datetime.fromisoformat(state["retry_at"]):
        return state, None
    state["retry_at"] = (now + RETRY_DELAY).isoformat()
    alert = {"kind": "stop", "ticker": item["ticker"], "name": item["name"],
             "current_price": price, "stop_price": stop, "currency": item["currency"],
             "quote_at": quote_at, "alert_id": f"stop:{item['identity']}:{state.get('generation', 0)}:{quote_at}"}
    return state, alert


def deliver_stop_alerts(items, sender, *, now=None):
    now = now or datetime.now(UTC)
    result = {"sent": 0, "failed": 0, "checked": 0, "deferred": 0}
    started = monotonic()
    for index, item in enumerate(items):
        # Leave time for the existing ATR path when the provider is slow (15s HTTP timeout).
        if monotonic() - started >= 8:
            result["deferred"] = len(items) - index
            break
        try:
            with SessionLocal() as db:
                key = "stop_alert:" + item["identity"]
                # Serializes state transitions and dispatch across overlapping workers.
                if not db.scalar(text("SELECT pg_try_advisory_xact_lock(hashtext(:key))"), {"key": key}):
                    continue
                row = db.scalar(select(AppSetting).where(AppSetting.key == key).with_for_update())
                state, alert = stop_transition(row.value_json if row else {}, item, now)
                if row is None:
                    row = AppSetting(key=key, value_json={}, description="Persistent stop crossing state")
                    db.add(row)
                result["checked"] += 1
                if alert:
                    try:
                        delivered = sender([alert])
                        sent = alert["alert_id"] in delivered.get("sent_alert_ids", [])
                    except Exception:
                        logger.exception("Stop notification failed: %s", item["ticker"])
                        sent = False
                    if sent:
                        state.update(triggered=True, last_sent_at=now.isoformat(), retry_at=None)
                        result["sent"] += 1
                    else:
                        result["failed"] += 1
                row.value_json = state
                db.commit()
        except Exception:
            # Never notify without persisted state storage; outages must not create spam.
            logger.exception("Stop state unavailable: %s", item.get("ticker"))
            result["failed"] += 1
    return result
