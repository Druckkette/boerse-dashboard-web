export type Tone = "good" | "neutral" | "warning" | "bad";
export type MarketPhase = "rot" | "gelb_startschuss" | "gruen" | "aufwaertstrend" | "gelb_trend_unter_druck" | "neutral";

export type KpiCard = {
  label: string;
  value: string;
  detail: string;
  tone: Tone;
};

export type MarketTrendAmpel = {
  logic?: "current" | "ibd";
  ruleset_version?: string;
  ftd_negated?: boolean;
  price_data_complete?: boolean;
  powertrend_state?: "off" | "on" | "under_pressure";
  powertrend_start_date?: string | null;
  powertrend_pressure_since?: string | null;
  powertrend_formally_active?: boolean;
  ticker: string;
  as_of: string;
  phase: MarketPhase;
  phase_label: string;
  close?: number | null;
  anchor_date?: string | null;
  floor_mark?: number | null;
  startschuss_low?: number | null;
  startschuss_bonus?: boolean | null;
  dist_count_25: number;
  market_structure: "up" | "down" | "mixed" | "unknown";
  uptrend_high?: number | null;
  phase_reason?: string | null;
  source: "database" | "missing" | "synthetic_fixture";
};

export type MarketOverview = {
  as_of: string;
  as_of_time: string;
  source: "database" | "synthetic_fixture" | "missing";
  data_status: "fresh" | "stale" | "missing" | "fallback" | "partial";
  message: string;
  phase: MarketPhase;
  phase_label: string;
  action: string;
  warning_count: number;
  breadth_mode: "schutz" | "wachsam" | "rueckenwind";
  volatility_regime: string;
  trend_ampel?: MarketTrendAmpel | null;
  kpis: KpiCard[];
};

export type MarketAmpelHero = {
  mode: string;
  tone: Tone;
  action: string;
  reasons: string[];
};

export type MarketAmpelLight = {
  key: "rot" | "gelb_startschuss" | "gruen" | "aufwaertstrend" | "gelb_trend_unter_druck";
  label: string;
  active: boolean;
  rule: string;
  tone: Tone;
};

export type MarketAmpelPhaseInfo = {
  phase: MarketPhase;
  label: string;
  reason: string;
  action: string;
  tone: Tone;
  next_step: string;
  last_changed_at?: string | null;
  last_change_reason?: string | null;
};

export type MarketAmpelCycle = {
  anchor_date?: string | null;
  anchor_current?: boolean;
  floor_mark?: number | null;
  floor_current?: boolean;
  floor_distance_pct?: number | null;
  startschuss_low?: number | null;
  startschuss_current?: boolean;
  startschuss_distance_pct?: number | null;
  startschuss_bonus?: boolean | null;
  ftd_negated: boolean;
  ma_order?: boolean | null;
  market_structure: "up" | "down" | "mixed" | "unknown";
  uptrend_high?: number | null;
  phase_reason?: string | null;
  diagnostics: string[];
};

export type MarketAmpelChangeCard = {
  title: string;
  value: string;
  detail: string;
  tone: Tone;
  detail2?: string | null;
  detail3?: string | null;
  arrow?: "up" | "down" | "flat" | null;
  quality?: string | null;
};

export type MarketAmpelDistanceTile = {
  label: string;
  value: string;
  indicator: string;
  tone: Tone;
  detail: string;
};

export type MarketAmpelWarningCheck = {
  code?: string | null;
  label: string;
  passed: boolean;
  detail: string;
  active_warning: boolean;
  tone: Tone;
};

export type MarketAmpelChartPoint = {
  date: string;
  open?: number | null;
  high?: number | null;
  low?: number | null;
  close?: number | null;
  volume?: number | null;
  ema21?: number | null;
  sma10?: number | null;
  sma50?: number | null;
  sma200?: number | null;
  vol_sma50?: number | null;
  dist_52w_pct?: number | null;
  consec_low_above_21: number;
  consec_low_above_50: number;
  consec_low_above_200: number;
  ema21_held: boolean;
  sma50_held: boolean;
  sma200_held: boolean;
  up_vol_declining: boolean;
  phase: MarketPhase;
  is_distribution: boolean;
  is_stall: boolean;
  intraday_reversal_down: boolean;
  intraday_reversal_up: boolean;
};

export type MarketAmpelChartMarker = {
  key: string;
  date: string;
  label: string;
  value?: number | null;
  color: string;
};

export type MarketAmpelPowerTrend = {
  enabled: boolean;
  state: "off" | "on" | "under_pressure";
  formal_active: boolean;
  start_date?: string | null;
  pressure_since?: string | null;
  low_above_21_streak: number;
  ema21_over_50_streak: number;
  sma50_rising_1d: boolean;
  positive_or_flat_day: boolean;
  reason: string;
};

export type MarketAmpel = {
  component_errors?: string[];
  logic: "current" | "ibd";
  confirmed_as_of?: string;
  quote_as_of?: string;
  intraday?: boolean;
  as_of: string;
  as_of_time: string;
  ticker: string;
  name: string;
  source: "database" | "missing";
  data_status: "fresh" | "stale" | "missing" | "fallback" | "partial";
  message: string;
  warning_count: number;
  breadth_mode: "schutz" | "wachsam" | "rueckenwind";
  volatility_regime: string;
  vix_regime: string;
  hero: MarketAmpelHero;
  phase_info: MarketAmpelPhaseInfo;
  lights: MarketAmpelLight[];
  cycle: MarketAmpelCycle;
  change_cards: MarketAmpelChangeCard[];
  distance_tiles: MarketAmpelDistanceTile[];
  warning_checks: MarketAmpelWarningCheck[];
  chart_points: MarketAmpelChartPoint[];
  chart_markers: MarketAmpelChartMarker[];
  powertrend: MarketAmpelPowerTrend;
};

export type BreadthPoint = {
  date: string;
  advancers: number;
  decliners: number;
  ad_line: number;
  mcclellan: number;
  pct_above_50sma: number;
  pct_above_200sma: number;
  new_highs: number;
  new_lows: number;
};

export type Breadth = {
  as_of: string;
  universe: string;
  source: "database" | "synthetic_fixture" | "missing";
  data_status: "fresh" | "stale" | "missing" | "fallback" | "partial";
  message: string;
  coverage_ratio: number;
  loaded_universe: number;
  requested_universe?: number | null;
  daily_covered_count: number;
  valid_for_50sma: number;
  valid_for_200sma: number;
  nhnl_uses_intraday: boolean;
  points: BreadthPoint[];
};

export type MarketBreadthOverviewPoint = {
  date: string;
  advancers: number;
  decliners: number;
  advance_decline_ratio?: number | null;
  ad_line?: number | null;
  mcclellan?: number | null;
  new_highs: number;
  new_lows: number;
  nh_nl_ratio?: number | null;
  pct_above_20sma?: number | null;
  pct_above_50sma?: number | null;
  pct_above_200sma?: number | null;
  up_volume?: number | null;
  down_volume?: number | null;
  up_down_volume_ratio?: number | null;
  deemer_ratio?: number | null;
};

export type MarketBreadthSignal = {
  key: string;
  title: string;
  value: string;
  detail: string;
  tone: Tone;
  comment: string;
  metrics: Record<string, unknown>;
};

export type MarketBreadthOverview = {
  as_of: string;
  universe: string;
  source: "database" | "missing";
  data_status: "fresh" | "stale" | "missing";
  message: string;
  coverage_ratio: number;
  loaded_universe: number;
  requested_universe?: number | null;
  signals: MarketBreadthSignal[];
  points: MarketBreadthOverviewPoint[];
};

