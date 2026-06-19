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


class SystemReadinessCheck(BaseModel):
    name: str
    status: Literal["ok", "warning", "error", "unknown"]
    required: bool
    detail: str
    latency_ms: int | None = None
    metadata: dict = Field(default_factory=dict)


class SystemReadinessResponse(BaseModel):
    status: Literal["ready", "degraded", "not_ready"]
    generated_at: datetime
    checks: list[SystemReadinessCheck]


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


class MarketAmpelHero(BaseModel):
    mode: str
    tone: Literal["good", "neutral", "warning", "bad"]
    action: str
    reasons: list[str]


class MarketAmpelLight(BaseModel):
    key: Literal["rot", "gelb", "gruen", "aufwaertstrend"]
    label: str
    active: bool
    rule: str
    tone: Literal["good", "neutral", "warning", "bad"]


class MarketAmpelPhaseInfo(BaseModel):
    phase: Literal["rot", "gelb", "gruen", "aufwaertstrend", "neutral"]
    label: str
    reason: str
    action: str
    tone: Literal["good", "neutral", "warning", "bad"]


class MarketAmpelCycle(BaseModel):
    anchor_date: str | None = None
    floor_mark: float | None = None
    floor_distance_pct: float | None = None
    startschuss_low: float | None = None
    startschuss_distance_pct: float | None = None
    startschuss_bonus: bool | None = None
    ma_order: bool | None = None
    diagnostics: list[str] = Field(default_factory=list)


class MarketAmpelChangeCard(BaseModel):
    title: str
    value: str
    detail: str
    tone: Literal["good", "neutral", "warning", "bad"]
    detail2: str | None = None
    detail3: str | None = None
    arrow: Literal["up", "down", "flat"] | None = None
    quality: str | None = None


class MarketAmpelDistanceTile(BaseModel):
    label: str
    value: str
    indicator: str
    tone: Literal["good", "neutral", "warning", "bad"]
    detail: str


class MarketAmpelWarningCheck(BaseModel):
    label: str
    passed: bool
    detail: str
    active_warning: bool
    tone: Literal["good", "neutral", "warning", "bad"]


class MarketAmpelChartPoint(BaseModel):
    date: str
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    volume: float | None = None
    ema21: float | None = None
    sma10: float | None = None
    sma50: float | None = None
    sma200: float | None = None
    vol_sma50: float | None = None
    dist_52w_pct: float | None = None
    consec_low_above_21: int = 0
    consec_low_above_50: int = 0
    consec_low_above_200: int = 0
    ema21_held: bool = False
    sma50_held: bool = False
    sma200_held: bool = False
    up_vol_declining: bool = False
    phase: Literal["rot", "gelb", "gruen", "aufwaertstrend", "neutral"]
    is_distribution: bool = False
    is_stall: bool = False
    intraday_reversal_down: bool = False
    intraday_reversal_up: bool = False


class MarketAmpelChartMarker(BaseModel):
    key: str
    date: str
    label: str
    value: float | None = None
    color: str


class MarketAmpelResponse(BaseModel):
    as_of: str
    ticker: str
    name: str
    source: Literal["database", "missing"]
    data_status: Literal["fresh", "stale", "missing", "fallback"]
    message: str = ""
    warning_count: int
    breadth_mode: Literal["schutz", "wachsam", "rueckenwind"]
    volatility_regime: str
    vix_regime: str
    hero: MarketAmpelHero
    phase_info: MarketAmpelPhaseInfo
    lights: list[MarketAmpelLight]
    cycle: MarketAmpelCycle
    change_cards: list[MarketAmpelChangeCard]
    distance_tiles: list[MarketAmpelDistanceTile]
    warning_checks: list[MarketAmpelWarningCheck]
    chart_points: list[MarketAmpelChartPoint]
    chart_markers: list[MarketAmpelChartMarker]


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
    new_highs: int = 0
    new_lows: int = 0


class MarketDeepAnalysisMetric(BaseModel):
    label: str
    value: str
    detail: str
    tone: Literal["good", "neutral", "warning", "bad"]


