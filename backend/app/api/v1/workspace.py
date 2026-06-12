from fastapi import APIRouter

from app.schemas import WorkspacePatch, WorkspaceState, WorkspaceTickerRequest
from app.services.workspace import (
    add_recent_ticker,
    add_watchlist_ticker,
    get_workspace_state,
    remove_watchlist_ticker,
    update_workspace_state,
)


router = APIRouter()


@router.get("", response_model=WorkspaceState)
def read_workspace() -> WorkspaceState:
    return get_workspace_state()


@router.patch("", response_model=WorkspaceState)
def patch_workspace(payload: WorkspacePatch) -> WorkspaceState:
    return update_workspace_state(payload)


@router.post("/watchlist", response_model=WorkspaceState)
def add_watchlist_item(payload: WorkspaceTickerRequest) -> WorkspaceState:
    return add_watchlist_ticker(payload.ticker)


@router.delete("/watchlist/{ticker}", response_model=WorkspaceState)
def remove_watchlist_item(ticker: str) -> WorkspaceState:
    return remove_watchlist_ticker(ticker)


@router.post("/recent-tickers", response_model=WorkspaceState)
def add_recent_ticker_item(payload: WorkspaceTickerRequest) -> WorkspaceState:
    return add_recent_ticker(payload.ticker)
