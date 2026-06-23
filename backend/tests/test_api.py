from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.main import app
from app.schemas import (
    BuyStrengthAssessmentResponse,
    BuyStrengthCheck,
    BuyStrengthOverviewResponse,
    BuyStrengthSummaryItem,
    FreshnessResponse,
    PortfolioPosition,
    PortfolioPositionWriteResponse,
    ServiceFreshness,
    SetupStatusResponse,
    SetupStep,
    SystemReadinessCheck,
    SystemReadinessResponse,
)


client = TestClient(app)


def test_health() -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_readiness_contract(monkeypatch) -> None:
    from app.api.v1 import health as health_api

    def fake_readiness() -> SystemReadinessResponse:
        return SystemReadinessResponse(
            status="degraded",
            generated_at=datetime.now(UTC),
            checks=[
                SystemReadinessCheck(
                    name="database",
                    status="ok",
                    required=True,
                    detail="Postgres-Verbindung ist erreichbar.",
                    latency_ms=4,
                    metadata={"dialect": "postgresql"},
                ),
                SystemReadinessCheck(
                    name="migrations",
                    status="ok",
                    required=True,
                    detail="Datenbankschema ist auf Alembic Head.",
                    latency_ms=2,
                    metadata={"current_revision": "0005", "head_revision": "0005"},
                ),
                SystemReadinessCheck(
                    name="redis",
                    status="warning",
                    required=False,
                    detail="Redis nicht erreichbar; API läuft weiter.",
                    latency_ms=1,
                ),
            ],
        )

    monkeypatch.setattr(health_api, "get_system_readiness", fake_readiness)

    response = client.get("/api/v1/readiness")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "degraded"
    assert {"database", "migrations", "redis"} == {check["name"] for check in payload["checks"]}


def test_freshness_contract(monkeypatch) -> None:
    from app.api.v1 import health as health_api

    def fake_freshness() -> FreshnessResponse:
        return FreshnessResponse(
            generated_at=datetime.now(UTC),
            services=[
                ServiceFreshness(name="prices", status="fresh", as_of="2026-06-12", lag_minutes=45),
                ServiceFreshness(name="market_breadth", status="missing", as_of="", lag_minutes=0),
            ],
        )

    monkeypatch.setattr(health_api, "get_freshness", fake_freshness)

    response = client.get("/api/v1/freshness")

    assert response.status_code == 200
    payload = response.json()
    assert payload["services"][0]["name"] == "prices"
    assert payload["services"][0]["status"] == "fresh"
    assert payload["services"][1]["status"] == "missing"


def test_setup_status_contract(monkeypatch) -> None:
    from app.api.v1 import setup as setup_api

    def fake_setup_status() -> SetupStatusResponse:
        return SetupStatusResponse(
            as_of=datetime.now(UTC),
            status="needs_action",
            summary="Nächster Schritt: Kursdaten.",
            next_step_key="prices",
            steps=[
                SetupStep(
                    key="portfolio",
                    label="Depot",
                    status="complete",
                    detail="2 offene Positionen sind gespeichert.",
                    href="/portfolio",
                    action_label="Depot öffnen",
                ),
                SetupStep(
                    key="prices",
                    label="Kursdaten",
                    status="pending",
                    detail="Noch kein Price-Cache vorhanden.",
                    job_type="refresh_prices",
                    job_payload={"mode": "manual", "range": "1y", "preset": "all"},
                    action_label="Kurse laden",
                ),
            ],
        )

    monkeypatch.setattr(setup_api, "get_setup_status", fake_setup_status)

    response = client.get("/api/v1/setup/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "needs_action"
    assert payload["next_step_key"] == "prices"
    assert payload["steps"][1]["job_type"] == "refresh_prices"
    assert payload["steps"][1]["job_payload"]["range"] == "1y"


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


def test_market_ampel_contract() -> None:
    response = client.get("/api/v1/market/ampel?ticker=SPY&days=90")
    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] in {"database", "missing"}
    assert payload["data_status"] in {"fresh", "stale", "missing", "fallback"}
    assert payload["ticker"] == "^GSPC"
    assert {"mode", "tone", "action", "reasons"}.issubset(payload["hero"])
    assert {"phase", "label", "reason", "action", "tone"}.issubset(payload["phase_info"])
    assert isinstance(payload["lights"], list)
    assert isinstance(payload["change_cards"], list)
    assert isinstance(payload["distance_tiles"], list)
    assert isinstance(payload["warning_checks"], list)
    assert isinstance(payload["chart_points"], list)
    if payload["chart_points"]:
        assert {
            "ema21_held",
            "sma50_held",
            "sma200_held",
            "up_vol_declining",
            "vol_sma50",
            "dist_52w_pct",
            "consec_low_above_21",
            "consec_low_above_50",
            "consec_low_above_200",
        }.issubset(payload["chart_points"][0])


