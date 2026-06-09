from datetime import UTC, datetime, timedelta

from app.schemas import (
    AppSettings,
    BreadthPoint,
    BreadthResponse,
    Job,
    KpiCard,
    MarketOverviewResponse,
    PortfolioPosition,
    PortfolioSnapshotResponse,
    SellEvaluateResponse,
    SellMetricsResponse,
    SellRankingRow,
    SellSignal,
    SettingsPatch,
)


def get_market_overview() -> MarketOverviewResponse:
    return MarketOverviewResponse(
        as_of="2026-06-05",
        source="synthetic_fixture",
        data_status="fallback",
        message="Synthetische Fixture-Daten. Price-Refresh und Market-Breadth-Job ausführen, um echte Snapshots zu sehen.",
        phase="gruen",
        phase_label="Grün",
        action="Konstruktiv bleiben, aber neue Käufe nur bei hoher Qualität.",
        warning_count=3,
        breadth_mode="wachsam",
        volatility_regime="Neutral",
        kpis=[
            KpiCard(label="S&P 500", value="+0.8%", detail="5 Tage", tone="good"),
            KpiCard(label="Nasdaq", value="+1.4%", detail="5 Tage", tone="good"),
            KpiCard(label="Russell 2000", value="-0.6%", detail="5 Tage", tone="warning"),
            KpiCard(label="VIX", value="16.8", detail="ruhiges Band", tone="neutral"),
        ],
    )


def get_breadth() -> BreadthResponse:
    base = datetime(2026, 5, 26, tzinfo=UTC)
    points = [
        BreadthPoint(
            date=(base + timedelta(days=i)).date().isoformat(),
            advancers=580 + i * 14,
            decliners=430 - i * 8,
            ad_line=10200 + i * 95,
            mcclellan=-12 + i * 4.5,
            pct_above_50sma=48 + i * 1.2,
            pct_above_200sma=42 + i * 0.7,
        )
        for i in range(10)
    ]
    return BreadthResponse(
        as_of=points[-1].date,
        universe="us_common_stocks_v3",
        source="synthetic_fixture",
        data_status="fallback",
        message="Synthetische Fixture-Daten. refresh_prices und refresh_breadth ausführen, um echte Breitenwerte zu berechnen.",
        coverage_ratio=0.86,
        points=points,
    )


def get_portfolio_positions() -> list[PortfolioPosition]:
    return [
        PortfolioPosition(
            ticker="NVDA",
            name="NVIDIA",
            shares=12,
            entry_price=91.2,
            current_price=126.8,
            market_value=1521.6,
            pnl_pct=39.0,
            weight_pct=13.4,
            atr_pct=3.8,
            beta=1.72,
            status="watch",
        ),
        PortfolioPosition(
            ticker="MSFT",
            name="Microsoft",
            shares=6,
            entry_price=382.1,
            current_price=449.4,
            market_value=2696.4,
            pnl_pct=17.6,
            weight_pct=23.8,
            atr_pct=1.9,
            beta=0.94,
            status="ok",
        ),
        PortfolioPosition(
            ticker="PLTR",
            name="Palantir",
            shares=30,
            entry_price=66.5,
            current_price=58.9,
            market_value=1767.0,
            pnl_pct=-11.4,
            weight_pct=15.6,
            atr_pct=5.7,
            beta=2.08,
            status="sell",
        ),
        PortfolioPosition(
            ticker="LLY",
            name="Eli Lilly",
            shares=2,
            entry_price=718.0,
            current_price=803.5,
            market_value=1607.0,
            pnl_pct=11.9,
            weight_pct=14.2,
            atr_pct=2.2,
            beta=0.72,
            status="ok",
        ),
    ]


def get_portfolio_snapshot() -> PortfolioSnapshotResponse:
    positions = get_portfolio_positions()
    invested = sum(row.market_value for row in positions)
    cash = 1760.0
    total = invested + cash
    return PortfolioSnapshotResponse(
        as_of="2026-06-08T17:00:00Z",
        total_value=total,
        invested_value=invested,
        cash_balance=cash,
        cash_ratio_pct=cash / total * 100,
        portfolio_atr_pct=3.08,
        beta_balancer=1.42,
        max_depot_loss_pct=8.7,
        kpis=[
            KpiCard(label="Depotwert", value=f"{total:,.0f} EUR", detail="inkl. Cash", tone="neutral"),
            KpiCard(label="Investiert", value=f"{invested:,.0f} EUR", detail="4 Positionen", tone="good"),
            KpiCard(label="Max. Depotverlust", value="8.7%", detail="im Zielkorridor", tone="good"),
            KpiCard(label="Portfolio ATR", value="3.08%", detail="offensiv", tone="warning"),
        ],
        positions=positions,
    )