export type MarketDeepAnalysisMetric = {
  label: string;
  value: string;
  detail: string;
  tone: Tone;
};

export type MarketDeepAnalysisCheck = {
  label: string;
  passed: boolean;
  detail: string;
  tone: Tone;
};

export type MarketDeepAnalysisPoint = {
  date: string;
  ad_line?: number | null;
  mcclellan?: number | null;
  new_highs: number;
  new_lows: number;
  nh_nl_ratio?: number | null;
  pct_above_50sma?: number | null;
  pct_above_200sma?: number | null;
  deemer_ratio?: number | null;
};

export type MarketDeepAnalysis = {
  as_of: string;
  source: "database" | "missing";
  data_status: "fresh" | "stale" | "missing";
  message: string;
  universe: string;
  coverage_ratio: number;
  loaded_universe: number;
  requested_universe?: number | null;
  daily_covered_count: number;
  valid_for_50sma: number;
  valid_for_200sma: number;
  nhnl_uses_intraday: boolean;
  metrics: MarketDeepAnalysisMetric[];
  checks: MarketDeepAnalysisCheck[];
  points: MarketDeepAnalysisPoint[];
};

export type UniverseStatus = {
  key: string;
  name: string;
  source: string;
  member_count: number;
  updated_at?: string | null;
  sample_tickers: string[];
  metadata: Record<string, unknown>;
};

export type UniverseSymbolMappingItem = {
  universe_key: string;
  source_ticker: string;
  yahoo_symbol: string;
  status: "active" | "ignored" | "unmapped";
  source: string;
  note: string;
  confidence?: number | null;
  updated_at?: string | null;
};

export type UniverseSymbolMappingReview = {
  source: "database" | "fallback" | "missing";
  as_of: string;
  universe_key: string;
  member_count: number;
  mapped_count: number;
  ignored_count: number;
  unmapped_count: number;
  mappings: UniverseSymbolMappingItem[];
  unmapped_sample: string[];
};

export type UniverseSymbolMappingUpdate = {
  universe_key?: string;
  source_ticker: string;
  yahoo_symbol?: string;
  status?: "active" | "ignored";
  note?: string;
};

export type VolatilityStatusCard = {
  title: string;
  status: string;
  detail: string;
  tone: Tone;
};

export type VolatilityPoint = {
  date: string;
  spx_close?: number | null;
  spx_ret_5d?: number | null;
  vix_close?: number | null;
  vix_sma10?: number | null;
  vix_ema21?: number | null;
  vix_ret_5d?: number | null;
  vix_pct_rank_252?: number | null;
  vix_pct_above_sma10?: number | null;
  vix_panic_overextension: boolean;
  vix_regime: string;
  vxx_close?: number | null;
  vxx_ema21?: number | null;
  vxx_ret_5d?: number | null;
  vxx_state: string;
  vxx_stress_confirmation: boolean;
  vxx_carry_decay: boolean;
  vol_regime: string;
  fragile_rally: boolean;
};

export type Volatility = {
  as_of: string;
  source: "database" | "missing";
  regime: string;
  status_cards: VolatilityStatusCard[];
  points: VolatilityPoint[];
};

export type SectorRankingRow = {
  ticker: string;
  name: string;
  rank: number;
  return_pct: number;
  return_1d_pct?: number | null;
  return_5d_pct?: number | null;
  return_20d_pct?: number | null;
};

export type SectorRankingPoint = {
  date: string;
  ticker: string;
  name: string;
  rank: number;
  return_pct: number;
};

export type SectorRanking = {
  as_of: string;
  source: "database" | "missing" | "synthetic_fixture";
  data_status: "fresh" | "stale" | "missing" | "fallback" | "partial";
  mode: "daily" | "weekly";
  message: string;
  rows: SectorRankingRow[];
  top: SectorRankingRow[];
  bottom: SectorRankingRow[];
  history: SectorRankingPoint[];
};

export type MarketDiagnosticCheck = {
  category: "trend" | "breadth" | "volatility" | "warning" | "intermarket" | "rotation" | "data";
  label: string;
  passed: boolean;
  detail: string;
  tone: Tone;
};

export type MarketIntermarketItem = {
  ticker: string;
  name: string;
  close?: number | null;
  day_pct?: number | null;
  dist_to_20d_high_pct?: number | null;
  at_20d_high: boolean;
  tone: Tone;
  status: string;
};

export type MarketSectorRotationItem = {
  ticker: string;
  name: string;
  group: "defensive" | "offensive";
  return_10d_pct?: number | null;
};

export type MarketSectorRotationGroup = {
  group: "defensive" | "offensive";
  label: string;
  avg_return_10d_pct?: number | null;
  items: MarketSectorRotationItem[];
};

export type MarketDiagnostics = {
  component_errors?: string[];
  as_of: string;
  source: "database" | "synthetic_fixture" | "missing";
  data_status: "fresh" | "stale" | "missing" | "fallback" | "partial";
  message: string;
  summary: string;
  warning_count: number;
  defensive_lead?: boolean | null;
  defensive_spread_pct?: number | null;
  checklist: MarketDiagnosticCheck[];
  intermarket: MarketIntermarketItem[];
  sector_rotation: MarketSectorRotationGroup[];
};

export type ServiceFreshness = {
  name: string;
  status: "fresh" | "stale" | "missing";
  as_of: string;
  lag_minutes: number;
  detail?: string;
  metadata?: Record<string, unknown>;
};

export type Freshness = {
  generated_at: string;
  services: ServiceFreshness[];
};

export type SystemReadinessCheck = {
  name: string;
  status: "ok" | "warning" | "error" | "unknown";
  required: boolean;
  detail: string;
  latency_ms?: number | null;
  metadata: Record<string, unknown>;
};

export type SystemReadiness = {
  status: "ready" | "degraded" | "not_ready";
  generated_at: string;
  checks: SystemReadinessCheck[];
};

export type PortfolioPosition = {
  ticker: string;
  name: string;
  shares: number;
  entry_price: number;
  current_price: number;
  market_value: number;
  pnl_pct: number;
  weight_pct: number;
  atr_pct?: number | null;
  beta?: number | null;
  beta_balancer_score?: number | null;
  risk_contribution?: number | null;
  position_loss_risk?: number | null;
  position_loss_risk_pct?: number | null;
  status: "ok" | "watch" | "risk" | "sell";
  pnl_abs: number;
  currency: string;
  buy_date?: string | null;
  pivot_tag?: string | null;
  stop_pct?: number | null;
  stop_price?: number | null;
  broker: string;
  account: string;
  note: string;
};

export type PortfolioAfterHoursPosition = {
  ticker: string;
  name: string;
  shares: number;
  regular_price?: number | null;
  after_hours_price?: number | null;
  after_hours_change?: number | null;
  after_hours_change_pct?: number | null;
  after_hours_value_change?: number | null;
  market_value: number;
  market_state: string;
  currency: string;
  source: string;
  available: boolean;
  error_message: string;
};

export type PortfolioAfterHours = {
  as_of: string;
  currency: string;
  total_market_value: number;
  total_after_hours_change: number;
  total_after_hours_change_pct: number;
  available_count: number;
  positions_count: number;
  positions: PortfolioAfterHoursPosition[];
};

export type PortfolioSnapshot = {
  as_of: string;
  total_value: number;
  invested_value: number;
  cash_balance: number;
  cash_ratio_pct: number;
  portfolio_atr_pct?: number | null;
  market_atr_pct?: number | null;
  beta_balancer?: number | null;
  max_depot_loss_abs?: number | null;
  max_depot_loss_available?: boolean;
  max_depot_loss_pct: number;
  stop_coverage_count: number;
  stop_coverage_total: number;
  stop_coverage_pct: number;
  data_quality_status: "trusted" | "limited" | "blocked";
  kpis: KpiCard[];
  positions: PortfolioPosition[];
};