def test_market_ampel_etf_aliases_map_to_streamlit_indexes() -> None:
    nasdaq = client.get("/api/v1/market/ampel?ticker=QQQ&days=90")
    russell = client.get("/api/v1/market/ampel?ticker=IWM&days=90")

    assert nasdaq.status_code == 200
    assert russell.status_code == 200
    assert nasdaq.json()["ticker"] == "^IXIC"
    assert russell.json()["ticker"] == "^RUT"


def test_market_breadth_contract() -> None:
    response = client.get("/api/v1/market/breadth")
    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] in {"database", "synthetic_fixture", "missing"}
    assert payload["data_status"] in {"fresh", "stale", "missing", "fallback"}
    assert isinstance(payload["coverage_ratio"], int | float)
    assert isinstance(payload["loaded_universe"], int)
    assert isinstance(payload["daily_covered_count"], int)
    assert isinstance(payload["valid_for_50sma"], int)
    assert isinstance(payload["valid_for_200sma"], int)
    assert isinstance(payload["nhnl_uses_intraday"], bool)
    assert isinstance(payload["points"], list)
    if payload["points"]:
        assert {"date", "advancers", "decliners", "pct_above_50sma", "new_highs", "new_lows"}.issubset(payload["points"][0])


def test_market_breadth_overview_contract() -> None:
    response = client.get("/api/v1/market/breadth-overview")
    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] in {"database", "missing"}
    assert payload["data_status"] in {"fresh", "stale", "missing"}
    assert isinstance(payload["coverage_ratio"], int | float)
    assert isinstance(payload["loaded_universe"], int)
    assert isinstance(payload["signals"], list)
    assert isinstance(payload["points"], list)
    if payload["signals"]:
        assert {"key", "title", "value", "detail", "tone", "comment", "metrics"}.issubset(payload["signals"][0])
    if payload["points"]:
        assert {
            "date",
            "advancers",
            "decliners",
            "advance_decline_ratio",
            "ad_line",
            "mcclellan",
            "new_highs",
            "new_lows",
            "nh_nl_ratio",
            "pct_above_50sma",
            "up_down_volume_ratio",
            "deemer_ratio",
        }.issubset(payload["points"][0])


def test_market_deep_analysis_contract() -> None:
    response = client.get("/api/v1/market/deep-analysis")
    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] in {"database", "missing"}
    assert payload["data_status"] in {"fresh", "stale", "missing"}
    assert isinstance(payload["coverage_ratio"], int | float)
    assert isinstance(payload["loaded_universe"], int)
    assert isinstance(payload["daily_covered_count"], int)
    assert isinstance(payload["valid_for_50sma"], int)
    assert isinstance(payload["valid_for_200sma"], int)
    assert isinstance(payload["nhnl_uses_intraday"], bool)
    assert isinstance(payload["metrics"], list)
    assert isinstance(payload["checks"], list)
    assert isinstance(payload["points"], list)
    if payload["metrics"]:
        assert {"label", "value", "detail", "tone"}.issubset(payload["metrics"][0])
    if payload["checks"]:
        assert {"label", "passed", "detail", "tone"}.issubset(payload["checks"][0])


def test_market_universe_contract() -> None:
    response = client.get("/api/v1/market/universe")
    assert response.status_code == 200
    payload = response.json()
    assert payload["key"]
    assert isinstance(payload["member_count"], int)
    assert isinstance(payload["sample_tickers"], list)
    assert isinstance(payload["metadata"], dict)


def test_market_universe_mappings_contract() -> None:
    response = client.get("/api/v1/market/universe/mappings")
    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] in {"database", "fallback", "missing"}
    assert payload["universe_key"]
    assert isinstance(payload["member_count"], int)
    assert isinstance(payload["mapped_count"], int)
    assert isinstance(payload["ignored_count"], int)
    assert isinstance(payload["unmapped_count"], int)
    assert isinstance(payload["mappings"], list)
    assert isinstance(payload["unmapped_sample"], list)


