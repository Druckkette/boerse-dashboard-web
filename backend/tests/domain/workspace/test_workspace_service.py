from datetime import UTC, datetime

from app.repositories.workspace import WorkspaceRepositoryUnavailable
from app.schemas import WorkspacePatch
from app.services import workspace as workspace_service


def test_workspace_normalizes_watchlist_and_recent_tickers(monkeypatch) -> None:
    def fake_read_workspace():
        return {
            "watchlist": [" nvda ", "NVDA", "brk.b", "bad/char"],
            "todos": "Tagesplan",
            "recent_tickers": ["msft", "MSFT", "aapl"],
        }, datetime(2026, 6, 12, tzinfo=UTC)

    monkeypatch.setattr(workspace_service.workspace_repository, "read_workspace", fake_read_workspace)

    state = workspace_service.get_workspace_state()

    assert state.source == "database"
    assert state.watchlist == ["NVDA", "BRK.B", "BADCHAR"]
    assert state.todos == "Tagesplan"
    assert state.recent_tickers == ["MSFT", "AAPL"]


def test_workspace_update_persists_normalized_state(monkeypatch) -> None:
    persisted = {}

    def fake_read_workspace():
        return {"watchlist": ["AAPL"], "todos": "", "recent_tickers": []}, None

    def fake_write_workspace(values: dict):
        persisted.update(values)
        return values, datetime(2026, 6, 12, tzinfo=UTC)

    monkeypatch.setattr(workspace_service.workspace_repository, "read_workspace", fake_read_workspace)
    monkeypatch.setattr(workspace_service.workspace_repository, "write_workspace", fake_write_workspace)

    state = workspace_service.update_workspace_state(
        WorkspacePatch(watchlist=["nvda", "NVDA", "msft"], todos="Checkliste", recent_tickers=["tsla"])
    )

    assert state.watchlist == ["NVDA", "MSFT"]
    assert state.recent_tickers == ["TSLA"]
    assert persisted["watchlist"] == ["NVDA", "MSFT"]
    assert persisted["todos"] == "Checkliste"


def test_workspace_falls_back_when_repository_unavailable(monkeypatch) -> None:
    def fake_read_workspace():
        raise WorkspaceRepositoryUnavailable("database down")

    monkeypatch.setattr(workspace_service.workspace_repository, "read_workspace", fake_read_workspace)

    state = workspace_service.get_workspace_state()

    assert state.source == "default"
    assert state.watchlist == []
    assert state.todos == ""


def test_add_recent_ticker_moves_existing_symbol_to_front(monkeypatch) -> None:
    persisted = {}

    def fake_read_workspace():
        return {"watchlist": [], "todos": "", "recent_tickers": ["MSFT", "NVDA"]}, None

    def fake_write_workspace(values: dict):
        persisted.update(values)
        return values, datetime(2026, 6, 12, tzinfo=UTC)

    monkeypatch.setattr(workspace_service.workspace_repository, "read_workspace", fake_read_workspace)
    monkeypatch.setattr(workspace_service.workspace_repository, "write_workspace", fake_write_workspace)

    state = workspace_service.add_recent_ticker("nvda")

    assert state.recent_tickers == ["NVDA", "MSFT"]
    assert persisted["recent_tickers"] == ["NVDA", "MSFT"]
