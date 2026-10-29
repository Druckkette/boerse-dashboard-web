"""Describe ongoing conditions from actual observed quotes, never sent messages."""
from datetime import UTC, datetime, timedelta
import math


def _number(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def _stamp(value):
    try:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return result.replace(tzinfo=UTC) if result.tzinfo is None else result
    except (TypeError, ValueError):
        return None


def _de(value, digits=2):
    return f"{value:,.{digits}f}".replace(",", "§").replace(".", ",").replace("§", ".")


def _subject(entry):
    event = (entry.get("alert", {}).get("events") or [{}])[0]
    return entry.get("ticker"), entry.get("category"), event.get("ma_key", "")


def snapshot_summary_entries(snapshots: dict, prefs: dict, now: datetime, *, existing_entries=()) -> list[dict]:
    """Supplement changes with recent observed status when explicitly requested.

    Quotes were validated before storage. The daily summary may describe their
    last observed state after the exchange closed, but never an older trading day.
    """
    excluded = {_subject(entry) for entry in existing_entries}
    result = []
    categories = set(prefs.get("summary", {}).get("categories", []))

    def add(ticker, category, label, snapshot, *, ma_key="", warning=True):
        if category not in categories or (ticker, category, ma_key) in excluded:
            return
        identifier = f"observed:{ticker}:{category}:{ma_key}:{snapshot['observed_at']}"
        event = {"label": label, "detail": "Zuletzt beobachteter Zustand.",
                 "tone": "warning" if warning else "neutral", "category": category,
                 "event_type": "current_status", "event_id": identifier, "mode": "digest"}
        if ma_key:
            event["ma_key"] = ma_key
        result.append({"id": identifier, "parent_id": identifier, "ticker": ticker,
                       "category": category, "mode": "digest", "at": snapshot["observed_at"],
                       "alert": {"kind": "stock_signal", "ticker": ticker, "events": [event]}})

    for ticker, snapshot in sorted(snapshots.items()):
        observed = _stamp(snapshot.get("observed_at"))
        if observed is None or not timedelta(0) <= now - observed <= timedelta(hours=24):
            continue
        monitor = snapshot.get("monitor") or {}
        price = _number(monitor.get("current_price"))
        distance = _number(monitor.get("distance_atr"))
        threshold = _number(monitor.get("threshold_atr"))
        if prefs.get("atr", {}).get("mode") != "off" and distance is not None and threshold is not None and distance >= threshold:
            add(ticker, "atr", f"Zuletzt weiterhin {_de(distance, 1)} ATR unter dem Referenzkurs.", snapshot)
        stop = snapshot.get("stop_observation") or {}
        stop_price, stop_limit = _number(stop.get("price")), _number(stop.get("stop"))
        if prefs.get("stop", {}).get("mode") != "off" and stop_price is not None and stop_limit is not None and stop_price <= stop_limit:
            add(ticker, "stop", f"Zuletzt weiterhin am oder unter dem Stopp von {_de(stop_limit)} {stop.get('currency') or 'USD'}.", snapshot)
        atr = _number(monitor.get("atr_value"))
        averages = (snapshot.get("trend_monitor") or {}).get("moving_averages") or {}
        for key, label in (("sma10", "10-Tage-Linie"), ("ema21", "21-Tage-EMA"), ("sma50", "50-Tage-Linie"), ("sma200", "200-Tage-Linie")):
            rule = prefs.get("ma", {}).get(key, {})
            if all(rule.get(mode, "off") == "off" for mode in ("break_mode", "recovery_mode", "worsening_mode")):
                continue
            average = averages.get(key) or {}
            distance_pct = _number(average.get("distance_pct"))
            required = _number(rule.get("min_distance"))
            if distance_pct is None or required is None:
                continue
            if rule.get("distance_unit") == "atr":
                if atr is None or price is None or price <= 0:
                    continue
                required = required * atr / price * 100
            if distance_pct <= -required:
                add(ticker, "ma", f"Zuletzt weiterhin {_de(abs(distance_pct), 1)} Prozent unter der {label}.", snapshot, ma_key=key)
        assessment = snapshot.get("assessment") or snapshot.get("notification_assessment") or {}
        policy = prefs.get("assessment", {})
        score = _number(assessment.get("overall_score"))
        if policy.get("score_mode") != "off" and score is not None:
            add(ticker, "score", f"Zuletzt berechneter Gesamtscore: {int(score)} Punkte.", snapshot, warning=False)
        verdict = assessment.get("verdict_label")
        if policy.get("verdict_mode") != "off" and verdict:
            add(ticker, "verdict", f"Zuletzt berechnetes Aktienurteil: {verdict}.", snapshot, warning=False)
    return result
