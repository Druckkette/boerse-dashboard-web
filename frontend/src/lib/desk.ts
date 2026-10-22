import { workspaceRequest as request } from "./api/client";
export type Stage =
  | "discovered"
  | "reviewed"
  | "planned"
  | "purchased"
  | "reviewed_after"
  | "archived";
export const stageLabels: Record<Stage, string> = {
  discovered: "Entdeckt",
  reviewed: "Geprüft",
  planned: "Geplant",
  purchased: "Kauf dokumentiert",
  reviewed_after: "Nachbetrachtet",
  archived: "Archiviert",
};
export type WatchItem = {
  ticker: string;
  note: string;
  tags: string[];
  stage: Exclude<Stage, "archived">;
};
export type Watchlist = { id: string; name: string; items: WatchItem[] };
export type PlanInput = {
  ticker: string;
  account_id: string;
  currency: string;
  entry: number;
  stop: number;
  risk_pct: number;
  fees: number;
  target: number | null;
  thesis: string;
  invalidation: string;
};
export type PlanPreview = {
  preview_hash: string;
  shares: number;
  risk_budget: number;
  planned_risk: number;
  planned_risk_pct: number;
  portfolio_risk_pct: number | null;
  cash_required: number;
  position_weight_pct: number;
  reward_risk: number | null;
  fx_rate: number;
  fx_as_of: string;
  account_currency: string;
  quote_currency: string;
  limited_by: string;
  account_basis?: { currency: string; total_value: number; cash: number };
  assessment: Record<string, unknown>;
};
export type Plan = PlanInput & {
  id: string;
  stage: Stage;
  created_at: string;
  preview: PlanPreview;
  history: { at: string; stage: Stage; note: string; preview?: PlanPreview }[];
};
export type AlertKind =
  | "price_above"
  | "price_below"
  | "rs_below"
  | "stop"
  | "earnings"
  | "data";
