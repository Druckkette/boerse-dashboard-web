"""Private bounded JSON workspace; serializes mutations and preserves legacy data."""

from copy import deepcopy
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from app.db.models import AppSetting
from app.db.session import SessionLocal

KEY = "professional_workspace_v1"


class DeskUnavailable(RuntimeError):
    pass


class DeskConflict(ValueError):
    pass


def transact(operation=None, *, revision=None):
    try:
        with SessionLocal() as db:
            if operation is not None:
                db.execute(
                    text(
                        "SELECT pg_advisory_xact_lock(hashtext('dashboard:professional_workspace'))"
                    )
                )
            row = db.get(AppSetting, KEY)
            legacy = db.get(AppSetting, "workspace")
            state = deepcopy(row.value_json if row else {})
            state.setdefault("revision", 0)
            for name in ("watchlists", "plans", "alerts", "history", "events", "accounts"):
                state.setdefault(name, [])
            favorite = next((item for item in state["watchlists"] if item["id"] == "default"), None)
            old_items = {item["ticker"]: item for item in favorite["items"]} if favorite else {}
            favorite = dict(
                id="default",
                name=(favorite or {}).get("name", "Meine Watchlist"),
                items=[
                    old_items.get(
                        ticker, {"ticker": ticker, "note": "", "tags": [], "stage": "discovered"}
                    )
                    for ticker in (legacy.value_json or {}).get("watchlist", [])
                ]
                if legacy
                else [],
            )
            state["watchlists"] = [
                favorite,
                *[item for item in state["watchlists"] if item["id"] != "default"],
            ]
            if operation is None:
                return state
            if revision is not None and revision != state["revision"]:
                raise DeskConflict(
                    "Die Daten wurden inzwischen geändert. Neu laden und erneut speichern."
                )
            result = operation(state)
            state["revision"] += 1
            if row is None:
                row = AppSetting(
                    key=KEY,
                    description="Private watchlists, plans, alerts, calendar and additional account ledgers",
                )
                db.add(row)
            row.value_json = state
            favorites = next(item for item in state["watchlists"] if item["id"] == "default")
            if legacy is None:
                legacy = AppSetting(key="workspace", description="Personal workspace")
                db.add(legacy)
            legacy.value_json = {
                **(legacy.value_json or {}),
                "watchlist": [item["ticker"] for item in favorites["items"]],
                "tracked_watchlists": list(
                    dict.fromkeys(
                        item["ticker"]
                        for row in state["watchlists"]
                        if row["id"] != "default"
                        for item in row["items"]
                    )
                ),
            }
            db.commit()
            return result if result is not None else state
    except SQLAlchemyError as exc:
        raise DeskUnavailable(
            "Arbeitsbereich derzeit nicht verfügbar. Änderungen wurden nicht bestätigt."
        ) from exc
