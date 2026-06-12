from __future__ import annotations

from datetime import datetime

from sqlalchemy.exc import SQLAlchemyError

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