class MarketDeepAnalysisCheck(BaseModel):
    label: str
    passed: bool
    detail: str
    tone: Literal["good", "neutral", "warning", "bad"]


class MarketDeepAnalysisPoint(BaseModel):
    date: str
    ad_line: float | None = None
    mcclellan: float | None = None
    new_highs: int = 0
    new_lows: int = 0
    nh_nl_ratio: float | None = None
    pct_above_50sma: float | None = None
    pct_above_200sma: float | None = None
    deemer_ratio: float | None = None


class MarketDeepAnalysisResponse(BaseModel):
    as_of: str
    source: Literal["database", "missing"]
    data_status: Literal["fresh", "stale", "missing"]
    message: str = ""
    universe: str
    coverage_ratio: float
    loaded_universe: int = 0
    requested_universe: int | None = None
    daily_covered_count: int = 0
    valid_for_50sma: int = 0
    valid_for_200sma: int = 0
    nhnl_uses_intraday: bool = False
    metrics: list[MarketDeepAnalysisMetric]
    checks: list[MarketDeepAnalysisCheck]
    points: list[MarketDeepAnalysisPoint]


class BreadthResponse(BaseModel):
    as_of: str
    universe: str
    source: Literal["database", "synthetic_fixture", "missing"]
    data_status: Literal["fresh", "stale", "missing", "fallback"]
    message: str = ""
    coverage_ratio: float
    loaded_universe: int = 0
    requested_universe: int | None = None
    daily_covered_count: int = 0
    valid_for_50sma: int = 0
    valid_for_200sma: int = 0
    nhnl_uses_intraday: bool = False
    points: list[BreadthPoint]


class MarketBreadthOverviewPoint(BaseModel):
    date: str
    advancers: int
    decliners: int
    advance_decline_ratio: float | None = None
    ad_line: float | None = None
    mcclellan: float | None = None
    new_highs: int = 0
    new_lows: int = 0
    nh_nl_ratio: float | None = None
    pct_above_20sma: float | None = None
    pct_above_50sma: float | None = None
    pct_above_200sma: float | None = None
    up_volume: float | None = None
    down_volume: float | None = None
    up_down_volume_ratio: float | None = None
    deemer_ratio: float | None = None


class MarketBreadthSignal(BaseModel):
    key: str
    title: str
    value: str
    detail: str
    tone: Literal["good", "neutral", "warning", "bad"]
    comment: str = ""
    metrics: dict = Field(default_factory=dict)


class MarketBreadthOverviewResponse(BaseModel):
    as_of: str
    universe: str
    source: Literal["database", "missing"]
    data_status: Literal["fresh", "stale", "missing"]
    message: str = ""
    coverage_ratio: float
    loaded_universe: int = 0
    requested_universe: int | None = None
    signals: list[MarketBreadthSignal]
    points: list[MarketBreadthOverviewPoint]


class UniverseStatusResponse(BaseModel):
    key: str
    name: str
    source: str
    member_count: int
    updated_at: datetime | None = None
    sample_tickers: list[str]
    metadata: dict = Field(default_factory=dict)


class UniverseSymbolMappingItem(BaseModel):
    universe_key: str = "us_common_stocks"
    source_ticker: str
    yahoo_symbol: str = ""
    status: Literal["active", "ignored", "unmapped"] = "active"
    source: str = "manual"
    note: str = ""
    confidence: float | None = Field(default=None, ge=0, le=1)
    updated_at: datetime | None = None


class UniverseSymbolMappingReviewResponse(BaseModel):
    source: Literal["database", "fallback", "missing"]
    as_of: str
    universe_key: str
    member_count: int
    mapped_count: int
    ignored_count: int
    unmapped_count: int
    mappings: list[UniverseSymbolMappingItem]
    unmapped_sample: list[str]


class UniverseSymbolMappingUpdateRequest(BaseModel):
    universe_key: str = "us_common_stocks"
    source_ticker: str = Field(min_length=1, max_length=32)
    yahoo_symbol: str = Field(default="", max_length=64)
    status: Literal["active", "ignored"] = "active"
    note: str = ""


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
    vix_pct_above_sma10: float | None = None
    vix_panic_overextension: bool = False
    vix_regime: str
    vxx_close: float | None = None
    vxx_ret_5d: float | None = None
    vxx_state: str
    vxx_stress_confirmation: bool
    vxx_carry_decay: bool
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