def test_patch_market_universe_mapping_contract(monkeypatch) -> None:
    from app.api.v1 import market as market_api
    from app.schemas import UniverseSymbolMappingReviewResponse

    def fake_update(request):
        return UniverseSymbolMappingReviewResponse(
            source="database",
            as_of="2026-06-12",
            universe_key=request.universe_key,
            member_count=1,
            mapped_count=1,
            ignored_count=0,
            unmapped_count=0,
            mappings=[],
            unmapped_sample=[],
        )

    monkeypatch.setattr(market_api, "update_universe_symbol_mapping", fake_update)

    response = client.patch(
        "/api/v1/market/universe/mappings",
        json={"source_ticker": "BRK-B", "yahoo_symbol": "BRK-B", "status": "active"},
    )

    assert response.status_code == 200
    assert response.json()["mapped_count"] == 1


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
                institutional_13f_holders=None,
                next_earnings_date=None,
                beta=None,
                eps_quarter_history=request.eps_quarter_history,
                annual_eps_history=request.annual_eps_history,
                revenue_quarter_history=request.revenue_quarter_history,
                annual_revenue_history=request.annual_revenue_history,
                roe_history=request.roe_history,
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
            "eps_quarter_history": [
                {
                    "fiscal_period": "2026 Q1",
                    "eps_current_quarter": 2.4,
                    "eps_same_quarter_last_year": 1.5,
                    "eps_growth_yoy_pct": 60.0,
                },
                {
                    "fiscal_period": "2025 Q4",
                    "eps_current_quarter": 2.1,
                    "eps_same_quarter_last_year": 1.4,
                    "eps_growth_yoy_pct": 50.0,
                },
                {
                    "fiscal_period": "2025 Q3",
                    "eps_current_quarter": 1.9,
                    "eps_same_quarter_last_year": 1.45,
                    "eps_growth_yoy_pct": 31.0,
                },
            ],
            "annual_eps_history": [
                {
                    "fiscal_year": "2025",
                    "eps_current_year": 7.2,
                    "eps_previous_year": 5.2,
                    "eps_growth_yoy_pct": 38.5,
                }
            ],
            "revenue_quarter_history": [
                {
                    "fiscal_period": "2026 Q1",
                    "revenue_current_quarter": 142.0,
                    "revenue_same_quarter_last_year": 100.0,
                    "revenue_growth_yoy_pct": 42.0,
                }
            ],
            "annual_revenue_history": [
                {
                    "fiscal_year": "2025",
                    "revenue_current_year": 1350.0,
                    "revenue_previous_year": 1000.0,
                    "revenue_growth_yoy_pct": 35.0,
                }
            ],
            "roe_pct": 21.0,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] == "database"
    assert payload["item"]["quarterly_eps_growth_pct"] == 42.0
    assert payload["item"]["eps_quarter_history"][0]["eps_growth_yoy_pct"] == 60.0
    assert payload["item"]["annual_eps_history"][0]["eps_growth_yoy_pct"] == 38.5
    assert payload["item"]["revenue_quarter_history"][0]["revenue_growth_yoy_pct"] == 42.0
    assert payload["item"]["annual_revenue_history"][0]["revenue_growth_yoy_pct"] == 35.0


def test_stock_assessment_ranking_contract() -> None:
    response = client.get("/api/v1/stocks/assessment/ranking?limit=10")
    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] in {"database", "missing"}
    assert isinstance(payload["rows"], list)
    if payload["rows"]:
        assert {"ticker", "overall_score", "technical_score", "verdict_label"}.issubset(payload["rows"][0])


def test_stock_assessment_compare_contract() -> None:
    response = client.get("/api/v1/stocks/assessment/compare?tickers=NVDA,MSFT&limit=12")
    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] in {"database", "partial", "missing"}
    assert payload["requested_tickers"] == ["NVDA", "MSFT"]
    assert isinstance(payload["missing_tickers"], list)
    assert len(payload["rows"]) == 2
    assert {
        "rank",
        "ticker",
        "overall_score",
        "technical_score",
        "fundamental_score",
        "moving_average_score",
        "chart_behavior_score",
        "above_sma50",
        "chart_positive",
    }.issubset(payload["rows"][0])


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


