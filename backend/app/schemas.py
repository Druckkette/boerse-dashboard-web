from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str
    version: str


class ServiceFreshness(BaseModel):
    name: str
    status: Literal["fresh", "stale", "missing"]
    as_of: str
    lag_minutes: int


class FreshnessResponse(BaseModel):
    generated_at: datetime
    services: list[ServiceFreshness]


class KpiCard(BaseModel):
    label: str
    value: str
    detail: str
    tone: Literal["good", "neutral", "warning", "bad"]


class MarketTrendAmpel(BaseModel):
    ticker: str
    as_of: str
    phase: Literal["rot", "gelb", "gruen", "aufwaertstrend", "neutral"]
    phase_label: str
    close: float | None = None
    anchor_date: str | None = None
    floor_mark: float | None = None
    startschuss_low: float | None = None
    startschuss_bonus: bool | None = None
    dist_count_25: int = 0
    source: Literal["database", "missing", "synthetic_fixture"] = "database"


class MarketOverviewResponse(BaseModel):
    as_of: str
    source: Literal["database", "synthetic_fixture", "missing"]
    data_status: Literal["fresh", "stale", "missing", "fallback"]
    message: str = ""
    phase: Literal["rot", "gelb", "gruen", "aufwaertstrend", "neutral"]
    phase_label: str
    action: str
    warning_count: int
    breadth_mode: Literal["schutz", "wachsam", "rueckenwind"]
    volatility_regime: str
    trend_ampel: MarketTrendAmpel | None = None
    kpis: list[KpiCard]


class BreadthPoint(BaseModel):
    date: str
    advancers: int
    decliners: int
    ad_line: float
    mcclellan: float
    pct_above_50sma: float
    pct_above_200sma: float


class BreadthResponse(BaseModel):
    as_of: str
    universe: str
    source: Literal["database", "synthetic_fixture", "missing"]
    data_status: Literal["fresh", "stale", "missing", "fallback"]
    message: str = ""
    coverage_ratio: float
    points: list[BreadthPoint]


class VolatilityStatusCard(BaseModel):
    title: str
    status: str
    detail: str
    tone: Literal["good", "neutral", "warning", "bad"]


class VolatilityPoint(BaseModel):
    date: str
    spx_close: float | None = None
    spx_ret_5d: float | None = None
    vix_close: float | None = None
    vix_ret_5d: float | None = None
    vix_pct_rank_252: float | None = None
    vix_regime: str
    vixy_close: float | None = None
    vixy_ret_5d: float | None = None
    vixy_state: str
    vixy_stress_confirmation: bool
    vixy_carry_decay: bool
    vol_regime: str
    fragile_rally: bool


class VolatilityResponse(BaseModel):
    as_of: str
    source: Literal["database", "missing"]
    regime: str
    status_cards: list[VolatilityStatusCard]
    points: list[VolatilityPoint]


class SectorRankingRow(BaseModel):
    ticker: str
    name: str
    rank: int
    return_pct: float
    return_1d_pct: float | None = None
    return_5d_pct: float | None = None
    return_20d_pct: float | None = None


class SectorRankingPoint(BaseModel):
    date: str
    ticker: str
    name: str
    rank: int
    return_pct: float


class SectorRankingResponse(BaseModel):
    as_of: str
    source: Literal["database", "missing", "synthetic_fixture"]
    data_status: Literal["fresh", "stale", "missing", "fallback"]
    mode: Literal["daily", "weekly"]
    message: str = ""
    rows: list[SectorRankingRow]
    top: list[SectorRankingRow]
    bottom: list[SectorRankingRow]
    history: list[SectorRankingPoint]


class PriceBarPoint(BaseModel):
    date: str
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float
    adj_close: float | None = None
    volume: float | None = None