class MarketDiagnosticCheck(BaseModel):
    category: Literal["trend", "breadth", "volatility", "warning", "intermarket", "rotation", "data"]
    label: str
    passed: bool
    detail: str
    tone: Literal["good", "neutral", "warning", "bad"]


class MarketIntermarketItem(BaseModel):
    ticker: str
    name: str
    close: float | None = None
    day_pct: float | None = None
    dist_to_20d_high_pct: float | None = None
    at_20d_high: bool
    tone: Literal["good", "neutral", "warning", "bad"]
    status: str


class MarketSectorRotationItem(BaseModel):
    ticker: str
    name: str
    group: Literal["defensive", "offensive"]
    return_10d_pct: float | None = None


class MarketSectorRotationGroup(BaseModel):
    group: Literal["defensive", "offensive"]
    label: str
    avg_return_10d_pct: float | None = None
    items: list[MarketSectorRotationItem]


class MarketDiagnosticsResponse(BaseModel):
    as_of: str
    source: Literal["database", "synthetic_fixture", "missing"]
    data_status: Literal["fresh", "stale", "missing", "fallback"]
    message: str = ""
    summary: str
    warning_count: int
    defensive_lead: bool | None = None
    defensive_spread_pct: float | None = None
    checklist: list[MarketDiagnosticCheck]
    intermarket: list[MarketIntermarketItem]
    sector_rotation: list[MarketSectorRotationGroup]


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


class RsLinePoint(BaseModel):
    date: str
    rs: float
    rs_ema21: float | None = None
    rs_ema50: float | None = None


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
    rs_ema21: float | None = None
    rs_ema50: float | None = None
    rs_history: list[RsLinePoint] = Field(default_factory=list)


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
    beta: float | None = None
    institutional_ownership_pct: float | None = None
    next_earnings_calendar_days: int | None = None
    next_earnings_trading_days: int | None = None


class StockFundamentalsEpsQuarter(BaseModel):
    fiscal_period: str = ""
    eps_current_quarter: float | None = None
    eps_same_quarter_last_year: float | None = None
    eps_growth_yoy_pct: float | None = None
    flag: str | None = None


class StockFundamentalsItem(BaseModel):
    ticker: str
    as_of: str
    source: str
    fiscal_period: str = ""
    quarterly_eps_growth_pct: float | None = None
    annual_eps_growth_pct: float | None = None
    quarterly_revenue_growth_pct: float | None = None
    annual_revenue_growth_pct: float | None = None
    roe_pct: float | None = None
    profit_margin_pct: float | None = None
    trailing_eps: float | None = None
    quarterly_eps_accelerating: bool | None = None
    quarterly_revenue_accelerating: bool | None = None
    institutional_holders: int | None = None
    institutional_ownership_pct: float | None = None
    next_earnings_date: str | None = None
    beta: float | None = None
    eps_quarter_history: list[StockFundamentalsEpsQuarter] = Field(default_factory=list)


class StockFundamentalsResponse(BaseModel):
    ticker: str
    source: Literal["database", "missing"]
    item: StockFundamentalsItem | None = None


class StockFundamentalsUpdateRequest(BaseModel):
    as_of: str | None = None
    source: str = "manual"
    fiscal_period: str = ""
    quarterly_eps_growth_pct: float | None = None
    annual_eps_growth_pct: float | None = None
    quarterly_revenue_growth_pct: float | None = None
    annual_revenue_growth_pct: float | None = None
    roe_pct: float | None = None
    profit_margin_pct: float | None = None
    trailing_eps: float | None = None
    quarterly_eps_accelerating: bool | None = None
    quarterly_revenue_accelerating: bool | None = None
    institutional_holders: int | None = Field(default=None, ge=0)
    institutional_ownership_pct: float | None = Field(default=None, ge=0, le=100)
    next_earnings_date: str | None = None
    beta: float | None = None
    eps_quarter_history: list[StockFundamentalsEpsQuarter] = Field(default_factory=list)