export const alertLabels: Record<AlertKind, string> = {
  price_above: "Schlusskurs erreicht obere Schwelle",
  price_below: "Schlusskurs erreicht untere Schwelle",
  rs_below: "RS fällt unter Schwelle",
  stop: "Gespeicherter Stopp erreicht",
  earnings: "Quartalszahlen stehen bevor",
  data: "Datenqualität eingeschränkt",
};
export type AlertInput = {
  name: string;
  ticker: string;
  kind: AlertKind;
  threshold: number;
  repeat_minutes: number;
  quiet_start: string;
  quiet_end: string;
  enabled: boolean;
  push: boolean;
};
export type Alert = AlertInput & {
  id: string;
  checked_at?: string;
  check_status?: string;
  check_detail?: string;
};
export type AlarmHistory = {
  id: string;
  name: string;
  ticker: string;
  kind: AlertKind;
  detail: string;
  as_of: string;
  at: string;
  acknowledged_at: string | null;
  push_status: string;
};
export type CalendarEvent = {
  id: string;
  title: string;
  date: string;
  ticker: string;
  kind: string;
  note: string;
  source: string;
  scope?: string;
  time?: string;
  date_conflict?: boolean;
};
export type Account = {
  id: string;
  name: string;
  currency: string;
  broker: string;
  transaction_count: number;
};
export type DeskState = {
  revision: number;
  watchlists: Watchlist[];
  plans: Plan[];
  alerts: Alert[];
  history: AlarmHistory[];
  events: CalendarEvent[];
  accounts: Account[];
};
export type AccountView = {
  id: string;
  name: string;
  currency: string;
  total_value: number | null;
  cash: number | null;
  as_of?: string;
  data_status: string;
  missing?: string[];
  positions: {
    ticker: string;
    shares: number;
    currency: string;
    current_price: number | null;
    price_as_of: string | null;
    market_value: number | null;
  }[];
  transactions: {
    id: string;
    date: string;
    type: string;
    ticker: string;
    shares: number;
    price: number;
    currency: string;
    amount: number;
    fees?: number;
    tax?: number;
  }[];
};
export type ImportPreview = {
  rows: AccountView["transactions"];
  count: number;
  duplicates: number;
  added: number;
  preview_hash: string;
  committed: boolean;
  state: DeskState;
};
export type Performance = {
  currency: string;
  start: string;
  end: string;
  twr_pct: number | null;
  mwr_annual_pct: number | null;
  max_drawdown_pct: number | null;
  period_result: number | null;
  external_flow: number | null;
  benchmark: string;
  benchmark_return_pct: number | null;
  benchmark_note: string;
  note: string;
  covered_points: number;
  total_points: number;
  complete: boolean;
  points: {
    date: string;
    portfolio_index: number | null;
    benchmark_index?: number | null;
    depot_value: number | null;
  }[];
};
export const deskApi = {
  state: () => request<DeskState>("/state"),
  save: (collection: string, body: unknown, revision: number, id?: string) =>
    request<DeskState>(
      `/${collection}${id ? `/${encodeURIComponent(id)}` : ""}?revision=${revision}`,
      id ? "PUT" : "POST",
      body,
    ),
  remove: (collection: string, id: string, revision: number) =>
    request<DeskState>(
      `/${collection}/${encodeURIComponent(id)}?revision=${revision}`,
      "DELETE",
    ),
  createPlan: (body: PlanInput, revision: number, previewHash: string) =>
    request<DeskState>(
      `/plans?revision=${revision}&preview_hash=${previewHash}`,
      "POST",
      body,
    ),
  transfer: (
    source: string,
    target: string,
    tickers: string[],
    move: boolean,
    revision: number,
  ) =>
    request<DeskState>(`/watchlists/transfer?revision=${revision}`, "POST", {
      source,
      target,
      tickers,
      move,
    }),
  previewPlan: (body: PlanInput) =>
    request<PlanPreview>("/plans/preview", "POST", body),
  planStage: (id: string, stage: Stage, note: string, revision: number) =>
    request<DeskState>(`/plans/${id}/stage?revision=${revision}`, "POST", {
      stage,
      note,
    }),
  fx: (source: string, target: string) =>
    request<{
      source: string;
      target: string;
      rate: number;
      as_of: string;
      provider: string;
    }>(`/fx?source=${source}&target=${target}`),
  check: () => request<DeskState>("/alerts/check", "POST"),
  acknowledge: (id: string, revision: number) =>
    request<DeskState>(
      `/history/${id}/acknowledge?revision=${revision}`,
      "POST",
    ),
  legacyAlerts: () =>
    request<{
      entries: {
        ticker?: string;
        timestamp?: string;
        status?: string;
        detail?: string;
      }[];
    }>("/legacy-alerts"),
  calendar: (days: number, scope: string) =>
    request<{ as_of: string; coverage_note?: string; rows: CalendarEvent[] }>(
      `/calendar?days=${days}&scope=${scope}`,
    ),
  overview: () =>
    request<{
      rows: AccountView[];
      currency: string;
      total_value: number | null;
      missing: string[];
    }>("/accounts/overview"),
  account: (id: string) => request<AccountView>(`/accounts/${id}`),
  importAccount: (
    id: string,
    csv: string,
    revision: number,
    commit = false,
    preview_hash = "",
  ) =>
    request<ImportPreview>(
      `/accounts/${id}/import?revision=${revision}`,
      "POST",
      { csv, commit, preview_hash },
    ),
  performance: (start: string, benchmark: string, accountId = "main") =>
    request<Performance>(
      `/performance?start=${start}&benchmark=${encodeURIComponent(benchmark)}&account_id=${accountId}`,
    ),
};
export const money = (value: number | null | undefined, currency: string) =>
  value == null
    ? "Nicht verfügbar"
    : new Intl.NumberFormat("de-DE", { style: "currency", currency }).format(
        value,
      );
export const percent = (value: number | null | undefined) =>
  value == null
    ? "Nicht verfügbar"
    : `${value.toLocaleString("de-DE", { maximumFractionDigits: 2 })} %`;
