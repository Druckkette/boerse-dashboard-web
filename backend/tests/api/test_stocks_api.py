from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.main import app
from app.schemas import (
    PriceBarPoint,
    PriceHistoryResponse,
    PriceRefreshResponse,
    StockSearchItem,
    StockSearchResponse,
    StockSignalChange,
    StockSignalChangesResponse,
)


client = TestClient(app)


def test_stock_price_refresh_contract(monkeypatch) -> None:
    from app.api.v1 import stocks as stocks_api

    refreshed_at = datetime(2026, 6, 21, 10, 30, tzinfo=UTC)

    def fake_refresh_and_get_price_history(
        ticker: str,
        *,
        range_key: str,
        fetch_range_key: str,
        incremental: bool,
        timeout: int,
    ) -> PriceRefreshResponse:
        assert ticker == "NVDA"
        assert range_key == "1y"
        assert fetch_range_key == "2y"
        assert incremental is True
        assert timeout == 15
        history = PriceHistoryResponse(
            ticker="NVDA",
            name="NVDA",
            range="1y",
            source="database",
            data_status="fresh",
            as_of="2026-06-18",
            first_date="2025-06-18",
            last_date="2026-06-18",
            cache_updated_at=refreshed_at,
            last_close=150.0,
            change_pct=12.5,
            points=[
                PriceBarPoint(
                    date="2026-06-18",
                    open=148.0,
                    high=151.0,
                    low=147.5,
                    close=150.0,
                    adj_close=150.0,
                    volume=1_000_000,
                )
            ],
        )
        return PriceRefreshResponse(
            ticker="NVDA",
            ok=True,
            refreshed_at=refreshed_at,
            refresh={"ok": True, "fetch_mode": "incremental"},
            history=history,
        )

    monkeypatch.setattr(stocks_api, "refresh_and_get_price_history", fake_refresh_and_get_price_history)

    response = client.post("/api/v1/stocks/NVDA/prices/refresh?range=1y")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["refresh"]["fetch_mode"] == "incremental"
    assert payload["history"]["ticker"] == "NVDA"
    assert payload["history"]["last_date"] == "2026-06-18"
    assert payload["history"]["cache_updated_at"] == "2026-06-21T10:30:00Z"


def test_stock_search_contract(monkeypatch) -> None:
    from app.api.v1 import stocks as stocks_api

    monkeypatch.setattr(
        stocks_api,
        "search_stocks",
        lambda query, limit: StockSearchResponse(
            query=query,
            rows=[StockSearchItem(ticker="NVDA", name="NVIDIA Corporation", yahoo_symbol="NVDA")],
        ),
    )

    response = client.get("/api/v1/stocks/search?q=nvidia")

    assert response.status_code == 200
    assert response.json()["rows"][0]["ticker"] == "NVDA"


def test_stock_signal_changes_contract(monkeypatch) -> None:
    from app.api.v1 import stocks as stocks_api

    monkeypatch.setattr(
        stocks_api,
        "get_stock_signal_changes",
        lambda ticker: StockSignalChangesResponse(
            ticker=ticker,
            current_as_of="2026-07-24",
            previous_as_of="2026-07-23",
            changes=[
                StockSignalChange(
                    kind="new",
                    category="trend",
                    label="21-EMA unterschritten",
                    detail="Schlusskurs unter der Linie.",
                )
            ],
        ),
    )

    response = client.get("/api/v1/stocks/NVDA/changes")

    assert response.status_code == 200
    assert response.json()["changes"][0]["kind"] == "new"
