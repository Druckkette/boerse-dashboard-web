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


class MarketOverviewResponse(BaseModel):
    as_of: str
    phase: Literal["rot", "gelb", "gruen", "aufwaertstrend", "neutral"]
    phase_label: str
    action: str
    warning_count: int
    breadth_mode: Literal["schutz", "wachsam", "rueckenwind"]
    volatility_regime: str
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
    coverage_ratio: float
    points: list[BreadthPoint]


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


class PortfolioPositionsResponse(BaseModel):
    positions: list[PortfolioPosition]


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
    rs_rating_source: Literal["csv_latest", "computed"]
    data_jobs_enabled: bool


class SettingsPatch(BaseModel):
    atr_threshold: float | None = None
    position_monitor_enabled: bool | None = None
    position_monitor_interval_minutes: int | None = None
    rs_rating_source: Literal["csv_latest", "computed"] | None = None
    data_jobs_enabled: bool | None = None