export type PortfolioCurvePoint = {
  date: string;
  depot_value: number;
  positions_value: number;
  cash: number;
  portfolio_index: number;
  portfolio_index_sma10?: number | null;
  portfolio_index_sma21?: number | null;
  sp500_index?: number | null;
};

export type PortfolioCurve = {
  as_of: string;
  source: "database" | "trade_republic_transactions" | "missing";
  data_status: "fresh" | "limited" | "stale" | "missing";
  base_date?: string | null;
  message: string;
  points: PortfolioCurvePoint[];
};

export type BuyStrengthCheck = {
  key: string;
  label: string;
  category: "positive" | "warning";
  passed: boolean;
  tone: "good" | "neutral" | "warning" | "bad";
  detail: string;
};

export type BuyStrengthSummaryItem = {
  ticker: string;
  name: string;
  buy_date: string;
  age_days: number;
  window_days?: number | null;
  latest_price_date?: string | null;
  data_status?: "fresh" | "stale" | "missing";
  pnl_pct?: number | null;
  current_price?: number | null;
  entry_price?: number | null;
  checks_passed: number;
  checks_total: number;
  warnings_active: number;
  warnings_total: number;
  status: "stark" | "ok" | "watch" | "risk" | "missing";
  status_label: string;
  message: string;
};

export type BuyStrengthOverview = {
  as_of: string;
  window_days: number;
  items: BuyStrengthSummaryItem[];
};

export type BuyStrengthAssessment = {
  ticker: string;
  name: string;
  buy_date?: string | null;
  age_days?: number | null;
  window_days: number;
  source: "database" | "missing";
  data_status: "fresh" | "stale" | "missing";
  status: "stark" | "ok" | "watch" | "risk" | "missing";
  status_label: string;
  message: string;
  entry_price?: number | null;
  current_price?: number | null;
  pnl_pct?: number | null;
  buy_day_low?: number | null;
  previous_day_low?: number | null;
  latest_close?: number | null;
  latest_price_date?: string | null;
  checks: BuyStrengthCheck[];
  warnings: BuyStrengthCheck[];
};

export type PortfolioPositionSizeRequest = {
  depot_value: number;
  risk_per_position_pct: number;
  target_risk_contribution: number;
  buy_price: number;
  stop_unit?: "pct" | "usd";
  stop_amount?: number | null;
  stop_pct: number;
  current_price?: number | null;
  atr_pct?: number | null;
  beta?: number | null;
  market_atr_pct?: number | null;
};

export type PortfolioPositionSizeResult = {
  risk_budget: number;
  risk_per_share: number;
  stop_price: number;
  max_shares_by_loss_budget: number;
  max_position_value_by_loss_budget: number;
  balancer_score?: number | null;
  max_weight_pct_by_balancer?: number | null;
  max_position_value_by_balancer?: number | null;
  max_shares_by_balancer?: number | null;
  recommended_max_shares: number;
  recommended_position_value: number;
  limiting_factor: "loss_budget" | "beta_balancer" | "insufficient_data";
  warnings: string[];
};

export type TradeJournalEntryType = "buy" | "sell" | "ex_post";
export type TradeJournalEntryStatus = "open" | "closed" | "draft";

export type TradeJournalImageSet = {
  daily_chart: string;
  weekly_chart: string;
};

export type TradeJournalDefaults = {
  ticker: string;
  entry_type: TradeJournalEntryType;
  trade_date: string;
  price?: number | null;
  shares?: number | null;
  currency?: string;
  fees?: number | null;
  tax?: number | null;
  source_evidence?: string;
  open_buy_entry_id?: string | null;
  open_buy_price?: number | null;
  open_buy_date?: string | null;
  stop_price?: number | null;
  stop_distance_pct?: number | null;
  portfolio_snapshot: Record<string, unknown>;
  market_snapshot: Record<string, unknown>;
};

export type TradeJournalEntryRequest = {
  ticker: string;
  entry_type: TradeJournalEntryType;
  trade_date?: string | null;
  price?: number | null;
  shares?: number | null;
  currency?: string;
  fees?: number | null;
  tax?: number | null;
  source_evidence?: string;
  stop_price?: number | null;
  linked_entry_id?: string | null;
  status?: TradeJournalEntryStatus | null;
  basis_text?: string;
  alternative_entry?: boolean;
  alternative_entry_text?: string;
  primary_reasons?: string;
  sell_reason?: string;
  close_with_related_buy?: boolean;
  questionnaire?: Record<string, unknown>;
  chart_images?: TradeJournalImageSet;
};

export type TradeJournalEntrySummary = {
  currency?: string;
  realized_pnl?: number | null;
  source_transaction_id?: string | null;
  trade_group_id?: string | null;
  position_id?: string | null;
  instrument_name: string;
  isin: string;
  execution_at?: string | null;
  source: "trade_republic" | "manual";
  fees?: number | null;
  tax?: number | null;
  gross_amount?: number | null;
  net_amount?: number | null;
  context_status: "archived" | "reconstructed" | "partial" | "missing" | "pending" | "failed";
  context_label: string;
  has_note: boolean;
  id: string;
  ticker: string;
  entry_type: TradeJournalEntryType;
  status: TradeJournalEntryStatus;
  trade_date: string;
  price?: number | null;
  shares?: number | null;
  realized_pnl_eur?: number | null;
  realized_pnl_pct?: number | null;
  linked_entry_id?: string | null;
  title: string;
  summary: string;
  created_at: string;
  updated_at: string;
};

export type TradeJournalEntryDetail = TradeJournalEntrySummary & {
  executions?: TradeJournalEntrySummary[];
  sell_assessment?: Record<string, unknown>;
  historical_chart?: {
    currency: string;
    execution_date: string;
    assessment_as_of: string;
    first_date: string | null;
    last_date: string | null;
    points: (PriceBarPoint & { sma10: number | null; ema21: number | null; sma50: number | null; sma200: number | null })[];
    markers: { entry_id: string; date: string; entry_type: "buy" | "sell"; price: number | null; currency: string; shares: number | null; selected: boolean }[];
  } | null;
  stop_price?: number | null;
  stop_distance_pct?: number | null;
  stop_deviation_pct?: number | null;
  basis_text: string;
  alternative_entry: boolean;
  alternative_entry_text: string;
  primary_reasons: string;
  sell_reason: string;
  questionnaire: Record<string, unknown>;
  stock_snapshot: Record<string, unknown>;
  market_snapshot: Record<string, unknown>;
  portfolio_snapshot: Record<string, unknown>;
  chart_images: TradeJournalImageSet;
};

export type TradeJournalEntriesResponse = {
  ticker?: string | null;
  entries: TradeJournalEntrySummary[];
  total: number;
  limit: number;
  offset: number;
  next_offset?: number | null;
};

export type TradeJournalFilters = {
  query?: string;
  entry_type?: TradeJournalEntryType | "";
  status?: TradeJournalEntryStatus | "";
  source?: "broker" | "manual" | "";
  date_from?: string;
  date_to?: string;
  limit?: number;
  offset?: number;
  sort?: "newest" | "oldest";
};

export type TradeJournalTradeSummary = {
  id: string;
  ticker: string;
  status: "open" | "closed" | "partial";
  first_entry_date: string;
  last_exit_date?: string | null;
  currency: string;
  execution_count: number;
  buy_count: number;
  sell_count: number;
  bought_shares: number;
  sold_shares: number;
  remaining_shares: number;
  invested_capital?: number | null;
  realized_pnl?: number | null;
  realized_pnl_pct?: number | null;
  context_status: TradeJournalEntrySummary["context_status"];
  has_review: boolean;
  executions: TradeJournalEntrySummary[];
};

