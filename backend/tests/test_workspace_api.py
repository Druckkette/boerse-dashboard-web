from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.main import app
from app.schemas import WorkspaceState


client = TestClient(app)


def test_workspace_contract(monkeypatch) -> None:
    from app.api.v1 import workspace as workspace_api

    def fake_workspace() -> WorkspaceState:
        return WorkspaceState(
            source="database",
            updated_at=datetime(2026, 6, 12, tzinfo=UTC),
            watchlist=["NVDA", "MSFT"],
            todos="NVDA nach Earnings prüfen",
            recent_tickers=["AAPL"],
        )

    monkeypatch.setattr(workspace_api, "get_workspace_state", fake_workspace)

    response = client.get("/api/v1/workspace")

    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] == "database"
    assert payload["watchlist"] == ["NVDA", "MSFT"]
    assert payload["todos"] == "NVDA nach Earnings prüfen"
    assert payload["recent_tickers"] == ["AAPL"]


def test_workspace_patch_contract(monkeypatch) -> None:
    from app.api.v1 import workspace as workspace_api
    from app.schemas import WorkspacePatch

    def fake_patch(payload: WorkspacePatch) -> WorkspaceState:
        return WorkspaceState(
            source="database",
            updated_at=datetime(2026, 6, 12, tzinfo=UTC),
            watchlist=payload.watchlist or [],
            todos=payload.todos or "",
            recent_tickers=payload.recent_tickers or [],
        )

    monkeypatch.setattr(workspace_api, "update_workspace_state", fake_patch)

    response = client.patch(
        "/api/v1/workspace",
        json={"watchlist": ["nvda", "msft"], "todos": "Plan", "recent_tickers": ["aapl"]},
    )

    assert response.status_code == 200
    assert response.json()["watchlist"] == ["nvda", "msft"]
    assert response.json()["todos"] == "Plan"


def test_workspace_watchlist_mutation_contract(monkeypatch) -> None:
    from app.api.v1 import workspace as workspace_api

    def fake_add(ticker: str) -> WorkspaceState:
        return WorkspaceState(source="database", watchlist=[ticker.upper()], todos="", recent_tickers=[])

    def fake_remove(ticker: str) -> WorkspaceState:
        assert ticker == "NVDA"
        return WorkspaceState(source="database", watchlist=[], todos="", recent_tickers=[])

    monkeypatch.setattr(workspace_api, "add_watchlist_ticker", fake_add)
    monkeypatch.setattr(workspace_api, "remove_watchlist_ticker", fake_remove)

    add_response = client.post("/api/v1/workspace/watchlist", json={"ticker": "nvda"})
    remove_response = client.delete("/api/v1/workspace/watchlist/NVDA")

    assert add_response.status_code == 200
    assert add_response.json()["watchlist"] == ["NVDA"]
    assert remove_response.status_code == 200
    assert remove_response.json()["watchlist"] == []