class StockEarningsWarning(BaseModel):
    next_earnings_date: str | None = None
    calendar_days: int | None = None
    trading_days: int | None = None
    tone: Literal["good", "neutral", "warning", "bad"]
    message: str


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
    fundamentals: StockFundamentalsItem | None = None
    earnings: StockEarningsWarning | None = None
    checks: list[StockAssessmentCheck]
    chart_signals: list[StockAssessmentSignal]
    drivers: list[str]
    warnings: list[str]


class StockAssessmentRankingItem(BaseModel):
    ticker: str
    name: str
    as_of: str
    verdict_label: str
    verdict_tone: Literal["good", "neutral", "warning", "bad"]
    overall_score: int
    technical_score: float
    fundamental_score: float
    moving_average_score: float
    chart_behavior_score: int
    rs_rating: int | None = None
    dollar_volume_mio: float | None = None
    atr_pct: float | None = None
    warnings_count: int
    top_warning: str = ""
    top_driver: str = ""


class StockAssessmentRankingResponse(BaseModel):
    as_of: str
    source: Literal["database", "missing"]
    rows: list[StockAssessmentRankingItem]


class StockAssessmentCompareItem(BaseModel):
    rank: int
    ticker: str
    name: str
    as_of: str
    source: Literal["database", "missing"]
    data_status: Literal["fresh", "stale", "missing"]
    verdict_label: str
    verdict_tone: Literal["good", "neutral", "warning", "bad"]
    overall_score: int
    technical_score: float
    fundamental_score: float
    moving_average_score: float
    chart_behavior_score: int
    price: float | None = None
    perf_1m_pct: float | None = None
    perf_3m_pct: float | None = None
    perf_6m_pct: float | None = None
    drawdown_52w_pct: float | None = None
    atr_pct: float | None = None
    beta: float | None = None
    rs_rating: int | None = Field(default=None, ge=1, le=99)
    above_sma10: bool | None = None
    above_ema21: bool | None = None
    above_sma50: bool | None = None
    above_sma200: bool | None = None
    ma_order: bool | None = None
    fundamental_criteria_passed: int
    fundamental_criteria_total: int
    fundamental_positive: int
    fundamental_negative: int
    fundamental_neutral: int
    technical_positive: int
    technical_negative: int
    technical_neutral: int
    chart_positive: int
    chart_negative: int
    chart_neutral: int
    top_driver: str = ""
    top_warning: str = ""


class StockAssessmentCompareResponse(BaseModel):
    as_of: str
    source: Literal["database", "partial", "missing"]
    requested_tickers: list[str]
    missing_tickers: list[str]
    rows: list[StockAssessmentCompareItem]


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


class Sec13FMappingItem(BaseModel):
    cusip: str
    ticker: str
    issuer_name: str = ""
    source: str = ""
    confidence: float | None = None
    updated_at: datetime | None = None


class Sec13FUnmatchedCusipItem(BaseModel):
    cusip: str
    issuer: str = ""
    title: str = ""
    reason: str = ""
    candidate_tickers: str = ""
    current_holder_count: int | None = None
    current_total_value_usd: float | None = None


class Sec13FMappingReviewResponse(BaseModel):
    source: Literal["database", "missing"]
    as_of: str
    mappings: list[Sec13FMappingItem]
    unmatched: list[Sec13FUnmatchedCusipItem]
    unmatched_source_job_id: str = ""


class Sec13FMappingUpdateRequest(BaseModel):
    cusip: str = Field(min_length=9, max_length=16)
    ticker: str = Field(min_length=1, max_length=32)
    issuer_name: str = ""


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


class TradeRepublicIsinMappingItem(BaseModel):
    isin: str
    name: str
    asset_class: str
    ticker: str = ""
    source: Literal["manual", "saved", "static", "missing"] = "missing"


class TradeRepublicSkippedPosition(BaseModel):
    isin: str
    name: str
    shares: float
    asset_class: str
    reason: str


