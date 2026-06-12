from __future__ import annotations

from datetime import datetime

from app.repositories import workspace as workspace_repository
from app.repositories.workspace import WorkspaceRepositoryUnavailable
from app.schemas import WorkspacePatch, WorkspaceState


MAX_TICKERS = 100
MAX_TODOS_LENGTH = 12_000


def get_workspace_state() -> WorkspaceState:
    try:
        values, updated_at = workspace_repository.read_workspace()
        return _workspace_from_values(values, updated_at=updated_at, source="database")
    except WorkspaceRepositoryUnavailable:
        return _workspace_from_values({}, updated_at=None, source="default")


def update_workspace_state(payload: WorkspacePatch) -> WorkspaceState:
    current = get_workspace_state().model_dump()
    source = current.pop("source", "default")
    current.pop("updated_at", None)
    updates = payload.model_dump(exclude_none=True)
    merged = {
        **current,
        **updates,
    }
    next_state = _workspace_from_values(merged, updated_at=None, source="database")
    try:
        persisted, updated_at = workspace_repository.write_workspace(
            {
                "watchlist": next_state.watchlist,
                "todos": next_state.todos,
                "recent_tickers": next_state.recent_tickers,
            }
        )
        return _workspace_from_values(persisted, updated_at=updated_at, source="database")
    except WorkspaceRepositoryUnavailable:
        return next_state.model_copy(update={"source": source})


def add_watchlist_ticker(ticker: str) -> WorkspaceState:
    state = get_workspace_state()
    clean = _normalize_ticker(ticker)
    if not clean:
        return state
    watchlist = [item for item in state.watchlist if item != clean]
    watchlist.insert(0, clean)
    return update_workspace_state(WorkspacePatch(watchlist=watchlist[:MAX_TICKERS]))


def remove_watchlist_ticker(ticker: str) -> WorkspaceState:
    clean = _normalize_ticker(ticker)
    state = get_workspace_state()
    return update_workspace_state(WorkspacePatch(watchlist=[item for item in state.watchlist if item != clean]))


def add_recent_ticker(ticker: str) -> WorkspaceState:
    state = get_workspace_state()
    clean = _normalize_ticker(ticker)
    if not clean:
        return state
    recent = [item for item in state.recent_tickers if item != clean]
    recent.insert(0, clean)
    return update_workspace_state(WorkspacePatch(recent_tickers=recent[:24]))


def _workspace_from_values(values: dict, *, updated_at: datetime | None, source: str) -> WorkspaceState:
    watchlist = _normalize_ticker_list(values.get("watchlist"))
    recent_tickers = _normalize_ticker_list(values.get("recent_tickers"), limit=24)
    todos = str(values.get("todos") or "")[:MAX_TODOS_LENGTH]
    return WorkspaceState(
        source=source,
        updated_at=updated_at,
        watchlist=watchlist,
        todos=todos,
        recent_tickers=recent_tickers,
    )


def _normalize_ticker_list(value: object, *, limit: int = MAX_TICKERS) -> list[str]:
    if not isinstance(value, list):
        return []
    normalized: list[str] = []
    for item in value:
        clean = _normalize_ticker(str(item))
        if clean and clean not in normalized:
            normalized.append(clean)
    return normalized[:limit]


def _normalize_ticker(value: str) -> str:
    allowed = []
    for char in value.strip().upper():
        if char.isalnum() or char in {".", "-"}:
            allowed.append(char)
    return "".join(allowed)[:32]
