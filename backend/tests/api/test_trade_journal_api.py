from datetime import date

from fastapi.testclient import TestClient

from app.main import app
from app.schemas import (
    TradeJournalDefaultsResponse,
    TradeJournalEntryDetail,
    TradeJournalEntryRequest,
    TradeJournalEntryResponse,
    TradeJournalEntrySummary,
)


client = TestClient(app)


def test_trade_journal_defaults_contract(monkeypatch) -> None:
    from app.api.v1 import trade_journal as api

    def fake_defaults(ticker: str, entry_type: str) -> TradeJournalDefaultsResponse:
        return TradeJournalDefaultsResponse(
            ticker=ticker.upper(),
            entry_type=entry_type,
            trade_date="2026-06-23",
            price=125.5,
            shares=10,
            stop_price=116.0,
            stop_distance_pct=7.57,
            portfolio_snapshot={"position_size_eur": 1098.0},
            market_snapshot={"ampel": {"phase_label": "Aufwärtstrend"}},
        )

    monkeypatch.setattr(api, "get_trade_journal_defaults", fake_defaults)

    response = client.get("/api/v1/trade-journal/defaults?ticker=nvda&entry_type=buy")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ticker"] == "NVDA"
    assert payload["entry_type"] == "buy"
    assert payload["stop_distance_pct"] == 7.57


def test_trade_journal_create_contract(monkeypatch) -> None:
    from app.api.v1 import trade_journal as api

    def fake_create(payload: TradeJournalEntryRequest) -> TradeJournalEntryResponse:
        detail = TradeJournalEntryDetail(
            id="entry-1",
            ticker=payload.ticker.upper(),
            entry_type=payload.entry_type,
            status="open",
            trade_date=(payload.trade_date or date(2026, 6, 23)).isoformat(),
            price=payload.price,
            shares=payload.shares,
            stop_price=payload.stop_price,
            stop_distance_pct=7.0,
            title=f"Kauf {payload.ticker.upper()} · 2026-06-23",
            summary="10 Stk. zu 100.00 USD",
            created_at="2026-06-23T10:00:00+00:00",
            updated_at="2026-06-23T10:00:00+00:00",
            basis_text=payload.basis_text,
            primary_reasons=payload.primary_reasons,
            stock_snapshot={"checks": []},
            market_snapshot={"ampel": {"phase_label": "Grün"}},
            portfolio_snapshot={"position_size_eur": 900},
            chart_images=payload.chart_images,
        )
        return TradeJournalEntryResponse(entry=detail)

    monkeypatch.setattr(api, "create_trade_journal_entry", fake_create)

    response = client.post(
        "/api/v1/trade-journal",
        json={
            "ticker": "nvda",
            "entry_type": "buy",
            "trade_date": "2026-06-23",
            "price": 100,
            "shares": 10,
            "stop_price": 93,
            "basis_text": "Rückkehr zur 50-Tage-Linie",
            "primary_reasons": "RS stark",
        },
    )

    assert response.status_code == 200
    payload = response.json()["entry"]
    assert payload["ticker"] == "NVDA"
    assert payload["stock_snapshot"]["checks"] == []
    assert payload["chart_images"]["daily_chart"] == ""


def test_trade_journal_list_contract(monkeypatch) -> None:
    from app.api.v1 import trade_journal as api
    from app.schemas import TradeJournalEntriesResponse

    def fake_entries(ticker: str | None = None) -> TradeJournalEntriesResponse:
        return TradeJournalEntriesResponse(
            ticker=ticker,
            entries=[
                TradeJournalEntrySummary(
                    id="entry-1",
                    ticker="NVDA",
                    entry_type="buy",
                    status="open",
                    trade_date="2026-06-23",
                    price=100,
                    shares=10,
                    title="Kauf NVDA · 2026-06-23",
                    summary="10 Stk. zu 100.00 USD",
                    created_at="2026-06-23T10:00:00+00:00",
                    updated_at="2026-06-23T10:00:00+00:00",
                )
            ],
        )

    monkeypatch.setattr(api, "get_trade_journal_entries", fake_entries)

    response = client.get("/api/v1/trade-journal?ticker=NVDA")

    assert response.status_code == 200
    assert response.json()["entries"][0]["title"].startswith("Kauf NVDA")