def test_trade_republic_transaction_import_preview_contract(monkeypatch) -> None:
    from datetime import date

    from app.services import portfolio as portfolio_service
    from app.services.fx import FxRate

    monkeypatch.setattr(
        portfolio_service,
        "get_eur_usd_rate",
        lambda: FxRate(pair="EUR/USD", rate=1.0, as_of=date(2026, 1, 1), source="test"),
    )
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


def test_portfolio_buy_strength_contract(monkeypatch) -> None:
    from app.api.v1 import portfolio as portfolio_api

    called: dict[str, int] = {}

    def fake_overview(weeks: int = 3) -> BuyStrengthOverviewResponse:
        called["weeks"] = weeks
        return BuyStrengthOverviewResponse(
            as_of="2026-06-21T10:00:00+00:00",
            window_days=weeks * 7,
            items=[
                BuyStrengthSummaryItem(
                    ticker="NVDA",
                    name="Nvidia",
                    buy_date="2026-06-14",
                    age_days=7,
                    pnl_pct=5.2,
                    current_price=105.2,
                    entry_price=100,
                    checks_passed=6,
                    checks_total=7,
                    warnings_active=1,
                    warnings_total=11,
                    status="stark",
                    status_label="Stark",
                    message="Frischer Kauf bestätigt Stärke.",
                )
            ],
        )

    monkeypatch.setattr(portfolio_api, "get_buy_strength_overview", fake_overview)

    response = client.get("/api/v1/portfolio/buy-strength?weeks=6")
    assert response.status_code == 200
    payload = response.json()
    assert called["weeks"] == 6
    assert payload["window_days"] == 42
    assert payload["items"][0]["ticker"] == "NVDA"
    assert payload["items"][0]["warnings_total"] == 11


def test_portfolio_buy_strength_detail_contract(monkeypatch) -> None:
    from app.api.v1 import portfolio as portfolio_api

    called: dict[str, int] = {}

    def fake_detail(ticker: str, weeks: int = 3) -> BuyStrengthAssessmentResponse:
        called["weeks"] = weeks
        return BuyStrengthAssessmentResponse(
            ticker=ticker.upper(),
            name=ticker.upper(),
            buy_date="2026-06-14",
            age_days=7,
            window_days=weeks * 7,
            source="database",
            data_status="fresh",
            status="watch",
            status_label="Beobachten",
            message="Gemischtes Verhalten nach Kauf.",
            entry_price=100,
            current_price=101,
            pnl_pct=1,
            buy_day_low=98,
            previous_day_low=97,
            latest_close=101,
            latest_price_date="2026-06-21",
            checks=[
                BuyStrengthCheck(
                    key="immediate_strength",
                    label="Unmittelbare Stärke nach Kauf",
                    category="positive",
                    passed=True,
                    tone="good",
                    detail="P&L positiv.",
                )
            ],
            warnings=[
                BuyStrengthCheck(
                    key="rs_declines",
                    label="Relative-Stärke-Linie sinkt",
                    category="warning",
                    passed=False,
                    tone="bad",
                    detail="RS fällt.",
                )
            ],
        )

    monkeypatch.setattr(portfolio_api, "get_buy_strength_assessment", fake_detail)

    response = client.get("/api/v1/portfolio/buy-strength/nvda?weeks=1")
    assert response.status_code == 200
    payload = response.json()
    assert called["weeks"] == 1
    assert payload["ticker"] == "NVDA"
    assert payload["window_days"] == 7
    assert payload["checks"][0]["category"] == "positive"
    assert payload["warnings"][0]["passed"] is False


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


def test_portfolio_stop_update_contract(monkeypatch) -> None:
    from app.api.v1 import portfolio as portfolio_api

    def fake_stop_update(ticker, payload) -> PortfolioPositionWriteResponse:
        return PortfolioPositionWriteResponse(
            position=PortfolioPosition(
                ticker=ticker.upper(),
                name="NVIDIA",
                shares=2,
                entry_price=100,
                current_price=125,
                market_value=250,
                pnl_pct=25,
                weight_pct=100,
                atr_pct=3.2,
                beta=1.4,
                status="ok",
                pnl_abs=50,
                currency="USD",
                stop_pct=None,
                stop_price=payload.stop_price,
            )
        )

    monkeypatch.setattr(portfolio_api, "update_portfolio_position_stop", fake_stop_update)

    response = client.patch("/api/v1/portfolio/positions/nvda/stop", json={"stop_price": 118.5})

    assert response.status_code == 200
    payload = response.json()
    assert payload["position"]["ticker"] == "NVDA"
    assert payload["position"]["stop_price"] == 118.5


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


