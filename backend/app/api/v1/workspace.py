from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Literal
from uuid import uuid4

from app.schemas import WorkspacePatch, WorkspaceState, WorkspaceTickerRequest
from app.services.home import invalidate_home_dashboard_cache
from app.services.workspace import (
    add_recent_ticker,
    add_watchlist_ticker,
    get_workspace_state,
    remove_watchlist_ticker,
    update_workspace_state,
)


router = APIRouter()


def persist(operation):
    from app.repositories.workspace import WorkspaceRepositoryUnavailable
    try:
        return operation()
    except WorkspaceRepositoryUnavailable as exc:
        raise HTTPException(status_code=503, detail="Watchlist konnte nicht gespeichert werden. Bitte erneut versuchen.") from exc


class SavedViewRequest(BaseModel):
    id: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")
    name: str = Field(min_length=1, max_length=60)
    scope: Literal["screening", "industry", "portfolio", "compare", "journal"]
    state: str = Field(max_length=8000)
    version: Literal[1] = 1


@router.get("/views")
def read_views() -> dict:
    from app.repositories.workspace import saved_views, WorkspaceRepositoryUnavailable
    try:
        return {"items": saved_views()}
    except WorkspaceRepositoryUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/views")
def save_view(payload: SavedViewRequest) -> dict:
    from app.repositories.workspace import saved_views, WorkspaceRepositoryUnavailable
    from urllib.parse import parse_qs
    import json
    params = parse_qs(payload.state)
    if not payload.name.strip():
        raise HTTPException(status_code=422, detail="Ansichtsname fehlt.")
    if params:
        try:
            state = json.loads(params[payload.scope][0])
            if not isinstance(state, dict) or state.get("version") != 1:
                raise ValueError()
        except (KeyError, ValueError, TypeError):
            raise HTTPException(status_code=422, detail="Unbekannte oder ungültige Ansichtsversion.") from None
    # Only the declared view namespace is retained. No credentials, arbitrary
    # navigation URLs, personal identifiers or cross-page state are stored.
    if set(params) - {payload.scope}:
        raise HTTPException(status_code=422, detail="Ansicht enthält unbekannte Parameter.")
    try:
        return {"items": saved_views(view={**payload.model_dump(), "id": payload.id or uuid4().hex, "name": payload.name.strip()})}
    except WorkspaceRepositoryUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.delete("/views/{view_id}")
def delete_view(view_id: str) -> dict:
    from app.repositories.workspace import saved_views, WorkspaceRepositoryUnavailable
    try:
        return {"items": saved_views(remove_id=view_id)}
    except WorkspaceRepositoryUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("", response_model=WorkspaceState)
def read_workspace() -> WorkspaceState:
    return get_workspace_state()


@router.patch("", response_model=WorkspaceState)
def patch_workspace(payload: WorkspacePatch) -> WorkspaceState:
    state = persist(lambda: update_workspace_state(payload))
    invalidate_home_dashboard_cache()
    return state


@router.post("/watchlist", response_model=WorkspaceState)
def add_watchlist_item(payload: WorkspaceTickerRequest) -> WorkspaceState:
    state = persist(lambda: add_watchlist_ticker(payload.ticker))
    invalidate_home_dashboard_cache()
    return state


@router.delete("/watchlist/{ticker}", response_model=WorkspaceState)
def remove_watchlist_item(ticker: str) -> WorkspaceState:
    state = persist(lambda: remove_watchlist_ticker(ticker))
    invalidate_home_dashboard_cache()
    return state


@router.post("/recent-tickers", response_model=WorkspaceState)
def add_recent_ticker_item(payload: WorkspaceTickerRequest) -> WorkspaceState:
    state = persist(lambda: add_recent_ticker(payload.ticker))
    invalidate_home_dashboard_cache()
    return state