class PriceHistoryResponse(BaseModel):
    ticker: str
    name: str = ""
    currency: str = "USD"
    range: Literal["1m", "3m", "6m", "1y", "2y", "5y"]
    source: Literal["database", "synthetic_fallback"]
    data_status: Literal["fresh", "stale", "missing", "fallback"]
    as_of: str
    first_date: str | None = None
    last_date: str | None = None
    last_close: float | None = None
    change_pct: float | None = None
    points: list[PriceBarPoint]


class RsRatingItem(BaseModel):
    ticker: str
    name: str = ""
    date: str
    rating: int | None = Field(default=None, ge=1, le=99)
    score: float | None = None
    percentile: float | None = Field(default=None, ge=0, le=100)
    method: str = ""
    source: str = ""
    universe_size: int = 0
    ret_1m: float | None = None
    ret_3m: float | None = None
    ret_6m: float | None = None
    ret_12m: float | None = None
    excess_return_3m: float | None = None
    excess_return_6m: float | None = None
    excess_return_12m: float | None = None
    near_high_52w: bool | None = None
    new_high_52w: bool | None = None


class RsRatingRankingResponse(BaseModel):
    as_of: str
    source: Literal["database", "missing"]
    rows: list[RsRatingItem]


class RsRatingDetailResponse(BaseModel):
    found: bool
    source: Literal["database", "missing"]
    item: RsRatingItem | None = None


class StockAssessmentCheck(BaseModel):
    category: Literal["fundamental", "technical", "trend", "risk"]
    label: str
    passed: bool
    detail: str
    severity: Literal["info", "warning", "critical"] = "info"


class StockAssessmentSignal(BaseModel):
    category: Literal["positive", "negative", "neutral"]
    label: str
    detail: str = ""


class StockAssessmentScores(BaseModel):
    overall: int = Field(ge=0, le=100)
    technical: float = Field(ge=0, le=100)
    fundamental: float = Field(ge=0, le=100)
    moving_averages: float = Field(ge=0, le=100)
    chart_behavior: int = Field(ge=0, le=100)


class StockAssessmentMetrics(BaseModel):
    last_close: float | None = None
    change_pct: float | None = None
    atr_pct: float | None = None
    volume_ratio_50d: float | None = None
    dollar_volume_mio: float | None = None
    cmf_20: float | None = None
    drawdown_52w_pct: float | None = None
    distance_sma10_pct: float | None = None
    distance_ema21_pct: float | None = None
    distance_sma50_pct: float | None = None
    distance_sma200_pct: float | None = None
    rs_rating: int | None = Field(default=None, ge=1, le=99)
    rs_percentile: float | None = Field(default=None, ge=0, le=100)


class StockAssessmentResponse(BaseModel):
    ticker: str
    as_of: str
    source: Literal["database", "missing"]
    data_status: Literal["fresh", "stale", "missing"]
    message: str
    verdict_label: str
    verdict_tone: Literal["good", "neutral", "warning", "bad"]
    verdict_text: str
    fundamentals_available: bool
    scores: StockAssessmentScores
    metrics: StockAssessmentMetrics
    checks: list[StockAssessmentCheck]
    chart_signals: list[StockAssessmentSignal]
    drivers: list[str]
    warnings: list[str]


class Institutional13FTrendItem(BaseModel):
    ticker: str
    cusip: str
    report_period: str
    previous_period: str | None = None
    holder_count: int
    previous_holder_count: int | None = None
    holder_count_delta: int | None = None
    large_holder_count: int | None = None
    previous_large_holder_count: int | None = None
    large_holder_delta: int | None = None
    total_value_usd: float | None = None
    previous_total_value_usd: float | None = None
    total_value_delta_pct: float | None = None
    total_shares: float | None = None
    previous_total_shares: float | None = None
    total_shares_delta_pct: float | None = None
    trend: Literal["positive", "negative", "neutral", "new", "missing"] = "missing"
    source_url: str = ""


class Institutional13FTrendResponse(BaseModel):
    ticker: str
    source: Literal["database", "missing"]
    as_of: str
    item: Institutional13FTrendItem | None = None


class Institutional13FRankingResponse(BaseModel):
    source: Literal["database", "missing"]
    as_of: str
    rows: list[Institutional13FTrendItem]


