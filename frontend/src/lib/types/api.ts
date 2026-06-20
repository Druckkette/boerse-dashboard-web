export type Tone = "good" | "neutral" | "warning" | "bad";

export type KpiCard = {
  label: string;
  value: string;
  detail: string;
  tone: Tone;
};

export type MarketTrendAmpel = {
  ticker: string;
  as_of: string;
  phase: "rot" | "gelb" | "gruen" | "aufwaertstrend" | "neutral";
  phase_label: string;
  close?: number | null;
  anchor_date?: string | null;
  floor_mark?: number | null;
  startschuss_low?: number | null;
  startschuss_bonus?: boolean | null;
  dist_count_25: number;
  source: "database" | "missing" | "synthetic_fixture";
};

export type MarketOverview = {
  as_of: string;
  source: "database" | "synthetic_fixture" | "missing";
  data_status: "fresh" | "stale" | "missing" | "fallback";
  message: string;
  phase: "rot" | "gelb" | "gruen" | "aufwaertstrend" | "neutral";
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
  key: "rot" | "gelb" | "gruen" | "aufwaertstrend";
  label: string;
  active: boolean;
  rule: string;
  tone: Tone;
};

export type MarketAmpelPhaseInfo = {
  phase: "rot" | "gelb" | "gruen" | "aufwaertstrend" | "neutral";
  label: string;
  reason: string;
  action: string;
  tone: Tone;
};

export type MarketAmpelCycle = {
  anchor_date?: string | null;
  floor_mark?: number | null;
  floor_distance_pct?: number | null;
  startschuss_low?: number | null;
  startschuss_distance_pct?: number | null;
  startschuss_bonus?: boolean | null;
  ma_order?: boolean | null;
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
  phase: "rot" | "gelb" | "gruen" | "aufwaertstrend" | "neutral";
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

export type MarketAmpel = {
  as_of: string;
  ticker: string;
  name: string;
  source: "database" | "missing";
  data_status: "fresh" | "stale" | "missing" | "fallback";
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
  data_status: "fresh" | "stale" | "missing" | "fallback";
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
  vix_ret_5d?: number | null;
  vix_pct_rank_252?: number | null;
  vix_pct_above_sma10?: number | null;
  vix_panic_overextension: boolean;
  vix_regime: string;
  vxx_close?: number | null;
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
  data_status: "fresh" | "stale" | "missing" | "fallback";
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
  as_of: string;
  source: "database" | "synthetic_fixture" | "missing";
  data_status: "fresh" | "stale" | "missing" | "fallback";
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
  atr_pct: number;
  beta: number;
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

export type PortfolioSnapshot = {
  as_of: string;
  total_value: number;
  invested_value: number;
  cash_balance: number;
  cash_ratio_pct: number;
  portfolio_atr_pct: number;
  beta_balancer: number;
  max_depot_loss_pct: number;
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
  data_status: "fresh" | "missing";
  message: string;
  points: PortfolioCurvePoint[];
};

export type PortfolioPositionSizeRequest = {
  depot_value: number;
  risk_per_position_pct: number;
  target_risk_contribution: number;
  buy_price: number;
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
  source: "database" | "synthetic_fallback";
  data_status: "fresh" | "stale" | "missing" | "fallback";
  as_of: string;
  first_date?: string | null;
  last_date?: string | null;
  last_close?: number | null;
  change_pct?: number | null;
  points: PriceBarPoint[];
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
  source: "database" | "missing";
  rows: RsRatingItem[];
};

export type RsRatingDetail = {
  found: boolean;
  source: "database" | "missing";
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
  institutional_ownership_pct?: number | null;
  next_earnings_calendar_days?: number | null;
  next_earnings_trading_days?: number | null;
};

export type StockFundamentalsEpsQuarter = {
  fiscal_period: string;
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
  institutional_holders?: number | null;
  institutional_ownership_pct?: number | null;
  next_earnings_date?: string | null;
  beta?: number | null;
  eps_quarter_history: StockFundamentalsEpsQuarter[];
  annual_eps_history: StockFundamentalsAnnualEps[];
  revenue_quarter_history: StockFundamentalsRevenueQuarter[];
  annual_revenue_history: StockFundamentalsAnnualRevenue[];
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
  institutional_holders?: number | null;
  institutional_ownership_pct?: number | null;
  next_earnings_date?: string | null;
  beta?: number | null;
  eps_quarter_history?: StockFundamentalsEpsQuarter[];
  annual_eps_history?: StockFundamentalsAnnualEps[];
  revenue_quarter_history?: StockFundamentalsRevenueQuarter[];
  annual_revenue_history?: StockFundamentalsAnnualRevenue[];
};

export type StockEarningsWarning = {
  next_earnings_date?: string | null;
  calendar_days?: number | null;
  trading_days?: number | null;
  tone: Tone;
  message: string;
};

export type StockAssessment = {
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
  drivers: string[];
  warnings: string[];
};

export type StockAssessmentRankingItem = {
  ticker: string;
  name: string;
  as_of: string;
  verdict_label: string;
  verdict_tone: Tone;
  overall_score: number;
  technical_score: number;
  fundamental_score: number;
  moving_average_score: number;
  chart_behavior_score: number;
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
  rows: StockAssessmentRankingItem[];
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

export type SellHealthScore = {
  health_score: number;
  status: "Halten" | "Beobachten" | "Verkaufen";
  rs_trend: "hoch" | "seitwärts" | "seitwaerts" | "runter";
  reasons: string[];
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
    metrics: Record<string, unknown>;
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
  | "refresh_fundamentals"
  | "refresh_universe"
  | "refresh_sec13f"
  | "position_atr_monitor"
  | "pushover_test"
  | "yahoo_symbol_diagnostics"
  | "yahoo_symbol_rescue";

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
  pushover_enabled: boolean;
  pushover_configured: boolean;
  rs_rating_source: "csv_latest" | "computed";
  data_jobs_enabled: boolean;
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
};

export type DataDiagnostics = {
  as_of: string;
  health_tone: Tone;
  summary: string;
  open_positions_count: number;
  price_cache_tickers_count: number;
  missing_price_count: number;
  stale_price_count: number;
  missing_yahoo_symbol_count: number;
  isin_mappings_count: number;
  issues: DataDiagnosticIssue[];
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