export type TradeJournalTradesResponse = { trades: TradeJournalTradeSummary[]; total: number };

export type TradeJournalAnalytics = {
  closed_trades: number;
  net_result: number;
  winners: number;
  losers: number;
  hit_rate_pct?: number | null;
  average_win?: number | null;
  average_loss?: number | null;
  profit_factor?: number | null;
  excluded_incomplete: number;
};

export type TradeJournalEntryResponse = {
  entry: TradeJournalEntryDetail;
};

export type PortfolioPositionWriteRequest = {
  ticker: string;
  name?: string;
  shares: number;
  entry_price: number;
  current_price?: number | null;
  currency?: string;
  buy_date?: string | null;
  pivot_tag?: string | null;
  stop_pct?: number | null;
  stop_price?: number | null;
  broker?: string;
  account?: string;
  note?: string;
  record_transaction?: boolean;
};

export type PortfolioTransaction = {
  id: string;
  ticker: string;
  date: string;
  transaction_type: string;
  shares: number;
  price?: number | null;
  fees: number;
  tax: number;
  gross_amount?: number | null;
  net_amount?: number | null;
  currency: string;
  broker: string;
  external_id: string;
};

export type PortfolioSellRequest = {
  shares: number;
  price: number;
  date?: string | null;
  currency?: string;
  fees?: number;
  tax?: number;
  note?: string;
};

export type PortfolioCashFlow = {
  id: string;
  date: string;
  amount: number;
  flow_type: "deposit" | "withdrawal" | "dividend" | "interest" | "tax" | "fee" | "other" | string;
  currency: string;
  broker: string;
  note: string;
};

export type PortfolioCashFlowRequest = {
  date?: string | null;
  amount: number;
  flow_type: "deposit" | "withdrawal" | "dividend" | "interest" | "tax" | "fee" | "other";
  currency?: string;
  broker?: string;
  note?: string;
};

export type PortfolioImportHistoryItem = {
  id: string;
  source: string;
  file_name: string;
  status: string;
  rows_total: number;
  rows_imported: number;
  error_message: string;
  created_at: string;
  finished_at?: string | null;
};

export type PortfolioImportRow = {
  ticker: string;
  name: string;
  shares: number;
  entry_price: number;
  current_price?: number | null;
  currency: string;
  buy_date?: string | null;
  broker: string;
  account: string;
  note: string;
  warnings: string[];
};

export type PortfolioImportRequest = {
  source?: string;
  file_name: string;
  content: string;
  dry_run: boolean;
  replace_open_positions: boolean;
};

export type PortfolioImportResponse = {
  ok: boolean;
  dry_run: boolean;
  import_id?: string | null;
  rows_total: number;
  rows_imported: number;
  positions: PortfolioImportRow[];
  errors: string[];
  warnings: string[];
};

export type TradeRepublicIsinMappingItem = {
  isin: string;
  name: string;
  asset_class: string;
  ticker: string;
  source: "manual" | "saved" | "static" | "missing";
};

export type TradeRepublicSkippedPosition = {
  isin: string;
  name: string;
  shares: number;
  asset_class: string;
  reason: string;
};

export type TradeRepublicTransactionImportRequest = {
  file_name: string;
  content: string;
  dry_run: boolean;
  replace_open_positions: boolean;
  isin_overrides: Record<string, string>;
};

export type TradeRepublicTransactionImportResponse = {
  ok: boolean;
  dry_run: boolean;
  import_id?: string | null;
  rows_total: number;
  rows_imported: number;
  transactions_total: number;
  cash_balance_estimate: number;
  positions: PortfolioImportRow[];
  mappings: TradeRepublicIsinMappingItem[];
  skipped_positions: TradeRepublicSkippedPosition[];
  errors: string[];
  warnings: string[];
};

export type IsinMappingPatchRequest = {
  mappings: Array<{ isin: string; ticker: string }>;
};

export type IsinMappingListResponse = {
  mappings: TradeRepublicIsinMappingItem[];
};

export type PriceRange = "1m" | "3m" | "6m" | "1y" | "2y" | "5y";

export type PriceBarPoint = {
  date: string;
  open?: number | null;
  high?: number | null;
  low?: number | null;
  close: number;
  adj_close?: number | null;
  volume?: number | null;
};

export type PriceHistory = {
  ticker: string;
  name: string;
  currency: string;
  range: PriceRange;
  source: "database" | "missing";
  data_status: "fresh" | "stale" | "missing" | "fallback" | "partial";
  as_of: string;
  expected_as_of: string;
  session_phase: "intraday" | "closed" | "fallback";
  first_date?: string | null;
  last_date?: string | null;
  cache_updated_at?: string | null;
  last_close?: number | null;
  change_pct?: number | null;
  points: PriceBarPoint[];
};

export type PriceRefresh = {
  ticker: string;
  ok: boolean;
  refreshed_at: string;
  refresh: Record<string, unknown>;
  history: PriceHistory;
};

export type RsRatingItem = {
  ticker: string;
  name: string;
  date: string;
  rating?: number | null;
  score?: number | null;
  percentile?: number | null;
  method: string;
  source: string;
  universe_size: number;
  ret_1m?: number | null;
  ret_3m?: number | null;
  ret_6m?: number | null;
  ret_12m?: number | null;
  excess_return_3m?: number | null;
  excess_return_6m?: number | null;
  excess_return_12m?: number | null;
  near_high_52w?: boolean | null;
  new_high_52w?: boolean | null;
  rs_ema21?: number | null;
  rs_ema50?: number | null;
  rs_history: Array<{
    date: string;
    rs: number;
    rs_ema21?: number | null;
    rs_ema50?: number | null;
  }>;
};

export type RsRatingRanking = {
  as_of: string;
  source: "computed" | "csv_latest" | "database" | "missing";
  total_count: number;
  limit: number;
  rows: RsRatingItem[];
};

export type RsRatingDetail = {
  found: boolean;
  source: "computed" | "csv_latest" | "database" | "missing";
  item?: RsRatingItem | null;
};

export type StockAssessmentCheck = {
  category: "fundamental" | "technical" | "trend" | "risk";
  label: string;
  passed: boolean;
  detail: string;
  severity: "info" | "warning" | "critical";
};

export type StockAssessmentSignal = {
  category: "positive" | "negative" | "neutral";
  label: string;
  detail: string;
  key?: string;
  source?: string;
  score_relevant?: boolean;
  display_relevant?: boolean;
};

export type AssessmentV2Detail = {
  score?: number | null;
  status?: string;
  available_weight?: number;
  data_coverage?: number;
  data_quality?: string;
  components?: Record<string, {
    score?: number | null;
    status?: string;
    base_weight?: number;
    effective_weight?: number;
    data_quality?: string;
    raw?: Record<string, unknown>;
  }>;
  [key: string]: unknown;
};

export type StockAssessmentSignalState = {
  active: boolean;
  available: boolean;
  detail: string;
};

export type StockAssessmentScores = {
  overall: number;
  technical: number;
  fundamental: number;
  moving_averages: number;
  chart_behavior: number;
};

export type StockAssessmentMetrics = {
  last_close?: number | null;
  change_pct?: number | null;
  atr_pct?: number | null;
  volume_ratio_50d?: number | null;
  dollar_volume_mio?: number | null;
  cmf_20?: number | null;
  drawdown_52w_pct?: number | null;
  distance_sma10_pct?: number | null;
  distance_ema21_pct?: number | null;
  distance_sma50_pct?: number | null;
  distance_sma200_pct?: number | null;
  rs_rating?: number | null;
  rs_percentile?: number | null;
  beta?: number | null;
  next_earnings_calendar_days?: number | null;
  next_earnings_trading_days?: number | null;
};