class PortfolioPosition(BaseModel):
    ticker: str
    name: str
    shares: float
    entry_price: float
    current_price: float
    market_value: float
    pnl_pct: float
    weight_pct: float
    atr_pct: float
    beta: float
    status: Literal["ok", "watch", "risk", "sell"]
    pnl_abs: float = 0
    currency: str = "EUR"
    buy_date: str | None = None
    pivot_tag: str | None = None
    stop_pct: float | None = None
    stop_price: float | None = None
    broker: str = ""
    account: str = ""
    note: str = ""


class PortfolioPositionsResponse(BaseModel):
    positions: list[PortfolioPosition]


class PortfolioPositionWriteRequest(BaseModel):
    ticker: str
    name: str = ""
    shares: float = Field(gt=0)
    entry_price: float = Field(gt=0)
    current_price: float | None = Field(default=None, gt=0)
    currency: str = "EUR"
    buy_date: str | None = None
    pivot_tag: str | None = None
    stop_pct: float | None = Field(default=7.0, gt=0, le=50)
    broker: str = ""
    account: str = ""
    note: str = ""
    record_transaction: bool = True


class PortfolioPositionWriteResponse(BaseModel):
    position: PortfolioPosition


class PortfolioPositionDeleteResponse(BaseModel):
    ticker: str
    closed: bool


class PortfolioTransaction(BaseModel):
    id: str
    ticker: str
    date: str
    transaction_type: Literal["buy", "sell", "fee", "dividend", "interest", "tax", "other"] | str
    shares: float
    price: float | None = None
    fees: float = 0
    tax: float = 0
    gross_amount: float | None = None
    net_amount: float | None = None
    currency: str = "EUR"
    broker: str = ""
    external_id: str = ""


class PortfolioTransactionsResponse(BaseModel):
    transactions: list[PortfolioTransaction]


class PortfolioSellRequest(BaseModel):
    shares: float = Field(gt=0)
    price: float = Field(gt=0)
    date: str | None = None
    currency: str = "EUR"
    fees: float = 0
    tax: float = 0
    note: str = ""


class PortfolioSellResponse(BaseModel):
    ticker: str
    remaining_position: PortfolioPosition | None = None
    transaction: PortfolioTransaction
    cash_balance: float


class PortfolioCashFlow(BaseModel):
    id: str
    date: str
    amount: float
    flow_type: Literal["deposit", "withdrawal", "dividend", "interest", "tax", "fee", "other"] | str
    currency: str = "EUR"
    broker: str = ""
    note: str = ""


class PortfolioCashFlowRequest(BaseModel):
    date: str | None = None
    amount: float = Field(gt=0)
    flow_type: Literal["deposit", "withdrawal", "dividend", "interest", "tax", "fee", "other"]
    currency: str = "EUR"
    broker: str = ""
    note: str = ""


class PortfolioCashFlowResponse(BaseModel):
    cash_flow: PortfolioCashFlow
    cash_balance: float


class PortfolioCashFlowsResponse(BaseModel):
    cash_flows: list[PortfolioCashFlow]
    cash_balance: float


class PortfolioImportHistoryItem(BaseModel):
    id: str
    source: str
    file_name: str
    status: str
    rows_total: int
    rows_imported: int
    error_message: str = ""
    created_at: datetime
    finished_at: datetime | None = None


class PortfolioImportHistoryResponse(BaseModel):
    imports: list[PortfolioImportHistoryItem]


class PortfolioImportRow(BaseModel):
    ticker: str
    name: str = ""
    shares: float
    entry_price: float
    current_price: float | None = None
    currency: str = "EUR"
    buy_date: str | None = None
    broker: str = ""
    account: str = ""
    note: str = ""
    warnings: list[str] = Field(default_factory=list)


class PortfolioImportRequest(BaseModel):
    source: str = "csv_positions"
    file_name: str = "positions.csv"
    content: str
    dry_run: bool = True
    replace_open_positions: bool = False


