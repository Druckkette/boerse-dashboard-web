export type Tone = "good" | "neutral" | "warning" | "bad";

export type KpiCard = {
  label: string;
  value: string;
  detail: string;
  tone: Tone;
};

export type MarketOverview = {
  as_of: string;
  phase: "rot" | "gelb" | "gruen" | "aufwaertstrend" | "neutral";
  phase_label: string;
  action: string;
  warning_count: number;
  breadth_mode: "schutz" | "wachsam" | "rueckenwind";
  volatility_regime: string;
  kpis: KpiCard[];
};

export type BreadthPoint = {
  date: string;
  advancers: number;
  decliners: number;
  ad_line: number;
  mcclellan: number;
  pct_above_50sma: number;
  pct_above_200sma: number;
};

export type Breadth = {
  as_of: string;
  universe: string;
  coverage_ratio: number;
  points: BreadthPoint[];
};

export type ServiceFreshness = {
  name: string;
  status: "fresh" | "stale" | "missing";
  as_of: string;
  lag_minutes: number;
};

export type Freshness = {
  generated_at: string;
  services: ServiceFreshness[];
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
  | "refresh_prices"
  | "refresh_breadth"
  | "refresh_relative_strength"
  | "refresh_sec13f"
  | "position_atr_monitor";

export type AppSettings = {
  atr_threshold: number;
  position_monitor_enabled: boolean;
  position_monitor_interval_minutes: number;
  rs_rating_source: "csv_latest" | "computed";
  data_jobs_enabled: boolean;
};
