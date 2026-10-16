from __future__ import annotations

from datetime import datetime

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import text

from app.db.models import AppSetting
from app.db.session import SessionLocal


WORKSPACE_KEY = "workspace"


class WorkspaceRepositoryUnavailable(RuntimeError):
    pass


def read_workspace() -> tuple[dict, datetime | None]:
    try:
        with SessionLocal() as db:
            row = db.get(AppSetting, WORKSPACE_KEY)
            if row is None:
                return {}, None
            return dict(row.value_json or {}), row.updated_at
    except SQLAlchemyError as exc:
        raise WorkspaceRepositoryUnavailable(str(exc)) from exc


def write_workspace(values: dict) -> tuple[dict, datetime | None]:
    try:
        with SessionLocal() as db:
            row = db.get(AppSetting, WORKSPACE_KEY)
            if row is None:
                row = AppSetting(
                    key=WORKSPACE_KEY,
                    value_json=dict(values),
                    description="Personal watchlist, notes and recent ticker workspace.",
                )
                db.add(row)
            else:
                row.value_json = dict(values)
            db.commit()
            db.refresh(row)
            return dict(row.value_json or {}), row.updated_at
    except SQLAlchemyError as exc:
        raise WorkspaceRepositoryUnavailable(str(exc)) from exc


def saved_views(*, view: dict | None = None, remove_id: str | None = None) -> list[dict]:
    from datetime import UTC
    try:
        with SessionLocal() as db:
            if view is not None or remove_id:
                db.execute(text("SELECT pg_advisory_xact_lock(hashtext('dashboard:saved_views'))"))
            row = db.get(AppSetting, "dashboard_saved_views")
            items = list((row.value_json or {}).get("items", [])) if row else []
            if remove_id:
                items = [item for item in items if item.get("id") != remove_id]
            if view is not None:
                items = [item for item in items if item.get("id") != view["id"]]
                if len(items) >= 40:
                    raise ValueError("Maximal 40 Ansichten speichern. Zuerst eine Ansicht entfernen.")
                items.append({**view, "updated_at": datetime.now(UTC).isoformat()})
            if view is not None or remove_id:
                if row is None:
                    row = AppSetting(key="dashboard_saved_views", value_json={}, description="Private named dashboard views")
                    db.add(row)
                row.value_json = {"items": items}
                db.commit()
            return items
    except SQLAlchemyError as exc:
        raise WorkspaceRepositoryUnavailable("Ansichten konnten nicht geladen oder gespeichert werden.") from exc
