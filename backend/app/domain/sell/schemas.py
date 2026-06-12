from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


RecommendationLabel = Literal["HALTEN", "TEILVERKAUF", "KOMPLETTVERKAUF"]
PendingStatus = Literal["halten", "in_bestaetigung", "snoozed", "scharf"]
SellStatus = Literal["Halten", "Beobachten", "Verkaufen"]


class SellManualInput(BaseModel):
    ticker: str = ""
    pivot: float | None = None
    low_day_1: float | None = None
    low_day_0: float | None = None
    market_environment: Literal["Bullisch", "Unsicher", "Bärisch"] = "Unsicher"
    industry_group_status: Literal["Stark", "Neutral", "Schwach"] = "Neutral"
    personality_changed: bool = False
    strength_checkboxes: dict[str, bool] = Field(default_factory=dict)
    warning_checkboxes: dict[str, bool] = Field(default_factory=dict)
    sell_setup: dict[str, Any] = Field(default_factory=dict)


class SellRecommendationState(BaseModel):
    last_seen_date: str = ""
    last_pct: int = 0
    consecutive_days: int = 0
    snoozed_until: str = ""
    snoozed_pct: int = 0


class TrancheLogEntry(BaseModel):
    ticker: str
    date: str = Field(default_factory=lambda: date.today().isoformat())
    pct: float = Field(ge=0, le=100)
    reason: str = ""
    price: float | None = None
    shares: float | None = None
    source: str = "api"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("ticker")
    @classmethod
    def normalize_ticker(cls, value: str) -> str:
        return str(value or "").upper().strip()


class SellMetricsRequest(BaseModel):
    ticker: str
    buy_date: date
    buy_price: float = Field(gt=0)
    shares: float = Field(ge=0)
    current_price: float | None = Field(default=None, gt=0)
    benchmark_ticker: str = "SPY"
    currency: str = "USD"
    pivot_date: date | None = None
    scenario: str | None = None

    @field_validator("ticker", "benchmark_ticker", "currency")
    @classmethod
    def normalize_upper(cls, value: str) -> str:
        return str(value or "").upper().strip()


class SellMetricsPayload(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    ok: bool
    error: str = ""
    ticker: str
    benchmark_ticker: str = "SPY"
    buy_date: str = ""
    pivot_date: str = ""
    buy_price: float | None = None
    shares: float = 0
    currency: str = "USD"
    as_of: str = ""
    benchmark_as_of: str = ""
    metrics: dict[str, Any] = Field(default_factory=dict)
    manual_defaults: dict[str, Any] = Field(default_factory=dict)
    auto_checkboxes: dict[str, Any] = Field(default_factory=dict)
    ohlc_frames: dict[str, Any] = Field(default_factory=dict, exclude=True)


class SellSignal(BaseModel):
    id: str
    label: str
    contribution_percent: int = 0
    signal_date: str = ""
    event_note: str = ""
    sell_mode: str = ""
    sell_style: str = ""
    strategy_key: str = ""
    severity: Literal["watch", "warning", "tranche", "killer"] = "watch"
    book_reference: str = ""


class SellHealthScore(BaseModel):
    health_score: float
    status: SellStatus
    rs_trend: Literal["hoch", "seitwärts", "seitwaerts", "runter"] = "seitwärts"
    reasons: list[str] = Field(default_factory=list)


class SellEvaluationRequest(BaseModel):
    manual: SellManualInput | None = None
    tranche_log: list[TrancheLogEntry] | None = None
    recommendation_state: SellRecommendationState | None = None


class SellEvaluationResponse(BaseModel):
    ticker: str
    recommendation_label: RecommendationLabel
    display_label: str
    regime: str
    sell_now_percent: int
    recommendation_percent: int
    target_total_sold_percent: int
    already_sold_percent: float
    remaining_after_sale_percent: float
    pending_status: PendingStatus
    explanation_short: str
    stop_price: float | None = None
    next_tranche_trigger_price: float | None = None
    full_exit_price: float | None = None
    add_again_condition: str = ""
    sell_mode: str = ""
    sell_style: str = ""
    killer_signals: list[SellSignal] = Field(default_factory=list)
    tranche_signals: list[SellSignal] = Field(default_factory=list)
    warning_signals: list[SellSignal] = Field(default_factory=list)
    watch_signals: list[SellSignal] = Field(default_factory=list)
    book_references: dict[str, str] = Field(default_factory=dict)
    next_recommendation_state: SellRecommendationState
    health: SellHealthScore
    manual: SellManualInput
    tranche_log: list[TrancheLogEntry] = Field(default_factory=list)


class SellPositionRankingItem(BaseModel):
    ticker: str
    name: str
    pnl_pct: float
    health_score: float
    recommendation_pct: int
    status: SellStatus
    reason: str
    pending_status: PendingStatus
    primary_signal: str = ""


class SellMetricsApiResponse(BaseModel):
    ticker: str
    as_of: str
    current_price: float | None = None
    pnl_pct: float | None = None
    ema21: float | None = None
    sma50: float | None = None
    sma200: float | None = None
    atr14: float | None = None
    days_under_ema21: int = 0
    distribution_days_25: int = 0
    rs_trend: Literal["hoch", "seitwaerts", "runter"] = "seitwaerts"
    health: SellHealthScore
    manual_defaults: dict[str, Any] = Field(default_factory=dict)
    auto_checkboxes: dict[str, Any] = Field(default_factory=dict)
    raw_payload: SellMetricsPayload


class SellLiveMonitorMetric(BaseModel):
    key: str
    label: str
    value: str
    detail: str = ""
    tone: Literal["good", "neutral", "warning", "bad"] = "neutral"


class SellStrategyDiagnostic(BaseModel):
    strategy_key: str
    theme: str
    label: str
    status: Literal["clear", "watch", "active"]
    tone: Literal["good", "neutral", "warning", "bad"]
    active_signal_count: int = 0
    watch_signal_count: int = 0
    max_contribution_percent: int = 0
    book_reference: str = ""
    description: str = ""
    signals: list[SellSignal] = Field(default_factory=list)


class SellPostMortemCheck(BaseModel):
    key: str
    label: str
    status: Literal["ok", "review", "fail"]
    tone: Literal["good", "neutral", "warning", "bad"]
    evidence: str


class SellDiagnosticsResponse(BaseModel):
    ticker: str
    as_of: str
    price_context: list[SellLiveMonitorMetric]
    strategy_hub: list[SellStrategyDiagnostic]
    post_mortem: list[SellPostMortemCheck]
    next_action: str


class SellRankingResponse(BaseModel):
    rows: list[SellPositionRankingItem]


class ManualInputResponse(BaseModel):
    manual: SellManualInput


class TrancheLogResponse(BaseModel):
    entry: TrancheLogEntry
    tranche_log: list[TrancheLogEntry]


class SnoozeRequest(BaseModel):
    snoozed_pct: int = Field(ge=0, le=100)
    days: int = Field(default=5, ge=1, le=60)


class SnoozeResponse(BaseModel):
    state: SellRecommendationState


def default_snoozed_until(days: int) -> str:
    return (date.today() + timedelta(days=days)).isoformat()