export type StockFundamentalsEpsQuarter = {
  fiscal_period: string;
  fiscal_year?: string;
  period_end_date?: string | null;
  period_key?: string | null;
  report_date?: string | null;
  eps_current_quarter?: number | null;
  eps_same_quarter_last_year?: number | null;
  eps_growth_yoy_pct?: number | null;
  flag?: string | null;
};

export type StockFundamentalsAnnualEps = {
  fiscal_year: string;
  eps_current_year?: number | null;
  eps_previous_year?: number | null;
  eps_growth_yoy_pct?: number | null;
  flag?: string | null;
};

export type StockFundamentalsRevenueQuarter = {
  fiscal_period: string;
  fiscal_year?: string;
  period_end_date?: string | null;
  period_key?: string | null;
  report_date?: string | null;
  revenue_current_quarter?: number | null;
  revenue_same_quarter_last_year?: number | null;
  revenue_growth_yoy_pct?: number | null;
  flag?: string | null;
};

export type StockFundamentalsAnnualRevenue = {
  fiscal_year: string;
  revenue_current_year?: number | null;
  revenue_previous_year?: number | null;
  revenue_growth_yoy_pct?: number | null;
  flag?: string | null;
};

export type StockFundamentalsRoeYear = {
  fiscal_year: string;
  roe_pct?: number | null;
  net_income?: number | null;
  shareholders_equity?: number | null;
  flag?: string | null;
};

export type StockFundamentalsItem = {
  ticker: string;
  as_of: string;
  source: string;
  fiscal_period: string;
  quarterly_eps_growth_pct?: number | null;
  annual_eps_growth_pct?: number | null;
  quarterly_revenue_growth_pct?: number | null;
  annual_revenue_growth_pct?: number | null;
  roe_pct?: number | null;
  profit_margin_pct?: number | null;
  trailing_eps?: number | null;
  quarterly_eps_accelerating?: boolean | null;
  quarterly_revenue_accelerating?: boolean | null;
  institutional_13f_holders?: number | null;
  institutional_holders_delta?: number | null;
  institutional_large_holders?: number | null;
  institutional_large_holders_delta?: number | null;
  institutional_report_period?: string | null;
  next_earnings_date?: string | null;
  beta?: number | null;
  eps_quarter_history: StockFundamentalsEpsQuarter[];
  annual_eps_history: StockFundamentalsAnnualEps[];
  revenue_quarter_history: StockFundamentalsRevenueQuarter[];
  annual_revenue_history: StockFundamentalsAnnualRevenue[];
  roe_history: StockFundamentalsRoeYear[];
};

export type StockFundamentals = {
  ticker: string;
  source: "database" | "missing";
  item?: StockFundamentalsItem | null;
};

export type StockFundamentalsUpdate = {
  as_of?: string | null;
  source?: string;
  fiscal_period?: string;
  quarterly_eps_growth_pct?: number | null;
  annual_eps_growth_pct?: number | null;
  quarterly_revenue_growth_pct?: number | null;
  annual_revenue_growth_pct?: number | null;
  roe_pct?: number | null;
  profit_margin_pct?: number | null;
  trailing_eps?: number | null;
  quarterly_eps_accelerating?: boolean | null;
  quarterly_revenue_accelerating?: boolean | null;
  next_earnings_date?: string | null;
  beta?: number | null;
  eps_quarter_history?: StockFundamentalsEpsQuarter[];
  annual_eps_history?: StockFundamentalsAnnualEps[];
  revenue_quarter_history?: StockFundamentalsRevenueQuarter[];
  annual_revenue_history?: StockFundamentalsAnnualRevenue[];
  roe_history?: StockFundamentalsRoeYear[];
};

export type StockEarningsWarning = {
  next_earnings_date?: string | null;
  calendar_days?: number | null;
  trading_days?: number | null;
  tone: Tone;
  message: string;
};

export type StockAssessment = {
  data_quality?: Record<string, { status: string; label: string; as_of?: string | null; fetched_at?: string | null; expected?: string }>;
  ticker: string;
  as_of: string;
  source: "database" | "missing";
  data_status: "fresh" | "stale" | "missing";
  message: string;
  verdict_label: string;
  verdict_tone: Tone;
  verdict_text: string;
  fundamentals_available: boolean;
  scores: StockAssessmentScores;
  metrics: StockAssessmentMetrics;
  fundamentals?: StockFundamentalsItem | null;
  earnings?: StockEarningsWarning | null;
  checks: StockAssessmentCheck[];
  chart_signals: StockAssessmentSignal[];
  chart_signal_states?: Record<string, StockAssessmentSignalState>;
  drivers: string[];
  warnings: string[];
  overall_v2?: AssessmentV2Detail;
  technical_v2?: AssessmentV2Detail;
  fundamental_v2?: AssessmentV2Detail;
  chart_v2?: AssessmentV2Detail;
  moving_average_v2?: AssessmentV2Detail;
  setup?: Record<string, unknown>;
  eligibility?: Record<string, unknown>;
};

export type StockAssessmentRankingItem = {
  ticker: string;
  name: string;
  as_of: string;
  last_close?: number | null;
  verdict_label: string;
  verdict_tone: Tone;
  overall_score: number;
  technical_score: number;
  fundamental_score: number;
  moving_average_score: number;
  chart_behavior_score: number;
  overall_status?: "available" | "limited";
  available_weight?: number;
  rs_rating?: number | null;
  dollar_volume_mio?: number | null;
  atr_pct?: number | null;
  warnings_count: number;
  top_warning: string;
  top_driver: string;
};

export type StockAssessmentRanking = {
  as_of: string;
  source: "database" | "missing";
  total_count: number;
  limit: number;
  rows: StockAssessmentRankingItem[];
};

export type StockScreeningItem = StockAssessmentRankingItem & {
  checks: StockAssessmentCheck[];
  fundamentals_available: boolean;
  rs_line_available: boolean;
  institutional_available: boolean;
  prices_stale: boolean;
};

export type StockScreening = {
  total_count: number;
  criteria: string[];
  summary: {
    universe_count?: number;
    records_written?: number;
    missing_count?: number;
    error_count?: number;
    reused_count?: number;
    calculated_count?: number;
    stale_count?: number;
    duration_seconds?: number;
    generated_at?: string;
  };
  rows: StockScreeningItem[];
};

export type TopDailyStockItem = {
  rank: number;
  previous_rank: number | null;
  ticker: string;
  name: string;
  last_close: number | null;
  daily_opportunity_score: number;
  quality_score: number;
  daily_dynamics_score: number;
  overall_score: number;
  overall_score_delta: number | null;
  technical_score: number;
  technical_score_delta: number | null;
  fundamental_score: number;
  moving_average_score: number;
  chart_behavior_score: number;
  overall_status?: "available" | "limited";
  available_weight?: number;
  rs_rating: number | null;
  rs_rating_delta: number | null;
  relative_performance_1d: number | null;
  relative_performance_5d: number | null;
  volume_ratio: number | null;
  dollar_volume_mio: number | null;
  positive_changes: string[];
  reasons: string[];
  warnings: string[];
};

export type TopDailyStockResponse = {
  as_of: string | null;
  generated_at: string | null;
  status: "current" | "stale" | "not_ready";
  rows: TopDailyStockItem[];
};

