from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health() -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_market_overview_contract() -> None:
    response = client.get("/api/v1/market/overview")
    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] in {"database", "synthetic_fixture", "missing"}
    assert payload["data_status"] in {"fresh", "stale", "missing", "fallback"}
    assert payload["phase_label"]
    assert payload["trend_ampel"] is None or {"ticker", "phase", "phase_label", "as_of"}.issubset(
        payload["trend_ampel"]
    )
    assert isinstance(payload["kpis"], list)


def test_market_breadth_contract() -> None:
    response = client.get("/api/v1/market/breadth")
    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] in {"database", "synthetic_fixture", "missing"}
    assert payload["data_status"] in {"fresh", "stale", "missing", "fallback"}
    assert isinstance(payload["coverage_ratio"], int | float)
    assert isinstance(payload["points"], list)
    if payload["points"]:
        assert {"date", "advancers", "decliners", "pct_above_50sma"}.issubset(payload["points"][0])


def test_market_universe_contract() -> None:
    response = client.get("/api/v1/market/universe")
    assert response.status_code == 200
    payload = response.json()
    assert payload["key"]
    assert isinstance(payload["member_count"], int)
    assert isinstance(payload["sample_tickers"], list)
    assert isinstance(payload["metadata"], dict)


def test_market_volatility_contract() -> None:
    response = client.get("/api/v1/market/volatility")
    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] in {"database", "missing"}
    assert payload["regime"]
    assert isinstance(payload["status_cards"], list)
    assert isinstance(payload["points"], list)


def test_market_diagnostics_contract() -> None:
    response = client.get("/api/v1/market/diagnostics")
    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] in {"database", "synthetic_fixture", "missing"}
    assert payload["data_status"] in {"fresh", "stale", "missing", "fallback"}
    assert isinstance(payload["warning_count"], int)
    assert isinstance(payload["checklist"], list)
    assert isinstance(payload["intermarket"], list)
    assert isinstance(payload["sector_rotation"], list)
    if payload["checklist"]:
        assert {"category", "label", "passed", "detail", "tone"}.issubset(payload["checklist"][0])


def test_market_sectors_contract() -> None:
    response = client.get("/api/v1/market/sectors?mode=daily&periods=10")
    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] in {"database", "synthetic_fixture", "missing"}
    assert payload["data_status"] in {"fresh", "stale", "missing", "fallback"}
    assert payload["mode"] == "daily"
    assert isinstance(payload["rows"], list)
    assert isinstance(payload["history"], list)
    if payload["rows"]:
        assert {"ticker", "name", "rank", "return_pct"}.issubset(payload["rows"][0])


def test_stock_price_history_contract() -> None:
    response = client.get("/api/v1/stocks/NVDA/prices?range=3m")
    assert response.status_code == 200
    payload = response.json()
    assert payload["ticker"] == "NVDA"
    assert payload["range"] == "3m"
    assert payload["points"]
    assert {"date", "close"}.issubset(payload["points"][0])


def test_rs_ranking_contract() -> None:
    response = client.get("/api/v1/stocks/ratings/rs")
    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] in {"database", "missing"}
    assert isinstance(payload["rows"], list)
    if payload["rows"]:
        assert {"ticker", "rating", "percentile", "date"}.issubset(payload["rows"][0])


def test_stock_rs_detail_contract() -> None:
    response = client.get("/api/v1/stocks/NVDA/rs")
    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] in {"database", "missing"}
    assert isinstance(payload["found"], bool)


def test_stock_assessment_contract() -> None:
    response = client.get("/api/v1/stocks/NVDA/assessment")
    assert response.status_code == 200
    payload = response.json()
    assert payload["ticker"] == "NVDA"
    assert payload["source"] in {"database", "missing"}
    assert payload["data_status"] in {"fresh", "stale", "missing"}
    assert {"overall", "technical", "fundamental", "moving_averages", "chart_behavior"}.issubset(
        payload["scores"]
    )
    assert isinstance(payload["checks"], list)
    assert isinstance(payload["chart_signals"], list)


def test_stock_fundamentals_contract() -> None:
    response = client.get("/api/v1/stocks/NVDA/fundamentals")
    assert response.status_code == 200
    payload = response.json()
    assert payload["ticker"] == "NVDA"
    assert payload["source"] in {"database", "missing"}
    assert "item" in payload


