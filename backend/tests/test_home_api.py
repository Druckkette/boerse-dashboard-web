from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_home_contract_tolerates_partial_sources(monkeypatch) -> None:
    from app.api.v1 import home as home_api

    monkeypatch.setattr(home_api, "get_home_dashboard", lambda: {
        "as_of": "2026-09-28", "errors": ["industry_groups"], "priorities": [],
        "opportunities": [], "changes": [], "portfolio": {"positions_count": 0},
        "industry_groups": [], "watchlist": [], "market": {}, "data_quality": None,
    })
    response = client.get("/api/v1/home")
    assert response.status_code == 200
    assert response.json()["errors"] == ["industry_groups"]


def test_home_service_never_uses_live_sell_fallback(monkeypatch) -> None:
    from app.services import home

    monkeypatch.setattr(home.sell_state_repository, "list_ranking_snapshot", lambda: ([], None, ""))
    monkeypatch.setattr(home, "get_workspace_state", lambda: None)
    monkeypatch.setattr(home, "get_market_overview", lambda: None)
    monkeypatch.setattr(home, "get_breadth", lambda: None)
    monkeypatch.setattr(home, "get_volatility", lambda: None)
    monkeypatch.setattr(home, "get_data_quality_summary", lambda: None)
    monkeypatch.setattr(home.daily_opportunities, "get_top_daily", lambda: {"rows": [], "status": "not_ready"})
    monkeypatch.setattr(home, "_portfolio_summary", lambda: {"positions_count": 0, "positions": []})
    monkeypatch.setattr(home.industry_group_rs, "list_rankings", lambda **_: {"rows": []})
    monkeypatch.setattr(home.stock_assessments, "list_all_snapshots", lambda *_: [])
    payload = home.get_home_dashboard()
    assert payload["sell_rows"] == []
    assert payload["opportunities"] == []