class TradeRepublicTransactionImportRequest(BaseModel):
    file_name: str = "trade-republic-transactions.csv"
    content: str
    dry_run: bool = True
    replace_open_positions: bool = False
    isin_overrides: dict[str, str] = Field(default_factory=dict)


class TradeRepublicTransactionImportResponse(BaseModel):
    ok: bool
    dry_run: bool
    import_id: str | None = None
    rows_total: int
    rows_imported: int
    transactions_total: int
    cash_balance_estimate: float
    positions: list[PortfolioImportRow]
    mappings: list[TradeRepublicIsinMappingItem]
    skipped_positions: list[TradeRepublicSkippedPosition] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class IsinMappingWrite(BaseModel):
    isin: str
    ticker: str


class IsinMappingPatchRequest(BaseModel):
    mappings: list[IsinMappingWrite]


class IsinMappingListResponse(BaseModel):
    mappings: list[TradeRepublicIsinMappingItem]


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


class PortfolioCurvePoint(BaseModel):
    date: str
    depot_value: float
    positions_value: float
    cash: float
    portfolio_index: float
    portfolio_index_sma10: float | None = None
    portfolio_index_sma21: float | None = None
    sp500_index: float | None = None


class PortfolioCurveResponse(BaseModel):
    as_of: str
    source: Literal["database", "trade_republic_transactions", "missing"]
    data_status: Literal["fresh", "missing"]
    message: str = ""
    points: list[PortfolioCurvePoint]


class PortfolioPositionSizeRequest(BaseModel):
    depot_value: float = Field(default=0, ge=0)
    risk_per_position_pct: float = Field(default=1.0, ge=0.1, le=5)
    target_risk_contribution: float = Field(default=0.20, ge=0.05, le=0.50)
    buy_price: float = Field(default=1.0, gt=0)
    stop_pct: float = Field(default=7.0, ge=0.1, le=50)
    current_price: float | None = Field(default=None, gt=0)
    atr_pct: float | None = Field(default=None, ge=0)
    beta: float | None = Field(default=None, ge=0)
    market_atr_pct: float | None = Field(default=None, gt=0)


class PortfolioPositionSizeResponse(BaseModel):
    risk_budget: float
    risk_per_share: float
    stop_price: float
    max_shares_by_loss_budget: int
    max_position_value_by_loss_budget: float
    balancer_score: float | None = None
    max_weight_pct_by_balancer: float | None = None
    max_position_value_by_balancer: float | None = None
    max_shares_by_balancer: int | None = None
    recommended_max_shares: int
    recommended_position_value: float
    limiting_factor: Literal["loss_budget", "beta_balancer", "insufficient_data"]
    warnings: list[str] = Field(default_factory=list)


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
    "smart_refresh_market_data",
    "bootstrap_market_data",
    "refresh_prices",
    "refresh_breadth",
    "refresh_relative_strength",
    "refresh_fundamentals",
    "refresh_universe",
    "refresh_sec13f",
    "position_atr_monitor",
    "pushover_test",
    "yahoo_symbol_diagnostics",
    "yahoo_symbol_rescue",
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


class DataDiagnosticIssue(BaseModel):
    key: str
    label: str
    severity: Literal["info", "warning", "critical"]
    detail: str
    tickers: list[str] = Field(default_factory=list)
    action_label: str = ""
    job_type: JobType | None = None
    job_payload: dict = Field(default_factory=dict)


class DataDiagnosticsResponse(BaseModel):
    as_of: str
    health_tone: Literal["good", "neutral", "warning", "bad"]
    summary: str
    open_positions_count: int = 0
    price_cache_tickers_count: int = 0
    missing_price_count: int = 0
    stale_price_count: int = 0
    missing_yahoo_symbol_count: int = 0
    isin_mappings_count: int = 0
    issues: list[DataDiagnosticIssue] = Field(default_factory=list)


class WorkspaceState(BaseModel):
    source: Literal["database", "default"]
    updated_at: datetime | None = None
    watchlist: list[str] = Field(default_factory=list)
    todos: str = ""
    recent_tickers: list[str] = Field(default_factory=list)


