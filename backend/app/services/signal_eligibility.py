"""Presentation eligibility shared by home, monitor and exports, not trading rules."""
from datetime import UTC, datetime
from app.services.market_calendar import completed_us_market_session, expected_us_market_session


def sell_signal_eligibility(row: dict, *, now: datetime | None = None, completed: str | None = None, expected: str | None = None) -> dict:
    now = now or datetime.now(UTC)
    completed = completed or completed_us_market_session(now).date.isoformat()
    expected = expected or expected_us_market_session(now).date.isoformat()
    seen = str(row.get("last_seen_date") or "")
    generated = row.get("generated_at")
    try:
        generated = generated if isinstance(generated, datetime) else datetime.fromisoformat(str(generated).replace("Z", "+00:00"))
        if generated.tzinfo is None:
            generated = generated.replace(tzinfo=UTC)
        current = completed <= seen <= expected and generated.date().isoformat() >= completed and generated <= now
    except (ValueError, TypeError):
        current = False
    trusted = row.get("data_quality_status") == "trusted"
    if not current or not trusted:
        reason = "Verkaufsbewertung nicht aktuell oder Erzeugungszeitpunkt fehlt." if not current else row.get("data_quality_detail") or "Eingeschränkte Datenbasis."
        return dict(decision_eligible=False, decision_category="data", eligibility_reason=reason, signal_current=current)
    eligible = row.get("status") == "Verkaufen" and row.get("pending_status") == "scharf" and (row.get("recommendation_pct") or 0) > 0
    category = "action" if eligible else "observe" if row.get("status") != "Halten" or row.get("pending_status") in {"in_bestaetigung", "snoozed"} else "hold"
    return dict(decision_eligible=eligible, decision_category=category, eligibility_reason="", signal_current=current)
