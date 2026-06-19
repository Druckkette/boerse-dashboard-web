import type {
  AppSettings,
  Breadth,
  DataDiagnostics,
  DatabaseTargetResponse,
  DatabaseTargetSwitchRequest,
  Freshness,
  Job,
  JobType,
  MarketAmpel,
  MarketBreadthOverview,
  MarketDeepAnalysis,
  MarketDiagnostics,
  MarketOverview,
  Institutional13FTrend,
  IsinMappingListResponse,
  IsinMappingPatchRequest,
  PriceHistory,
  PriceRange,
  PortfolioCashFlow,
  PortfolioCashFlowRequest,
  PortfolioCurve,
  PortfolioImportHistoryItem,
  PortfolioImportRequest,
  PortfolioImportResponse,
  PortfolioPosition,
  PortfolioPositionSizeRequest,
  PortfolioPositionSizeResult,
  PortfolioPositionWriteRequest,
  PortfolioSellRequest,
  PortfolioSnapshot,
  PortfolioTransaction,
  RsRatingDetail,
  RsRatingRanking,
  Sec13FMappingReview,
  Sec13FMappingUpdate,
  RuntimeConfig,
  RuntimeConfigPatch,
  RuntimeConfigTestRequest,
  RuntimeConfigTestResponse,
  RuntimeServicesRestartResponse,
  SectorRanking,
  SellDiagnostics,
  StockAssessment,
  StockAssessmentCompare,
  StockAssessmentRanking,
  StockFundamentals,
  StockFundamentalsUpdate,
  SellEvaluation,
  SellManualInput,
  SellMetrics,
  SellPostMortemNote,
  SellPostMortemNoteRequest,
  SellRankingResponse,
  SetupStatus,
  SystemReadiness,
  TrancheLogEntry,
  TradeRepublicTransactionImportRequest,
  TradeRepublicTransactionImportResponse,
  UniverseStatus,
  UniverseSymbolMappingReview,
  UniverseSymbolMappingUpdate,
  Volatility,
  WorkspacePatch,
  WorkspaceState
} from "@/lib/types/api";

const configuredApiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL;

function getApiBaseUrl() {
  if (configuredApiBaseUrl) return configuredApiBaseUrl;
  return "/api/v1";
}

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${getApiBaseUrl()}${path}`, {
    headers: { "Content-Type": "application/json" },
    cache: "no-store"
  });
  if (!response.ok) {
    throw new Error(await errorMessage(response));
  }
  return response.json() as Promise<T>;
}

async function patchJson<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(`${getApiBaseUrl()}${path}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body)
  });
  if (!response.ok) {
    throw new Error(await errorMessage(response));
  }
  return response.json() as Promise<T>;
}

async function deleteJson<T>(path: string): Promise<T> {
  const response = await fetch(`${getApiBaseUrl()}${path}`, {
    method: "DELETE",
    headers: { "Content-Type": "application/json" }
  });
  if (!response.ok) {
    throw new Error(await errorMessage(response));
  }
  return response.json() as Promise<T>;
}

