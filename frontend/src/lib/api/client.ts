import type {
  AppSettings,
  Breadth,
  DataDiagnostics,
  Freshness,
  Job,
  JobType,
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
  SectorRanking,
  SellDiagnostics,
  StockAssessment,
  StockAssessmentRanking,
  StockFundamentals,
  StockFundamentalsUpdate,
  SellEvaluation,
  SellManualInput,
  SellMetrics,
  SellPostMortemNote,
  SellPostMortemNoteRequest,
  SellRankingRow,
  TrancheLogEntry,
  TradeRepublicTransactionImportRequest,
  TradeRepublicTransactionImportResponse,
  UniverseStatus,
  UniverseSymbolMappingReview,
  UniverseSymbolMappingUpdate,
  Volatility
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
    throw new Error(`API request failed: ${response.status} ${response.statusText}`);
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
    throw new Error(`API request failed: ${response.status} ${response.statusText}`);
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
    throw new Error(`API request failed: ${response.status} ${response.statusText}`);
  }
  return response.json() as Promise<T>;
}

export const api = {
  marketOverview: () => getJson<MarketOverview>("/market/overview"),
  marketBreadth: () => getJson<Breadth>("/market/breadth"),
  marketVolatility: () => getJson<Volatility>("/market/volatility"),
  marketDiagnostics: () => getJson<MarketDiagnostics>("/market/diagnostics"),
  marketUniverse: () => getJson<UniverseStatus>("/market/universe"),
  marketUniverseMappings: (limit = 500) =>
    getJson<UniverseSymbolMappingReview>(`/market/universe/mappings?limit=${limit}`),
  patchMarketUniverseMapping: (body: UniverseSymbolMappingUpdate) =>
    patchJson<UniverseSymbolMappingReview>("/market/universe/mappings", body),
  marketSectors: (mode: "daily" | "weekly" = "daily", periods = 15) =>
    getJson<SectorRanking>(`/market/sectors?mode=${mode}&periods=${periods}`),
  freshness: () => getJson<Freshness>("/freshness"),
  stockPrices: (ticker: string, range: PriceRange = "1y") =>
    getJson<PriceHistory>(`/stocks/${ticker}/prices?range=${range}`),
  rsRanking: (limit = 100) => getJson<RsRatingRanking>(`/stocks/ratings/rs?limit=${limit}`),
  stockRs: (ticker: string) => getJson<RsRatingDetail>(`/stocks/${ticker}/rs`),
  stockAssessment: (ticker: string) => getJson<StockAssessment>(`/stocks/${ticker}/assessment`),
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
  sellRanking: async () => {
    const payload = await getJson<{ rows: SellRankingRow[] }>("/sell/positions/ranking");
    return payload.rows;
  },
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
  dataDiagnostics: () => getJson<DataDiagnostics>("/settings/data-diagnostics"),
  patchSettings: (body: Partial<AppSettings>) => patchJson<AppSettings>("/settings", body)
};