export type StockAssessmentCompareItem = {
  rank: number;
  ticker: string;
  name: string;
  as_of: string;
  source: "database" | "missing";
  data_status: "fresh" | "stale" | "missing";
  verdict_label: string;
  verdict_tone: Tone;
  overall_score: number;
  technical_score: number;
  fundamental_score: number;
  moving_average_score: number;
  chart_behavior_score: number;
  price?: number | null;
  perf_1m_pct?: number | null;
  perf_3m_pct?: number | null;
  perf_6m_pct?: number | null;
  drawdown_52w_pct?: number | null;
  atr_pct?: number | null;
  beta?: number | null;
  rs_rating?: number | null;
  above_sma10?: boolean | null;
  above_ema21?: boolean | null;
  above_sma50?: boolean | null;
  above_sma200?: boolean | null;
  ma_order?: boolean | null;
  fundamental_criteria_passed: number;
  fundamental_criteria_total: number;
  fundamental_positive: number;
  fundamental_negative: number;
  fundamental_neutral: number;
  technical_positive: number;
  technical_negative: number;
  technical_neutral: number;
  chart_positive: number;
  chart_negative: number;
  chart_neutral: number;
  top_driver: string;
  top_warning: string;
};

export type StockAssessmentCompare = {
  as_of: string;
  source: "database" | "partial" | "missing";
  requested_tickers: string[];
  missing_tickers: string[];
  rows: StockAssessmentCompareItem[];
};

export type Institutional13FTrendItem = {
  ticker: string;
  cusip: string;
  report_period: string;
  previous_period?: string | null;
  holder_count: number;
  previous_holder_count?: number | null;
  holder_count_delta?: number | null;
  large_holder_count?: number | null;
  previous_large_holder_count?: number | null;
  large_holder_delta?: number | null;
  total_value_usd?: number | null;
  previous_total_value_usd?: number | null;
  total_value_delta_pct?: number | null;
  total_shares?: number | null;
  previous_total_shares?: number | null;
  total_shares_delta_pct?: number | null;
  trend: "positive" | "negative" | "neutral" | "new" | "missing";
  source_url: string;
};

export type Institutional13FTrend = {
  ticker: string;
  source: "database" | "missing";
  as_of: string;
  item?: Institutional13FTrendItem | null;
};

export type Sec13FMappingItem = {
  cusip: string;
  ticker: string;
  issuer_name: string;
  source: string;
  confidence?: number | null;
  updated_at?: string | null;
};

export type Sec13FUnmatchedCusipItem = {
  cusip: string;
  issuer: string;
  title: string;
  reason: string;
  candidate_tickers: string;
  current_holder_count?: number | null;
  current_total_value_usd?: number | null;
};

export type Sec13FMappingReview = {
  source: "database" | "missing";
  as_of: string;
  mappings: Sec13FMappingItem[];
  unmatched: Sec13FUnmatchedCusipItem[];
  unmatched_source_job_id: string;
};

export type Sec13FMappingUpdate = {
  cusip: string;
  ticker: string;
  issuer_name?: string;
};

export type SellRankingRow = {
  ticker: string;
  name: string;
  pnl_pct: number;
  health_score: number;
  recommendation_pct: number;
  status: "Halten" | "Beobachten" | "Verkaufen";
  reason: string;
  pending_status: PendingStatus;
  primary_signal: string;
  last_seen_date: string;
  consecutive_days: number;
  snoozed_until: string;
  snoozed_pct: number;
  data_quality_status: "trusted" | "limited" | "blocked";
  data_quality_detail: string;
};

export type SellRankingResponse = {
  rows: SellRankingRow[];
  source: "snapshot" | "live";
  generated_at: string;
  source_job_id: string;
  message: string;
};

export type PendingStatus = "halten" | "in_bestaetigung" | "snoozed" | "scharf";

export type SellManualInput = {
  ticker: string;
  pivot?: number | null;
  low_day_1?: number | null;
  low_day_0?: number | null;
  market_environment: "Bullisch" | "Unsicher" | "Bärisch";
  industry_group_status: "Stark" | "Neutral" | "Schwach";
  personality_changed: boolean;
  strength_checkboxes: Record<string, boolean>;
  warning_checkboxes: Record<string, boolean>;
  sell_setup: Record<string, unknown>;
  use_global_sell_setup?: boolean | null;
};

export type SellRecommendationState = {
  last_seen_date: string;
  last_pct: number;
  consecutive_days: number;
  snoozed_until: string;
  snoozed_pct: number;
};

export type TrancheLogEntry = {
  ticker: string;
  date: string;
  pct: number;
  reason: string;
  price?: number | null;
  shares?: number | null;
  source: string;
  created_at: string;
};

export type SellSignal = {
  id: string;
  label: string;
  contribution_percent: number;
  signal_date: string;
  event_note: string;
  sell_mode: string;
  sell_style: string;
  strategy_key: string;
  severity: "watch" | "warning" | "tranche" | "killer";
  book_reference: string;
};

export type SellRuleFeature = {
  id: string;
  category: "emergency" | "offensive" | "defensive";
  label: string;
  active: boolean;
  severity: "inactive" | "watch" | "warning" | "tranche" | "killer";
  value: string;
  threshold: string;
  detail: string;
  signal_date: string;
  contribution_percent: number;
  strategy_key: string;
  setup: Record<string, unknown>;
  strategy_selected?: boolean;
  recommendation_contribution_percent?: number;
  recommendation_effect?: string;
};

export type SellStrategyRecommendation = {
  id: string;
  label: string;
  active: boolean;
  tranche_percent: number;
  detail: string;
  trigger: string;
  feature_ids: string[];
};

export type SellStrategyResult = {
  strategy_key: string;
  label: string;
  description: string;
  recommendation_percent: number;
  recommendations: SellStrategyRecommendation[];
};

export type SellHealthScore = {
  health_score: number;
  status: "Halten" | "Beobachten" | "Verkaufen";
  rs_trend: "hoch" | "seitwärts" | "seitwaerts" | "runter";
  reasons: string[];
};

export type SellRsChartPoint = {
  date: string;
  rs: number;
  rs_ma21?: number | null;
  rs_ma50?: number | null;
};

export type SellMetrics = {
  ticker: string;
  as_of: string;
  current_price?: number | null;
  pnl_pct?: number | null;
  ema21?: number | null;
  sma50?: number | null;
  sma200?: number | null;
  atr14?: number | null;
  days_under_ema21: number;
  distribution_days_25: number;
  rs_trend: "hoch" | "seitwaerts" | "runter";
  health: SellHealthScore;
  manual_defaults: Record<string, unknown>;
  auto_checkboxes: Record<string, unknown>;
  raw_payload: {
    ok: boolean;
    error: string;
    ticker: string;
    buy_price: number | null;
    buy_date: string;
    currency: string;
    metrics: Record<string, unknown> & { rs_chart_history?: SellRsChartPoint[] };
  };
};

export type SellEvaluation = {
  ticker: string;
  recommendation_label: "HALTEN" | "TEILVERKAUF" | "KOMPLETTVERKAUF";
  display_label: string;
  regime: string;
  sell_now_percent: number;
  recommendation_percent: number;
  target_total_sold_percent: number;
  already_sold_percent: number;
  remaining_after_sale_percent: number;
  pending_status: PendingStatus;
  explanation_short: string;
  stop_price?: number | null;
  next_tranche_trigger_price?: number | null;
  full_exit_price?: number | null;
  add_again_condition: string;
  sell_mode: string;
  sell_style: string;
  killer_signals: SellSignal[];
  tranche_signals: SellSignal[];
  warning_signals: SellSignal[];
  watch_signals: SellSignal[];
  emergency_features: SellRuleFeature[];
  offensive_features: SellRuleFeature[];
  defensive_features: SellRuleFeature[];
  strategy: SellStrategyResult;
  book_references: Record<string, string>;
  next_recommendation_state: SellRecommendationState;
  health: SellHealthScore;
  manual: SellManualInput;
  tranche_log: TrancheLogEntry[];
};