def test_patch_stock_fundamentals_contract(monkeypatch) -> None:
    from app.api.v1 import stocks as stocks_api
    from app.schemas import StockFundamentalsItem, StockFundamentalsResponse

    def fake_update(ticker, request):
        return StockFundamentalsResponse(
            ticker=ticker.upper(),
            source="database",
            item=StockFundamentalsItem(
                ticker=ticker.upper(),
                as_of=request.as_of or "2026-06-12",
                source=request.source,
                fiscal_period=request.fiscal_period,
                quarterly_eps_growth_pct=request.quarterly_eps_growth_pct,
                annual_eps_growth_pct=None,
                quarterly_revenue_growth_pct=None,
                annual_revenue_growth_pct=None,
                roe_pct=request.roe_pct,
                profit_margin_pct=None,
                trailing_eps=None,
                quarterly_eps_accelerating=None,
                quarterly_revenue_accelerating=None,
                institutional_holders=None,
                institutional_ownership_pct=None,
                next_earnings_date=None,
                beta=None,
            ),
        )

    monkeypatch.setattr(stocks_api, "update_stock_fundamentals", fake_update)
    response = client.patch(
        "/api/v1/stocks/NVDA/fundamentals",
        json={
            "as_of": "2026-06-12",
            "source": "manual",
            "fiscal_period": "Q1 2026",
            "quarterly_eps_growth_pct": 42.0,
            "roe_pct": 21.0,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] == "database"
    assert payload["item"]["quarterly_eps_growth_pct"] == 42.0


def test_stock_assessment_ranking_contract() -> None:
    response = client.get("/api/v1/stocks/assessment/ranking?limit=10")
    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] in {"database", "missing"}
    assert isinstance(payload["rows"], list)
    if payload["rows"]:
        assert {"ticker", "overall_score", "technical_score", "verdict_label"}.issubset(payload["rows"][0])


def test_stock_institutional_13f_contract() -> None:
    response = client.get("/api/v1/stocks/NVDA/institutional/13f")
    assert response.status_code == 200
    payload = response.json()
    assert payload["ticker"] == "NVDA"
    assert payload["source"] in {"database", "missing"}
    assert "as_of" in payload


def test_sec13f_mapping_review_contract() -> None:
    response = client.get("/api/v1/stocks/institutional/13f/mappings")
    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] in {"database", "missing"}
    assert isinstance(payload["mappings"], list)
    assert isinstance(payload["unmatched"], list)
    assert "unmatched_source_job_id" in payload


