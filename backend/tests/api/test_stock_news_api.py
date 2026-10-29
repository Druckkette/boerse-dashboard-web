from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.stocks import router
from app.schemas_news import StockNewsResponse
from app.services import stock_news


def test_news_endpoint_returns_only_public_contract_and_passes_selected_ticker(monkeypatch):
    calls = []

    def get(ticker):
        calls.append(ticker)
        return StockNewsResponse(ticker=ticker, status="empty", updated_at=datetime(2026, 10, 28, tzinfo=UTC))

    monkeypatch.setattr(stock_news, "get_stock_news", get)
    app = FastAPI()
    app.include_router(router, prefix="/stocks")
    with TestClient(app) as client:
        result = client.get("/stocks/NVDA/news")
        assert result.status_code == 200
        assert result.json() == {"ticker": "NVDA", "articles": [], "updated_at": "2026-10-28T00:00:00Z",
                                 "status": "empty", "cached": False, "message": None}
        assert client.get("/stocks/AAPL/news").json()["ticker"] == "AAPL"
    assert calls == ["NVDA", "AAPL"]