def get_sell_ranking() -> list[SellRankingRow]:
    return [
        SellRankingRow(
            ticker="PLTR",
            name="Palantir",
            pnl_pct=-11.4,
            health_score=31,
            recommendation_pct=50,
            status="Verkaufen",
            reason="P&L < -7%, Kurs unter 50-SMA, RS schwach",
        ),
        SellRankingRow(
            ticker="NVDA",
            name="NVIDIA",
            pnl_pct=39.0,
            health_score=62,
            recommendation_pct=25,
            status="Beobachten",
            reason="Gewinnzone erreicht, Abstand zur 21-EMA erhöht",
        ),
        SellRankingRow(
            ticker="MSFT",
            name="Microsoft",
            pnl_pct=17.6,
            health_score=81,
            recommendation_pct=0,
            status="Halten",
            reason="Trend intakt, RS stabil",
        ),
    ]


def get_sell_metrics(ticker: str) -> SellMetricsResponse:
    clean = ticker.upper()
    bearish = clean == "PLTR"
    return SellMetricsResponse(
        ticker=clean,
        as_of="2026-06-08",
        current_price=58.9 if bearish else 126.8,
        pnl_pct=-11.4 if bearish else 39.0,
        ema21=62.4 if bearish else 119.2,
        sma50=65.1 if bearish else 111.7,
        sma200=49.8 if bearish else 88.5,
        atr14=3.35 if bearish else 4.8,
        days_under_ema21=5 if bearish else 0,
        distribution_days_25=5 if bearish else 2,
        rs_trend="runter" if bearish else "hoch",
    )


def evaluate_sell_dummy(ticker: str) -> SellEvaluateResponse:
    clean = ticker.upper()
    if clean == "PLTR":
        return SellEvaluateResponse(
            ticker=clean,
            recommendation_label="TEILVERKAUF",
            sell_now_percent=50,
            pending_status="scharf",
            explanation_short="Defensive Reduktion wegen Verlustschwelle und Trendbruch.",
            signals=[
                SellSignal(id="loss_limit", label="Notbremse-Verlustzone", contribution_percent=50, severity="tranche"),
                SellSignal(id="under_sma50", label="Kurs unter 50-SMA", contribution_percent=25, severity="tranche"),
            ],
        )
    return SellEvaluateResponse(
        ticker=clean,
        recommendation_label="HALTEN",
        sell_now_percent=0,
        pending_status="halten",
        explanation_short="Keine aktiven Verkaufsregeln. Position halten.",
        signals=[SellSignal(id="trend_ok", label="Trend intakt", contribution_percent=0, severity="watch")],
    )


def get_jobs() -> list[Job]:
    now = datetime.now(UTC)
    return [
        Job(
            job_id="job_refresh_prices_001",
            job_type="refresh_prices",
            status="done",
            progress=100,
            current_step="Abgeschlossen",
            requested_by="scheduler",
            created_at=now - timedelta(hours=2),
            requested_at=now - timedelta(hours=2),
            started_at=now - timedelta(hours=2, minutes=-1),
            finished_at=now - timedelta(hours=1, minutes=45),
            result={"rows_written": 18420, "coverage": 0.86},
        ),
        Job(
            job_id="job_sell_rank_002",
            job_type="sell_ranking",
            status="running",
            progress=42,
            current_step="Positionen auswerten",
            requested_by="api",
            created_at=now - timedelta(minutes=4),
            requested_at=now - timedelta(minutes=4),
            started_at=now - timedelta(minutes=3),
        ),
    ]


def get_job(job_id: str) -> Job | None:
    return next((job for job in get_jobs() if job.job_id == job_id), None)


_settings = AppSettings(
    atr_threshold=1.5,
    position_monitor_enabled=False,
    position_monitor_interval_minutes=5,
    rs_rating_source="csv_latest",
    data_jobs_enabled=True,
)


def get_settings_dummy() -> AppSettings:
    return _settings.model_copy()


def update_settings_dummy(payload: SettingsPatch) -> AppSettings:
    values = _settings.model_dump()
    updates = payload.model_dump(exclude_none=True)
    values.update(updates)
    return AppSettings(**values)
