import type {
  AppSettings,
  Breadth,
  Freshness,
  Job,
  JobType,
  MarketOverview,
  PriceHistory,
  PriceRange,
  PortfolioImportRequest,
  PortfolioImportResponse,
  PortfolioPosition,
  PortfolioSnapshot,
  RsRatingDetail,
  RsRatingRanking,
  SellEvaluation,
  SellManualInput,
  SellMetrics,
  SellRankingRow,
  TrancheLogEntry,
  Volatility
} from "@/lib/types/api";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    cache: "no-store"
  });
  if (!response.ok) {
    throw new Error(`API request failed: ${response.status} ${response.statusText}`);
  }
  return response.json() as Promise<T>;
}

async function patchJson<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body)
  });
  if (!response.ok) {
    throw new Error(`API request failed: ${response.status} ${response.statusText}`);
  }
  return response.json() as Promise<T>;
}

async function postJson<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body)
  });
  if (!response.ok) {
    throw new Error(`API request failed: ${response.status} ${response.statusText}`);
  }
  return response.json() as Promise<T>;
}

export const api = {
  marketOverview: () => getJson<MarketOverview>("/market/overview"),
  marketBreadth: () => getJson<Breadth>("/market/breadth"),
  marketVolatility: () => getJson<Volatility>("/market/volatility"),
  freshness: () => getJson<Freshness>("/freshness"),
  stockPrices: (ticker: string, range: PriceRange = "1y") =>
    getJson<PriceHistory>(`/stocks/${ticker}/prices?range=${range}`),
  rsRanking: (limit = 100) => getJson<RsRatingRanking>(`/stocks/ratings/rs?limit=${limit}`),
  stockRs: (ticker: string) => getJson<RsRatingDetail>(`/stocks/${ticker}/rs`),
  portfolioPositions: async () => {
    const payload = await getJson<{ positions: PortfolioPosition[] }>("/portfolio/positions");
    return payload.positions;
  },
  portfolioSnapshot: () => getJson<PortfolioSnapshot>("/portfolio/snapshot"),
  importPortfolioPositions: (body: PortfolioImportRequest) =>
    postJson<PortfolioImportResponse>("/portfolio/imports/positions", body),
  sellRanking: async () => {
    const payload = await getJson<{ rows: SellRankingRow[] }>("/sell/positions/ranking");
    return payload.rows;
  },
  sellMetrics: (ticker: string) => getJson<SellMetrics>(`/sell/${ticker}/metrics`),
  sellEvaluation: (ticker: string) => postJson<SellEvaluation>(`/sell/${ticker}/evaluate`),
  patchSellManual: async (ticker: string, body: SellManualInput) => {
    const payload = await patchJson<{ manual: SellManualInput }>(`/sell/${ticker}/manual`, body);
    return payload.manual;
  },
  createSellTranche: (ticker: string, body: Pick<TrancheLogEntry, "ticker" | "pct" | "reason">) =>
    postJson<{ entry: TrancheLogEntry; tranche_log: TrancheLogEntry[] }>(`/sell/${ticker}/tranches`, body),
  snoozeSellSignal: (ticker: string, body: { snoozed_pct: number; days: number }) =>
    postJson<{ state: { snoozed_until: string; snoozed_pct: number } }>(`/sell/${ticker}/snooze`, body),
  jobs: async () => {
    const payload = await getJson<{ jobs: Job[] }>("/jobs");
    return payload.jobs;
  },
  startJob: async (body: { type: JobType; payload?: Record<string, unknown> }) => {
    const payload = await postJson<{ job: Job }>("/jobs", {
      type: body.type,
      payload: body.payload ?? {}
    });
    return payload.job;
  },
  cancelJob: async (jobId: string) => {
    const payload = await postJson<{ job: Job; cancelled: boolean }>(`/jobs/${jobId}/cancel`);
    return payload;
  },
  settings: () => getJson<AppSettings>("/settings"),
  patchSettings: (body: Partial<AppSettings>) => patchJson<AppSettings>("/settings", body)
};
