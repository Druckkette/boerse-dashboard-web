from datetime import UTC, datetime


def refresh_prices() -> dict:
    return {"ok": True, "task": "refresh_prices", "completed_at": datetime.now(UTC).isoformat()}


def recompute_sell_ranking() -> dict:
    return {"ok": True, "task": "recompute_sell_ranking", "completed_at": datetime.now(UTC).isoformat()}

