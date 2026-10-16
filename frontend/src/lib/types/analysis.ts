export type AttributionRow = { ticker: string; result: number | null; price_effect: number | null; fx_effect: number | null; costs: number; trading_and_interaction: number | null; opening_value: number | null; ending_value: number | null; status: string };
export type PortfolioAnalysis = {
  as_of: string; currency: string; cash_ratio_pct: number;
  attribution: { model: string; start: string; end: string; currency: string; result: number | null; positions_result: number | null; cash_fx: number | null; other_cash_result: number; external_cash_flow: number; rows: AttributionRow[]; covered_count: number; total_count: number; mismatched_tickers: string[]; note: string; decomposition: string };
  sectors: { name: string; weight_pct: number }[]; industry_groups: { name: string; weight_pct: number }[];
  top_positions: { ticker: string; weight_pct: number }[];
  stops: { ticker: string; currency: string; stop: number | null; distance_pct: number | null; modeled_loss_pct: number | null }[];
  correlations: { left: string; right: string; observations: number; value: number | null }[];
  correlation_note: string;
  earnings: { windows: { days: number; weight_pct: number }[]; missing_weight_pct: number; rows: { ticker: string; date: string; time: string; source: string; date_conflict: boolean; weight_pct: number }[] };
  scenarios: { sector: string; sector_shock_pct: number; sector_impact: number; fx_shock_pct: number; fx_impact: number | null; note: string };
  notes: string[];
};

export type SavedView = { id: string; name: string; scope: string; state: string; version: number; updated_at: string };

export type ResearchResults = {
 manifest: { cutoff: string; generated_at: string; input_sha256: string; recommendation_events: number; files: Record<string, string> };
 horizons: { sessions: number; bps: number; observations: number; recommendation_days: number; tickers: number; stock_net_pct: number | null; benchmark_net_pct: number | null; excess_pp: number | null }[];
 sell_summary: { sample: string; strategy: string; cohorts: number; tickers: number; first_entry: string; last_end: string; mean_net_10bps_pct: number; median_net_10bps_pct: number; win_rate_pct: number; mean_max_drawdown_pct: number; mean_buy_hold_pct: number; mean_spy_pct: number }[];
 notes: string[];
};
export type StockProvenance = { ticker: string; fields: { key: string; label: string; value: number | null; unit: string; source: string | null; observation_date: string | null; retrieved_at: string | null; period: string | null; publication_date?: string | null; formula: string }[]; component_errors: string[]; institutional: { status: string; missing_cause: string; note: string }; notes: string[] };
export type ScoreHistory = { ticker: string; status: string; points: { connect_to_previous?: boolean; as_of: string; score: number; rs: number | null; calculation: { version: string; configuration_hash: string } | null }[]; changes: { id: string; label: string; before: boolean; after: boolean; detail: string }[]; component_changes: { key: string; before: number; after: number; contribution_delta: number }[]; rounding_delta: number | null; score_delta: number | null; note: string };