export type SellLiveMonitorMetric = {
  key: string;
  label: string;
  value: string;
  detail: string;
  tone: Tone;
};

export type SellStrategyDiagnostic = {
  strategy_key: string;
  theme: string;
  label: string;
  status: "clear" | "watch" | "active";
  tone: Tone;
  active_signal_count: number;
  watch_signal_count: number;
  max_contribution_percent: number;
  book_reference: string;
  description: string;
  signals: SellSignal[];
};

export type SellPostMortemCheck = {
  key: string;
  label: string;
  status: "ok" | "review" | "fail";
  tone: Tone;
  evidence: string;
};

export type SellPostMortemNoteStatus = "open" | "done" | "dismissed";

export type SellPostMortemNote = {
  id: string;
  ticker: string;
  check_key: string;
  note: string;
  action: string;
  status: SellPostMortemNoteStatus;
  created_at: string;
  updated_at: string;
};

export type SellPostMortemNoteRequest = {
  check_key: string;
  note: string;
  action: string;
  status: SellPostMortemNoteStatus;
};

export type SellDiagnostics = {
  ticker: string;
  as_of: string;
  price_context: SellLiveMonitorMetric[];
  strategy_hub: SellStrategyDiagnostic[];
  post_mortem: SellPostMortemCheck[];
  post_mortem_notes: SellPostMortemNote[];
  next_action: string;
};

export type Job = {
  job_id: string;
  celery_task_id: string;
  job_type: string;
  status: JobStatus;
  progress: number;
  current_step: string;
  message: string;
  error_message: string;
  requested_by: string;
  payload: Record<string, unknown>;
  created_at: string;
  requested_at: string;
  started_at?: string | null;
  heartbeat_at: string;
  finished_at?: string | null;
  result: Record<string, unknown>;
};

export type JobStatus = "queued" | "running" | "done" | "failed" | "skipped" | "cancelled";

export type JobType =
  | "smart_refresh_market_data"
  | "bootstrap_market_data"
  | "refresh_prices"
  | "refresh_breadth"
  | "refresh_relative_strength"
  | "refresh_stock_assessments"
  | "refresh_industry_group_rs"
  | "refresh_fundamentals"
  | "refresh_earnings_calendar"
  | "refresh_stock_detail"
  | "refresh_universe"
  | "refresh_sec13f"
  | "position_atr_monitor"
  | "pushover_test"
  | "yahoo_symbol_diagnostics"
  | "yahoo_symbol_rescue"
  | "backfill_trade_journal_contexts";

export type AppSettings = {
  atr_threshold: number;
  risk_per_position_pct: number;
  target_risk_contribution: number;
  max_depot_loss_lower_pct: number;
  max_depot_loss_upper_pct: number;
  position_monitor_enabled: boolean;
  position_monitor_interval_minutes: number;
  position_monitor_threshold_atr: number;
  position_monitor_atr_period: number;
  position_monitor_lookback_days: number;
  position_monitor_cooldown_hours: number;
  position_monitor_reference: "high_since_buy" | "close_since_buy" | "entry_price" | "previous_close";
  position_monitor_ma_alerts_enabled: boolean;
  position_monitor_assessment_alerts_enabled: boolean;
  position_monitor_assessment_interval_minutes: number;
  pushover_enabled: boolean;
  pushover_configured: boolean;
  rs_rating_source: "csv_latest" | "computed";
  data_jobs_enabled: boolean;
  market_ampel_logic: "current" | "ibd";
  assessment_score_weights: AssessmentScoreWeights;
  sell_rule_setup: Record<string, unknown>;
};

export type AssessmentScoreWeights = {
  overall: Record<"technical" | "fundamental" | "chart" | "moving_average", number>;
  technical: Record<"k4_rs_leadership" | "k13_rs_dynamics" | "rs_rating" | "high_position" | "up_down_volume" | "cmf", number>;
  fundamental: Record<"fundamental_core" | "k9_eps_sales_alignment", number>;
  chart: Record<"price_action_core" | "k35_down_week_quality" | "k38_hh_hl_good_close", number>;
  moving_average: Record<"price_above_200_sma" | "price_above_50_sma" | "price_above_21_ema" | "price_above_10_sma" | "ma_order" | "persistence" | "slope", number>;
};

export type RuntimeConfigItem = {
  key: string;
  label: string;
  category: "external_api" | "notifications" | "database" | "security" | "deployment";
  description: string;
  configured: boolean;
  source: "database" | "environment" | "missing" | "bootstrap_only";
  secret: boolean;
  editable: boolean;
  restart_required: boolean;
  runtime_applied: boolean;
  placeholder: string;
  value_preview: string;
};

export type RuntimeConfig = {
  items: RuntimeConfigItem[];
  editable_keys: string[];
  bootstrap_keys: string[];
  note: string;
};

export type RuntimeConfigPatch = {
  values?: Record<string, string>;
  clear_keys?: string[];
};

export type RuntimeConfigTestRequest = {
  key: string;
  value?: string | null;
};

export type RuntimeConfigTestResponse = {
  key: string;
  ok: boolean;
  status: "ok" | "missing" | "invalid" | "failed" | "unsupported";
  detail: string;
  checked_at: string;
  restart_required: boolean;
};

export type DatabaseTarget = "local" | "neon";

export type DatabaseTargetResponse = {
  target: DatabaseTarget;
  running_target: DatabaseTarget;
  restart_required: boolean;
  neon_configured: boolean;
  neon_value_preview: string;
  local_value_preview: string;
  active_value_preview: string;
  message: string;
};

export type DatabaseTargetSwitchRequest = {
  target: DatabaseTarget;
};

export type RuntimeServicesRestartResponse = {
  ok: boolean;
  status: "scheduled" | "disabled" | "failed";
  detail: string;
  services: string[];
  started_at: string;
};

export type DataDiagnosticIssue = {
  key: string;
  label: string;
  severity: "info" | "warning" | "critical";
  detail: string;
  tickers: string[];
  action_label: string;
  job_type?: JobType | null;
  job_payload: Record<string, unknown>;
  category: "freshness" | "price" | "fundamental" | "mapping" | "portfolio" | "corporate_action" | "system";
  blocks_decisions: boolean;
};

export type DataQualityEvent = {
  ticker: string;
  event_type: "split_candidate" | "dividend_candidate" | "ticker_mapping";
  event_date: string;
  label: string;
  detail: string;
  severity: "info" | "warning" | "critical";
};

export type DataDiagnostics = {
  as_of: string;
  generated_at: string;
  health_tone: Tone;
  decision_status: "trusted" | "limited" | "blocked";
  summary: string;
  open_positions_count: number;
  price_cache_tickers_count: number;
  missing_price_count: number;
  stale_price_count: number;
  missing_yahoo_symbol_count: number;
  isin_mappings_count: number;
  stop_coverage_count: number;
  stop_coverage_total: number;
  stop_coverage_pct: number;
  missing_fundamentals_count: number;
  missing_risk_metrics_count: number;
  implausible_position_count: number;
  freshness: ServiceFreshness[];
  corporate_events: DataQualityEvent[];
  issues: DataDiagnosticIssue[];
};

export type PushoverDeliveryLogItem = {
  timestamp: string;
  ticker: string;
  status: "sent" | "failed" | "skipped";
  detail: string;
  distance_atr?: number | null;
  threshold_atr?: number | null;
  reference_label: string;
};