class PortfolioImportResponse(BaseModel):
    ok: bool
    dry_run: bool
    import_id: str | None = None
    rows_total: int
    rows_imported: int
    positions: list[PortfolioImportRow]
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class PortfolioSnapshotResponse(BaseModel):
    as_of: str
    total_value: float
    invested_value: float
    cash_balance: float
    cash_ratio_pct: float
    portfolio_atr_pct: float
    beta_balancer: float
    max_depot_loss_pct: float
    kpis: list[KpiCard]
    positions: list[PortfolioPosition]


class SellRankingRow(BaseModel):
    ticker: str
    name: str
    pnl_pct: float
    health_score: float
    recommendation_pct: int
    status: Literal["Halten", "Beobachten", "Verkaufen"]
    reason: str


class SellRankingResponse(BaseModel):
    rows: list[SellRankingRow]


class SellMetricsResponse(BaseModel):
    ticker: str
    as_of: str
    current_price: float
    pnl_pct: float
    ema21: float
    sma50: float
    sma200: float
    atr14: float
    days_under_ema21: int
    distribution_days_25: int
    rs_trend: Literal["hoch", "seitwaerts", "runter"]


class SellSignal(BaseModel):
    id: str
    label: str
    contribution_percent: int
    severity: Literal["watch", "tranche", "killer"]


class SellEvaluateResponse(BaseModel):
    ticker: str
    recommendation_label: Literal["HALTEN", "TEILVERKAUF", "KOMPLETTVERKAUF"]
    sell_now_percent: int
    pending_status: Literal["halten", "in_bestaetigung", "snoozed", "scharf"]
    explanation_short: str
    signals: list[SellSignal]


JobStatus = Literal["queued", "running", "done", "failed", "skipped", "cancelled"]
JobType = Literal[
    "refresh_prices",
    "refresh_breadth",
    "refresh_relative_strength",
    "refresh_sec13f",
    "position_atr_monitor",
]


class Job(BaseModel):
    job_id: str
    celery_task_id: str = ""
    job_type: JobType | str
    status: JobStatus
    progress: int = Field(ge=0, le=100)
    current_step: str
    message: str = ""
    error_message: str = ""
    requested_by: str
    payload: dict = Field(default_factory=dict)
    created_at: datetime
    requested_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    result: dict = Field(default_factory=dict)


class JobListResponse(BaseModel):
    jobs: list[Job]


class JobDetailResponse(BaseModel):
    job: Job


class JobCreateRequest(BaseModel):
    type: JobType
    payload: dict = Field(default_factory=dict)
    requested_by: str = "api"


class JobCreateResponse(BaseModel):
    job: Job


class JobCancelResponse(BaseModel):
    job: Job
    cancelled: bool


class AppSettings(BaseModel):
    atr_threshold: float
    position_monitor_enabled: bool
    position_monitor_interval_minutes: int
    position_monitor_threshold_atr: float = 1.5
    position_monitor_atr_period: int = 21
    position_monitor_lookback_days: int = 120
    position_monitor_cooldown_hours: int = 12
    position_monitor_reference: Literal["high_since_buy", "close_since_buy", "entry_price"] = "high_since_buy"
    pushover_enabled: bool = False
    pushover_configured: bool = False
    rs_rating_source: Literal["csv_latest", "computed"]
    data_jobs_enabled: bool


class SettingsPatch(BaseModel):
    atr_threshold: float | None = None
    position_monitor_enabled: bool | None = None
    position_monitor_interval_minutes: int | None = None
    position_monitor_threshold_atr: float | None = None
    position_monitor_atr_period: int | None = None
    position_monitor_lookback_days: int | None = None
    position_monitor_cooldown_hours: int | None = None
    position_monitor_reference: Literal["high_since_buy", "close_since_buy", "entry_price"] | None = None
    pushover_enabled: bool | None = None
    rs_rating_source: Literal["csv_latest", "computed"] | None = None
    data_jobs_enabled: bool | None = None