def test_patch_sec13f_mapping_contract(monkeypatch) -> None:
    from app.api.v1 import stocks as stocks_api
    from app.schemas import (
        Sec13FMappingItem,
        Sec13FMappingReviewResponse,
    )

    def fake_update(request):
        return Sec13FMappingReviewResponse(
            source="database",
            as_of="2026-06-12",
            mappings=[
                Sec13FMappingItem(
                    cusip=request.cusip,
                    ticker=request.ticker.upper(),
                    issuer_name=request.issuer_name,
                    source="manual",
                    confidence=1.0,
                )
            ],
            unmatched=[],
        )

    monkeypatch.setattr(stocks_api, "update_sec13f_manual_mapping", fake_update)
    response = client.patch(
        "/api/v1/stocks/institutional/13f/mappings",
        json={"cusip": "67066G104", "ticker": "nvda", "issuer_name": "NVIDIA CORP"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["mappings"][0]["cusip"] == "67066G104"
    assert payload["mappings"][0]["ticker"] == "NVDA"


def test_portfolio_import_dry_run_contract() -> None:
    response = client.post(
        "/api/v1/portfolio/imports/positions",
        json={
            "file_name": "positions.csv",
            "content": "Ticker,Shares,Entry_Price\nNVDA,12,91.2\n",
            "dry_run": True,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["dry_run"] is True
    assert payload["positions"][0]["ticker"] == "NVDA"


def test_trade_republic_transaction_import_preview_contract() -> None:
    csv_content = (
        "date,datetime,type,asset_class,name,symbol,shares,price,currency,amount,fee,tax\n"
        "2025-01-02,2025-01-02T10:00:00Z,BUY,STOCK,NVIDIA,US67066G1040,10,100,USD,-1000,-1,0\n"
        "2025-01-10,2025-01-10T10:00:00Z,SELL,STOCK,NVIDIA,US67066G1040,2,120,USD,240,-1,-10\n"
    )
    response = client.post(
        "/api/v1/portfolio/imports/tr-transactions",
        json={
            "file_name": "transactions.csv",
            "content": csv_content,
            "dry_run": True,
            "replace_open_positions": False,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["dry_run"] is True
    assert payload["rows_total"] == 2
    assert payload["transactions_total"] == 2
    assert payload["cash_balance_estimate"] == -772
    assert payload["positions"][0]["ticker"] == "NVDA"
    assert payload["positions"][0]["shares"] == 8
    assert payload["mappings"][0]["isin"] == "US67066G1040"


def test_isin_mappings_contract() -> None:
    response = client.get("/api/v1/portfolio/isin-mappings")
    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload["mappings"], list)


def test_portfolio_transactions_contract() -> None:
    response = client.get("/api/v1/portfolio/transactions")
    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload["transactions"], list)


def test_portfolio_cash_flows_contract() -> None:
    response = client.get("/api/v1/portfolio/cash-flows")
    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload["cash_flows"], list)
    assert isinstance(payload["cash_balance"], int | float)


def test_portfolio_curve_contract() -> None:
    response = client.get("/api/v1/portfolio/curve")
    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] in {"database", "trade_republic_transactions", "missing"}
    assert payload["data_status"] in {"fresh", "missing"}
    assert isinstance(payload["points"], list)


def test_portfolio_position_size_contract() -> None:
    response = client.post(
        "/api/v1/portfolio/position-size",
        json={
            "depot_value": 100000,
            "risk_per_position_pct": 1,
            "target_risk_contribution": 0.2,
            "buy_price": 100,
            "stop_pct": 7,
            "current_price": 100,
            "atr_pct": 4,
            "beta": 1.2,
            "market_atr_pct": 2,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["risk_budget"] == 1000
    assert payload["risk_per_share"] == 7
    assert payload["max_shares_by_loss_budget"] == 142
    assert payload["recommended_max_shares"] > 0
    assert payload["limiting_factor"] in {"loss_budget", "beta_balancer", "insufficient_data"}


def test_portfolio_import_history_contract() -> None:
    response = client.get("/api/v1/portfolio/imports")
    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload["imports"], list)


def test_sell_metrics_contract() -> None:
    response = client.get("/api/v1/sell/PLTR/metrics")
    assert response.status_code == 200
    assert response.json()["ticker"] == "PLTR"


def test_sell_diagnostics_contract() -> None:
    response = client.get("/api/v1/sell/NVDA/diagnostics")
    assert response.status_code == 200
    payload = response.json()
    assert payload["ticker"] == "NVDA"
    assert isinstance(payload["price_context"], list)
    assert isinstance(payload["strategy_hub"], list)
    assert isinstance(payload["post_mortem"], list)
    assert isinstance(payload["post_mortem_notes"], list)
    assert payload["next_action"]


def test_sell_post_mortem_note_contract() -> None:
    response = client.post(
        "/api/v1/sell/NOTE/post-mortem",
        json={
            "check_key": "data_quality",
            "note": "Teilverkauf nach dem Signal prüfen.",
            "action": "Stop am nächsten Handelstag nachziehen.",
            "status": "open",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["note"]["ticker"] == "NOTE"
    assert payload["note"]["check_key"] == "data_quality"
    assert payload["note"]["status"] == "open"
    assert any(note["check_key"] == "data_quality" for note in payload["notes"])

    diagnostics = client.get("/api/v1/sell/NOTE/diagnostics")
    assert diagnostics.status_code == 200
    assert any(note["check_key"] == "data_quality" for note in diagnostics.json()["post_mortem_notes"])


def test_settings_data_diagnostics_contract() -> None:
    response = client.get("/api/v1/settings/data-diagnostics")
    assert response.status_code == 200
    payload = response.json()
    assert payload["health_tone"] in {"good", "neutral", "warning", "bad"}
    assert isinstance(payload["open_positions_count"], int)
    assert isinstance(payload["issues"], list)
    if payload["issues"]:
        assert {"key", "label", "severity", "detail", "tickers"}.issubset(payload["issues"][0])