export type PushoverDeliveryLog = {
  entries: PushoverDeliveryLogItem[];
};

export type StockSearchItem = {
  ticker: string;
  name: string;
  yahoo_symbol: string;
  exchange: string;
};

export type StockSearchResponse = {
  query: string;
  rows: StockSearchItem[];
};

export type StockSignalChange = {
  kind: "new" | "resolved" | "unchanged";
  category: string;
  label: string;
  detail: string;
};

export type StockSignalChanges = {
  ticker: string;
  current_as_of: string;
  previous_as_of: string;
  changes: StockSignalChange[];
};

export type WorkspaceState = {
  source: "database" | "default";
  updated_at?: string | null;
  watchlist: string[];
  todos: string;
  recent_tickers: string[];
};

export type WorkspacePatch = {
  watchlist?: string[];
  todos?: string;
  recent_tickers?: string[];
};

export type HomeDashboard = {
  generated_at: string;
  as_of?: string | null;
  data_quality?: { decision_status?: string; summary?: string } | null;
  errors: string[];
  market: {
    logic?: "current" | "ibd";
    summary?: string;
    status?: "available" | "partial" | "missing";
    session?: {
      phase: "open" | "closed" | "unknown";
      last_completed_as_of?: string | null;
      current_session_as_of?: string | null;
    };
    phase?: string | null;
    phase_label?: string | null;
    warning_count?: number | null;
    breadth?: { as_of?: string | null; pct_above_50sma?: number | null } | null;
    volatility?: { as_of?: string | null; close?: number | null; status?: string } | null;
    indices: Array<{
      ticker: string;
      label: string;
      as_of?: string | null;
      previous_as_of?: string | null;
      close?: number | null;
      previous_close?: number | null;
      change_pct?: number | null;
      status: "available" | "stale" | "partial" | "missing";
      phase?: string | null;
      phase_label?: string;
      phase_as_of?: string | null;
      phase_status?: "available" | "stale" | "partial" | "missing";
      phase_reason?: string | null;
      powertrend?: Pick<MarketAmpelPowerTrend, "enabled" | "state" | "formal_active" | "start_date" | "pressure_since"> | null;
    }>;
  };
  priorities: Array<{ ticker: string; category: string; label: string; detail: string; href: string; tone: Tone }>;
  priorities_total: number;
  review_positions_count: number;
  opportunities: TopDailyStockItem[];
  changes: Array<{
    ticker: string;
    scopes: Array<"portfolio" | "watchlist" | "top_stocks">;
    kind: "score" | "signal";
    summary: string;
    details: string[];
    as_of?: string | null;
    previous_as_of?: string | null;
    href: string;
  }>;
  portfolio: {
    positions_count: number;
    stop_coverage_count?: number;
    stop_coverage_total?: number;
    daily_price_change_pct?: number | null;
    daily_price_change_as_of?: string | null;
    daily_price_change_status?: "available" | "partial" | "mixed_currency" | "missing";
    comparable_positions?: number;
    positions: Array<{ ticker: string; name: string; pnl_pct: number; has_stop: boolean }>;
  };
  sell_rows: SellRankingRow[];
  industry_groups: Array<Pick<IndustryGroupRankingRow, "code" | "name" | "rank" | "rs_score" | "rank_change_20d">>;
  industry_groups_as_of?: string | null;
  watchlist: Array<(StockAssessmentRankingItem & { data_status: "available" | "missing" | "error"; name?: string; as_of?: string | null })>;
  watchlist_total: number;
};

export type SetupStep = {
  key:
    | "system"
    | "portfolio"
    | "prices"
    | "market_breadth"
    | "relative_strength"
    | "institutional_13f"
    | "atr_monitor";
  label: string;
  status: "complete" | "pending" | "running" | "warning" | "blocked" | "error";
  detail: string;
  action_label: string;
  href: string;
  job_type?: JobType | null;
  job_payload: Record<string, unknown>;
  latest_job?: Job | null;
};

export type SetupStatus = {
  as_of: string;
  status: "ready" | "needs_action" | "running" | "blocked";
  summary: string;
  next_step_key: string;
  steps: SetupStep[];
};

export type IndustryGroupStockRow = {
  ticker: string;
  name: string;
  group_rank: number;
  group_members: number;
  overall_score?: number | null;
  technical_score?: number | null;
  stock_rs?: number | null;
  fundamental_score?: number | null;
  moving_average_score?: number | null;
  chart_behavior_score?: number | null;
  verdict_label?: string | null;
  latest_close?: number | null;
  return_1d?: number | null;
  return_1w?: number | null;
  return_1m?: number | null;
  return_3m?: number | null;
  return_6m?: number | null;
  return_12m?: number | null;
  issuer_representative?: boolean;
  representative_ticker?: string;
};

export type IndustryGroupRankingRow = {
  id: string;
  code: string;
  name: string;
  sector: string;
  industry_family: string;
  snapshot_date: string;
  member_count: number;
  eligible_member_count: number;
  issuer_count: number;
  is_ranked: boolean;
  rank_status: "ranked" | "small_group" | "insufficient_history";
  rank?: number | null;
  ranked_group_count: number;
  rs_score?: number | null;
  rs_1m?: number | null;
  rs_3m?: number | null;
  rs_6m?: number | null;
  rs_12m?: number | null;
  return_1d?: number | null;
  return_1m?: number | null;
  return_3m?: number | null;
  return_6m?: number | null;
  return_12m?: number | null;
  benchmark_return_1m?: number | null;
  benchmark_return_3m?: number | null;
  benchmark_return_6m?: number | null;
  benchmark_return_12m?: number | null;
  excess_return_1m?: number | null;
  excess_return_3m?: number | null;
  excess_return_6m?: number | null;
  excess_return_12m?: number | null;
  rank_5d_ago?: number | null;
  rank_20d_ago?: number | null;
  rank_change_5d?: number | null;
  rank_change_20d?: number | null;
  rs_change_5d?: number | null;
  rs_change_20d?: number | null;
  benchmark_ticker: string;
  top_stock?: IndustryGroupStockRow | null;
};

export type IndustryGroupRankings = {
  as_of: string;
  taxonomy_version: string;
  algorithm_version: string;
  benchmark: string;
  min_group_members_for_rs: number;
  weights: Record<string, number>;
  rows: IndustryGroupRankingRow[];
};

export type IndustryGroupPerformancePoint = {
  date: string;
  group_index: number;
  benchmark_index: number;
};

export type IndustryGroupDetail = {
  group: IndustryGroupRankingRow;
  top_stocks: IndustryGroupStockRow[];
  members: IndustryGroupStockRow[];
  performance_series: IndustryGroupPerformancePoint[];
};

export type IndustryGroupStockContext = {
  group: IndustryGroupRankingRow;
  stock: IndustryGroupStockRow;
  top_stocks: IndustryGroupStockRow[];
};

export type IndustryGroupRsDiagnostics = {
  taxonomy_version: string;
  algorithm_version: string;
  snapshot_date: string;
  benchmark: string;
  min_group_members_for_rs: number;
  total_groups: number;
  ranked_groups: number;
  small_groups: number;
  insufficient_history_groups: number;
  total_members: number;
  eligible_issuers: number;
  missing_1m: number;
  missing_3m: number;
  missing_6m: number;
  missing_12m: number;
  calculation_duration?: number | null;
  weights: Record<string, number>;
  top_10_groups: IndustryGroupRankingRow[];
  bottom_10_groups: IndustryGroupRankingRow[];
  largest_rank_gainers_5d: IndustryGroupRankingRow[];
  largest_rank_gainers_20d: IndustryGroupRankingRow[];
};
