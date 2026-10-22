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


def tracked_watchlist_tickers() -> list[str]:
    values, _ = workspace_repository.read_workspace()
    return _normalize_ticker_list([*values.get("watchlist", []), *values.get("tracked_watchlists", [])], limit=3000)


def update_workspace_state(payload: WorkspacePatch) -> WorkspaceState:
    updates = payload.model_dump(exclude_none=True)
    return _mutate(lambda current: {**current, **updates})


def _mutate(operation) -> WorkspaceState:
    def normalized(values):
        current = operation(values)
        state = _workspace_from_values(current, updated_at=None, source="database")
        return {**current, "watchlist": state.watchlist, "todos": state.todos, "recent_tickers": state.recent_tickers}
    persisted, updated_at = workspace_repository.mutate_workspace(normalized)
    return _workspace_from_values(persisted, updated_at=updated_at, source="database")


def add_watchlist_ticker(ticker: str) -> WorkspaceState:
    clean = _normalize_ticker(ticker)
    if not clean:
        return get_workspace_state()
    return _mutate(lambda current: {**current, "watchlist": [clean, *[item for item in _normalize_ticker_list(current.get("watchlist")) if item != clean]][:MAX_TICKERS]})


def remove_watchlist_ticker(ticker: str) -> WorkspaceState:
    clean = _normalize_ticker(ticker)
    return _mutate(lambda current: {**current, "watchlist": [item for item in _normalize_ticker_list(current.get("watchlist")) if item != clean]})


def add_recent_ticker(ticker: str) -> WorkspaceState:
    clean = _normalize_ticker(ticker)
    if not clean:
        return get_workspace_state()
    return _mutate(lambda current: {**current, "recent_tickers": [clean, *[item for item in _normalize_ticker_list(current.get("recent_tickers"), limit=24) if item != clean]][:24]})


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