async function postJson<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(`${getApiBaseUrl()}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body)
  });
  if (!response.ok) {
    throw new Error(await errorMessage(response));
  }
  return response.json() as Promise<T>;
}

async function errorMessage(response: Response) {
  const fallback = `API request failed: ${response.status} ${response.statusText}`;
  const contentType = response.headers.get("content-type") ?? "";
  if (!contentType.includes("application/json")) return fallback;

  try {
    const payload = (await response.json()) as {
      detail?: unknown;
      hint?: unknown;
      target_origin?: unknown;
      error?: unknown;
    };
    const detail = typeof payload.detail === "string" ? payload.detail : fallback;
    const hint = typeof payload.hint === "string" ? ` Hinweis: ${payload.hint}` : "";
    const target = typeof payload.target_origin === "string" ? ` Ziel: ${payload.target_origin}.` : "";
    const error = typeof payload.error === "string" ? ` Fehler: ${payload.error}` : "";
    return `${detail}.${target}${hint}${error}`;
  } catch {
    return fallback;
  }
}

export const api = {
  marketOverview: (ticker = "^GSPC") =>
    getJson<MarketOverview>(`/market/overview?ticker=${encodeURIComponent(ticker)}`),
  marketAmpel: (ticker = "SPY", days = 90) =>
    getJson<MarketAmpel>(`/market/ampel?ticker=${encodeURIComponent(ticker)}&days=${days}`),
  marketBreadth: () => getJson<Breadth>("/market/breadth"),
  marketBreadthOverview: (limit = 260, ticker = "^GSPC") =>
    getJson<MarketBreadthOverview>(`/market/breadth-overview?limit=${limit}&ticker=${encodeURIComponent(ticker)}`),
  marketDeepAnalysis: (limit = 260, ticker = "^GSPC") =>
    getJson<MarketDeepAnalysis>(`/market/deep-analysis?limit=${limit}&ticker=${encodeURIComponent(ticker)}`),
  marketVolatility: () => getJson<Volatility>("/market/volatility"),
  marketDiagnostics: (ticker = "^GSPC") =>
    getJson<MarketDiagnostics>(`/market/diagnostics?ticker=${encodeURIComponent(ticker)}`),
  marketUniverse: () => getJson<UniverseStatus>("/market/universe"),
  marketUniverseMappings: (limit = 500) =>
    getJson<UniverseSymbolMappingReview>(`/market/universe/mappings?limit=${limit}`),
  patchMarketUniverseMapping: (body: UniverseSymbolMappingUpdate) =>
    patchJson<UniverseSymbolMappingReview>("/market/universe/mappings", body),
  marketSectors: (mode: "daily" | "weekly" = "daily", periods = 15) =>
    getJson<SectorRanking>(`/market/sectors?mode=${mode}&periods=${periods}`),
  freshness: () => getJson<Freshness>("/freshness"),
  readiness: () => getJson<SystemReadiness>("/readiness"),
  setupStatus: () => getJson<SetupStatus>("/setup/status"),
  stockPrices: (ticker: string, range: PriceRange = "1y") =>
    getJson<PriceHistory>(`/stocks/${ticker}/prices?range=${range}`),
  rsRanking: (limit = 100) => getJson<RsRatingRanking>(`/stocks/ratings/rs?limit=${limit}`),
  stockRs: (ticker: string) => getJson<RsRatingDetail>(`/stocks/${ticker}/rs`),
  stockAssessment: (ticker: string) => getJson<StockAssessment>(`/stocks/${ticker}/assessment`),
  stockAssessmentCompare: (tickers: string[], limit = 12) =>
    getJson<StockAssessmentCompare>(`/stocks/assessment/compare?tickers=${encodeURIComponent(tickers.join(","))}&limit=${limit}`),
  stockAssessmentRanking: (limit = 50) => getJson<StockAssessmentRanking>(`/stocks/assessment/ranking?limit=${limit}`),
  stockFundamentals: (ticker: string) => getJson<StockFundamentals>(`/stocks/${ticker}/fundamentals`),
  updateStockFundamentals: (ticker: string, body: StockFundamentalsUpdate) =>
    patchJson<StockFundamentals>(`/stocks/${ticker}/fundamentals`, body),
  stockInstitutional13F: (ticker: string) => getJson<Institutional13FTrend>(`/stocks/${ticker}/institutional/13f`),
  sec13FMappingReview: (limit = 500) =>
    getJson<Sec13FMappingReview>(`/stocks/institutional/13f/mappings?limit=${limit}`),
  updateSec13FMapping: (body: Sec13FMappingUpdate) =>
    patchJson<Sec13FMappingReview>("/stocks/institutional/13f/mappings", body),
  portfolioPositions: async () => {
    const payload = await getJson<{ positions: PortfolioPosition[] }>("/portfolio/positions");
    return payload.positions;
  },
  portfolioSnapshot: () => getJson<PortfolioSnapshot>("/portfolio/snapshot"),
  portfolioCurve: (days = 370) => getJson<PortfolioCurve>(`/portfolio/curve?days=${days}`),
  portfolioPositionSize: (body: PortfolioPositionSizeRequest) =>
    postJson<PortfolioPositionSizeResult>("/portfolio/position-size", body),
  upsertPortfolioPosition: async (body: PortfolioPositionWriteRequest) => {
    const payload = await postJson<{ position: PortfolioPosition }>("/portfolio/positions", body);
    return payload.position;
  },
  deletePortfolioPosition: (ticker: string) =>
    fetch(`${getApiBaseUrl()}/portfolio/positions/${ticker}`, { method: "DELETE" }).then((response) => {
      if (!response.ok) throw new Error(`API request failed: ${response.status} ${response.statusText}`);
      return response.json() as Promise<{ ticker: string; closed: boolean }>;
    }),
  sellPortfolioPosition: async (ticker: string, body: PortfolioSellRequest) => {
    const payload = await postJson<{
      ticker: string;
      remaining_position?: PortfolioPosition | null;
      transaction: PortfolioTransaction;
      cash_balance: number;
    }>(`/portfolio/positions/${ticker}/sell`, body);
    return payload;
  },
  portfolioTransactions: async (limit = 250) => {
    const payload = await getJson<{ transactions: PortfolioTransaction[] }>(`/portfolio/transactions?limit=${limit}`);
    return payload.transactions;
  },
  portfolioCashFlows: () =>
    getJson<{ cash_flows: PortfolioCashFlow[]; cash_balance: number }>("/portfolio/cash-flows"),
  createPortfolioCashFlow: (body: PortfolioCashFlowRequest) =>
    postJson<{ cash_flow: PortfolioCashFlow; cash_balance: number }>("/portfolio/cash-flows", body),
  portfolioImportHistory: async (limit = 100) => {
    const payload = await getJson<{ imports: PortfolioImportHistoryItem[] }>(`/portfolio/imports?limit=${limit}`);
    return payload.imports;
  },
  isinMappings: () => getJson<IsinMappingListResponse>("/portfolio/isin-mappings"),
  patchIsinMappings: (body: IsinMappingPatchRequest) =>
    patchJson<IsinMappingListResponse>("/portfolio/isin-mappings", body),
  importPortfolioPositions: (body: PortfolioImportRequest) =>
    postJson<PortfolioImportResponse>("/portfolio/imports/positions", body),
  importTradeRepublicTransactions: (body: TradeRepublicTransactionImportRequest) =>
    postJson<TradeRepublicTransactionImportResponse>("/portfolio/imports/tr-transactions", body),
  sellRanking: () => getJson<SellRankingResponse>("/sell/positions/ranking"),
  sellMetrics: (ticker: string) => getJson<SellMetrics>(`/sell/${ticker}/metrics`),
  sellEvaluation: (ticker: string) => postJson<SellEvaluation>(`/sell/${ticker}/evaluate`),
  sellDiagnostics: (ticker: string) => getJson<SellDiagnostics>(`/sell/${ticker}/diagnostics`),
  sellPostMortemNotes: (ticker: string) => getJson<SellPostMortemNote[]>(`/sell/${ticker}/post-mortem`),
  saveSellPostMortemNote: (ticker: string, body: SellPostMortemNoteRequest) =>
    postJson<{ note: SellPostMortemNote; notes: SellPostMortemNote[] }>(`/sell/${ticker}/post-mortem`, body),
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
  runtimeConfig: () => getJson<RuntimeConfig>("/settings/runtime-config"),
  patchRuntimeConfig: (body: RuntimeConfigPatch) => patchJson<RuntimeConfig>("/settings/runtime-config", body),
  testRuntimeConfig: (body: RuntimeConfigTestRequest) =>
    postJson<RuntimeConfigTestResponse>("/settings/runtime-config/test", body),
  databaseTarget: () => getJson<DatabaseTargetResponse>("/settings/database-target"),
  switchDatabaseTarget: (body: DatabaseTargetSwitchRequest) =>
    postJson<DatabaseTargetResponse>("/settings/database-target", body),
  restartRuntimeServices: () =>
    postJson<RuntimeServicesRestartResponse>("/settings/runtime-services/restart"),
  dataDiagnostics: () => getJson<DataDiagnostics>("/settings/data-diagnostics"),
  patchSettings: (body: Partial<AppSettings>) => patchJson<AppSettings>("/settings", body),
  workspace: () => getJson<WorkspaceState>("/workspace"),
  patchWorkspace: (body: WorkspacePatch) => patchJson<WorkspaceState>("/workspace", body),
  addWorkspaceTicker: (ticker: string) => postJson<WorkspaceState>("/workspace/watchlist", { ticker }),
  removeWorkspaceTicker: (ticker: string) => deleteJson<WorkspaceState>(`/workspace/watchlist/${encodeURIComponent(ticker)}`),
  addRecentTicker: (ticker: string) => postJson<WorkspaceState>("/workspace/recent-tickers", { ticker })
};