def test_runtime_config_contract() -> None:
    response = client.get("/api/v1/settings/runtime-config")
    assert response.status_code == 200
    payload = response.json()
    assert "SEC_USER_AGENT" in payload["editable_keys"]
    assert "NEON_DATABASE_URL" in payload["editable_keys"]
    assert "APP_AUTH_ENABLED" in payload["editable_keys"]
    assert "APP_AUTH_USER" in payload["editable_keys"]
    assert "APP_AUTH_PASSWORD" in payload["editable_keys"]
    sec_item = next(item for item in payload["items"] if item["key"] == "SEC_USER_AGENT")
    db_item = next(item for item in payload["items"] if item["key"] == "NEON_DATABASE_URL")
    auth_item = next(item for item in payload["items"] if item["key"] == "APP_AUTH_PASSWORD")
    assert sec_item["editable"] is True
    assert sec_item["runtime_applied"] is True
    assert db_item["editable"] is True
    assert db_item["restart_required"] is True
    assert auth_item["editable"] is True
    assert auth_item["restart_required"] is True


def test_database_target_contract() -> None:
    response = client.get("/api/v1/settings/database-target")
    assert response.status_code == 200
    payload = response.json()
    assert payload["target"] in {"local", "neon"}
    assert payload["running_target"] in {"local", "neon"}
    assert "neon_configured" in payload
    assert "restart_required" in payload


def test_runtime_config_test_endpoint_validates_sec_user_agent() -> None:
    response = client.post(
        "/api/v1/settings/runtime-config/test",
        json={"key": "SEC_USER_AGENT", "value": "boerse-dashboard-web tests@example.com"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["status"] == "ok"


def test_runtime_config_test_endpoint_validates_app_auth_password() -> None:
    response = client.post(
        "/api/v1/settings/runtime-config/test",
        json={"key": "APP_AUTH_PASSWORD", "value": "long-enough-password"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["status"] == "ok"
    assert payload["restart_required"] is True


def test_runtime_config_test_endpoint_uses_fmp_stable_profile(monkeypatch) -> None:
    from app.services import settings as settings_service

    calls: list[dict] = []

    class FakeResponse:
        status_code = 200
        text = '[{"symbol":"AAPL","companyName":"Apple Inc.","currency":"USD"}]'

        def json(self):
            return [{"symbol": "AAPL", "companyName": "Apple Inc.", "currency": "USD"}]

    def fake_get(url, *, params, timeout):
        calls.append({"url": url, "params": params, "timeout": timeout})
        return FakeResponse()

    monkeypatch.setattr(settings_service.requests, "get", fake_get)

    response = client.post(
        "/api/v1/settings/runtime-config/test",
        json={"key": "FMP_API_KEY", "value": "test-fmp-key"},
    )

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert calls == [
        {
            "url": "https://financialmodelingprep.com/stable/profile",
            "params": {"symbol": "AAPL", "apikey": "test-fmp-key"},
            "timeout": 12,
        }
    ]


def test_runtime_config_test_endpoint_returns_fmp_response_body_on_403(monkeypatch) -> None:
    from app.services import settings as settings_service

    class FakeResponse:
        status_code = 403
        text = "Legacy Endpoint"

        def json(self):
            return {"error": "Legacy Endpoint"}

    monkeypatch.setattr(settings_service.requests, "get", lambda *args, **kwargs: FakeResponse())

    response = client.post(
        "/api/v1/settings/runtime-config/test",
        json={"key": "FMP_API_KEY", "value": "test-fmp-key"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is False
    assert payload["status"] == "failed"
    assert "HTTP 403" in payload["detail"]
    assert "Legacy Endpoint" in payload["detail"]


def test_runtime_config_patch_masks_secret() -> None:
    response = client.patch(
        "/api/v1/settings/runtime-config",
        json={"values": {"SEC_USER_AGENT": "boerse-dashboard-web tests@example.com"}},
    )
    assert response.status_code == 200
    payload = response.json()
    sec_item = next(item for item in payload["items"] if item["key"] == "SEC_USER_AGENT")
    assert sec_item["source"] == "database"
    assert sec_item["configured"] is True
    assert "tests@example.com" not in sec_item["value_preview"]
    assert sec_item["value_preview"].startswith("bo")
