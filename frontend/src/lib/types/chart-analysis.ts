export type PatternKind =
  | "cup_with_handle"
  | "cup_without_handle"
  | "double_bottom"
  | "high_tight_flag"
  | "box";
export type PatternParameters = Record<string, number | boolean> & {
  require_volume: boolean;
};
export type ChartPattern = {
  id: string;
  ticker: string;
  name?: string;
  kind: PatternKind;
  label: string;
  start_date: string;
  end_date: string;
  detected_on: string;
  breakout_on: string | null;
  status:
    | "ready"
    | "breakout"
    | "unconfirmed_breakout"
    | "invalidated"
    | "expired";
  pivot: number;
  depth_pct: number;
  duration_days: number;
  volume_ratio: number | null;
  breakout_volume_ratio: number | null;
  parameter_hash: string;
  stale?: boolean;
  price_as_of?: string;
  points: { date: string; value: number; label: string }[];
  checks: string[];
  warnings: string[];
};
export type PatternConfig = {
  parameters: PatternParameters;
  defaults: PatternParameters;
  parameter_hash: string;
  algorithm_version: string;
  patterns: Record<PatternKind, string>;
};
export type PatternResults = {
  available: boolean;
  obsolete: boolean;
  generated_at?: string;
  scanned_count?: number;
  analysed_count?: number;
  skipped_count?: number;
  skipped?: { ticker: string; reason: string }[];
  parameter_hash?: string;
  current_parameter_hash: string;
  total: number;
  offset: number;
  limit: number;
  rows: ChartPattern[];
};
export type PatternChart = {
  ticker: string;
  as_of: string;
  price_as_of: string | null;
  stale: boolean;
  parameter_hash: string;
  diagnostics: string[];
  patterns: ChartPattern[];
  points: {
    date: string;
    open: number | null;
    high: number | null;
    low: number | null;
    close: number | null;
    volume: number | null;
  }[];
};
export const patternLabels: Record<PatternKind, string> = {
  cup_with_handle: "Cup with Handle",
  cup_without_handle: "Cup without Handle",
  double_bottom: "Double Bottom",
  high_tight_flag: "High Tight Flag",
  box: "Box",
};
export const patternStatuses: Record<ChartPattern["status"], string> = {
  ready: "Basis erkannt",
  breakout: "Ausbruch mit Volumen",
  unconfirmed_breakout: "Ausbruch ohne Volumenbestätigung",
  invalidated: "Basis unterschritten",
  expired: "Ohne Ausbruch abgelaufen",
};