class WorkspacePatch(BaseModel):
    watchlist: list[str] | None = None
    todos: str | None = None
    recent_tickers: list[str] | None = None


class WorkspaceTickerRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=32)


class SetupStep(BaseModel):
    key: Literal["system", "portfolio", "prices", "market_breadth", "relative_strength", "atr_monitor"]
    label: str
    status: Literal["complete", "pending", "running", "warning", "blocked", "error"]
    detail: str
    action_label: str = ""
    href: str = ""
    job_type: JobType | None = None
    job_payload: dict = Field(default_factory=dict)
    latest_job: Job | None = None


class SetupStatusResponse(BaseModel):
    as_of: datetime
    status: Literal["ready", "needs_action", "running", "blocked"]
    summary: str
    next_step_key: str = ""
    steps: list[SetupStep]


class AppSettings(BaseModel):
    atr_threshold: float
    risk_per_position_pct: float = 1.0
    target_risk_contribution: float = 0.20
    max_depot_loss_lower_pct: float = 4.0
    max_depot_loss_upper_pct: float = 8.0
    position_monitor_enabled: bool
    position_monitor_interval_minutes: int
    position_monitor_threshold_atr: float = 1.5
    position_monitor_atr_period: int = 14
    position_monitor_lookback_days: int = 420
    position_monitor_cooldown_hours: int = 18
    position_monitor_reference: Literal["high_since_buy", "close_since_buy", "entry_price", "previous_close"] = "high_since_buy"
    pushover_enabled: bool = False
    pushover_configured: bool = False
    rs_rating_source: Literal["csv_latest", "computed"]
    data_jobs_enabled: bool


class SettingsPatch(BaseModel):
    atr_threshold: float | None = None
    risk_per_position_pct: float | None = None
    target_risk_contribution: float | None = None
    max_depot_loss_lower_pct: float | None = None
    max_depot_loss_upper_pct: float | None = None
    position_monitor_enabled: bool | None = None
    position_monitor_interval_minutes: int | None = None
    position_monitor_threshold_atr: float | None = None
    position_monitor_atr_period: int | None = None
    position_monitor_lookback_days: int | None = None
    position_monitor_cooldown_hours: int | None = None
    position_monitor_reference: Literal["high_since_buy", "close_since_buy", "entry_price", "previous_close"] | None = None
    pushover_enabled: bool | None = None
    rs_rating_source: Literal["csv_latest", "computed"] | None = None
    data_jobs_enabled: bool | None = None


class RuntimeConfigItem(BaseModel):
    key: str
    label: str
    category: Literal["external_api", "notifications", "database", "security", "deployment"]
    description: str
    configured: bool
    source: Literal["database", "environment", "missing", "bootstrap_only"]
    secret: bool = True
    editable: bool = False
    restart_required: bool = False
    runtime_applied: bool = False
    placeholder: str = ""
    value_preview: str = ""


class RuntimeConfigResponse(BaseModel):
    items: list[RuntimeConfigItem]
    editable_keys: list[str]
    bootstrap_keys: list[str]
    note: str


class RuntimeConfigPatch(BaseModel):
    values: dict[str, str] = Field(default_factory=dict)
    clear_keys: list[str] = Field(default_factory=list)


class RuntimeConfigTestRequest(BaseModel):
    key: str
    value: str | None = None


class RuntimeConfigTestResponse(BaseModel):
    key: str
    ok: bool
    status: Literal["ok", "missing", "invalid", "failed", "unsupported"]
    detail: str
    checked_at: datetime
    restart_required: bool = False


DatabaseTarget = Literal["local", "neon"]


class DatabaseTargetResponse(BaseModel):
    target: DatabaseTarget
    running_target: DatabaseTarget
    restart_required: bool
    neon_configured: bool
    neon_value_preview: str = ""
    local_value_preview: str = ""
    active_value_preview: str = ""
    message: str


class DatabaseTargetSwitchRequest(BaseModel):
    target: DatabaseTarget


class RuntimeServicesRestartResponse(BaseModel):
    ok: bool
    status: Literal["scheduled", "disabled", "failed"]
    detail: str
    services: list[str] = Field(default_factory=list)
    started_at: datetime
