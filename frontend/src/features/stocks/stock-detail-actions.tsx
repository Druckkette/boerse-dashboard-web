"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BookmarkPlus, BriefcaseBusiness, CheckCircle2, Loader2, RefreshCw, TriangleAlert } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { StatusChip } from "@/components/ui/status-chip";
import { api } from "@/lib/api/client";
import type { Job, PriceHistory, StockAssessment, WorkspaceState } from "@/lib/types/api";

const workspaceKey = ["workspace"];
const portfolioSnapshotKey = ["portfolio-snapshot"];
const portfolioPositionsKey = ["portfolio-positions"];

export function StockDetailActions({ ticker }: { ticker: string }) {
  const clean = normalizeTicker(ticker);
  const queryClient = useQueryClient();
  const [positionSaved, setPositionSaved] = useState(false);
  const [refreshJobId, setRefreshJobId] = useState<string | null>(null);
  const handledRefreshJobId = useRef<string | null>(null);
  const autoPriceRefreshTicker = useRef<string | null>(null);

  const workspaceQuery = useQuery({ queryKey: workspaceKey, queryFn: api.workspace, staleTime: 30_000 });
  const assessmentQuery = useQuery({
    queryKey: ["stock-assessment", clean],
    queryFn: () => api.stockAssessment(clean),
    enabled: Boolean(clean),
    staleTime: 60_000
  });
  const priceQuery = useQuery({
    queryKey: ["stock-prices", clean, "1y"],
    queryFn: () => api.stockPrices(clean, "1y"),
    enabled: Boolean(clean),
    staleTime: 60_000
  });
  const fundamentalsQuery = useQuery({
    queryKey: ["stock-fundamentals", clean],
    queryFn: () => api.stockFundamentals(clean),
    enabled: Boolean(clean),
    staleTime: 60_000
  });
  const rsQuery = useQuery({
    queryKey: ["stock-rs", clean],
    queryFn: () => api.stockRs(clean),
    enabled: Boolean(clean),
    staleTime: 60_000
  });
  const institutionalQuery = useQuery({
    queryKey: ["institutional-13f", clean],
    queryFn: () => api.stockInstitutional13F(clean),
    enabled: Boolean(clean),
    staleTime: 5 * 60_000
  });
  const refreshJobQuery = useQuery({
    queryKey: ["job", refreshJobId],
    queryFn: () => api.job(refreshJobId ?? ""),
    enabled: Boolean(refreshJobId),
    refetchInterval: (query) => {
      const job = query.state.data as Job | undefined;
      return job && isTerminalJob(job) ? false : 1500;
    }
  });

  useEffect(() => {
    if (!clean) return;
    void api
      .addRecentTicker(clean)
      .then((state) => {
        queryClient.setQueryData(workspaceKey, state);
      })
      .catch(() => undefined);
  }, [clean, queryClient]);

  const workspace = workspaceQuery.data;
  const isWatchlisted = Boolean(workspace?.watchlist.includes(clean));
  const positionDefaults = useMemo(
    () => buildPositionDefaults(clean, assessmentQuery.data, priceQuery.data),
    [clean, assessmentQuery.data, priceQuery.data]
  );

  const addWatchlistMutation = useMutation({
    mutationFn: () => api.addWorkspaceTicker(clean),
    onMutate: async () => {
      if (!clean) return {};
      await queryClient.cancelQueries({ queryKey: workspaceKey });
      const previous = queryClient.getQueryData<WorkspaceState>(workspaceKey);
      queryClient.setQueryData<WorkspaceState>(workspaceKey, optimisticWorkspace(previous, { watchlist: prependTicker(previous?.watchlist, clean) }));
      return { previous };
    },
    onError: (_error, _variables, context) => {
      if (context?.previous) queryClient.setQueryData(workspaceKey, context.previous);
    },
    onSuccess: (state) => queryClient.setQueryData(workspaceKey, state),
    onSettled: () => queryClient.invalidateQueries({ queryKey: workspaceKey })
  });

  const savePositionMutation = useMutation({
    mutationFn: () => {
      if (!positionDefaults.price) throw new Error("Kein gespeicherter Kurs vorhanden.");
      return api.upsertPortfolioPosition({
        ticker: clean,
        name: clean,
        shares: 1,
        entry_price: positionDefaults.price,
        current_price: positionDefaults.price,
        currency: positionDefaults.currency,
        buy_date: positionDefaults.date,
        pivot_tag: positionDefaults.date,
        stop_pct: 7,
        note: "Aus der Aktienbewertung vorgemerkt.",
        record_transaction: false
      });
    },
    onSuccess: () => {
      setPositionSaved(true);
      queryClient.invalidateQueries({ queryKey: portfolioSnapshotKey });
      queryClient.invalidateQueries({ queryKey: portfolioPositionsKey });
    }
  });
  const refreshStockMutation = useMutation({
    mutationFn: (options?: { includePrices?: boolean; include13f?: boolean }) =>
      api.startJob({
        type: "refresh_stock_detail",
        payload: {
          ticker: clean,
          range: "2y",
          benchmark_ticker: "SPY",
          include_prices: options?.includePrices ?? true,
          include_fundamentals: true,
          include_rs: true,
          include_13f: options?.include13f ?? true,
          incremental: true,
          source: "stock_detail"
        }
      }),
    onSuccess: (job) => {
      setRefreshJobId(job.job_id);
      handledRefreshJobId.current = null;
      void queryClient.invalidateQueries({ queryKey: ["jobs"] });
    }
  });
  const refreshPriceMutation = useMutation({
    mutationFn: () => api.refreshStockPrices(clean, "1y"),
    onSuccess: (payload) => {
      queryClient.setQueryData(["stock-prices", clean, "1y"], payload.history);
      void queryClient.invalidateQueries({ queryKey: ["stock-assessment", clean] });
      void queryClient.invalidateQueries({ queryKey: ["stock-assessment-ranking"] });
    }
  });

  useEffect(() => {
    const job = refreshJobQuery.data;
    if (!job || !isTerminalJob(job) || handledRefreshJobId.current === job.job_id) return;
    handledRefreshJobId.current = job.job_id;
    void queryClient.invalidateQueries({ queryKey: ["stock-prices", clean] });
    void queryClient.invalidateQueries({ queryKey: ["stock-fundamentals", clean] });
    void queryClient.invalidateQueries({ queryKey: ["stock-assessment", clean] });
    void queryClient.invalidateQueries({ queryKey: ["stock-rs", clean] });
    void queryClient.invalidateQueries({ queryKey: ["institutional-13f", clean] });
    void queryClient.invalidateQueries({ queryKey: ["stock-assessment-ranking"] });
    void queryClient.invalidateQueries({ queryKey: ["jobs"] });
  }, [clean, queryClient, refreshJobQuery.data]);

  useEffect(() => {
    if (!clean || autoPriceRefreshTicker.current === clean || refreshPriceMutation.isPending) return;
    if (typeof window === "undefined") return;
    const storageKey = `stock-detail-price-refresh:${clean}`;
    if (window.sessionStorage.getItem(storageKey)) return;
    autoPriceRefreshTicker.current = clean;
    window.sessionStorage.setItem(storageKey, "1");
    refreshPriceMutation.mutate();
  }, [clean, refreshPriceMutation]);

  const loadingPrice = assessmentQuery.isLoading || priceQuery.isLoading;
  const canSavePosition = Boolean(clean && positionDefaults.price && !savePositionMutation.isPending);
  const refreshJob = refreshJobQuery.data;
  const refreshRunning = Boolean(refreshJob && !isTerminalJob(refreshJob));
  const priceRefreshRunning = refreshPriceMutation.isPending;
  const detailDataLoading =
    priceQuery.isLoading || fundamentalsQuery.isLoading || rsQuery.isLoading || institutionalQuery.isLoading;
  const detailDataMissing =
    priceQuery.data?.source !== "database" ||
    !fundamentalsQuery.data?.item ||
    !rsQuery.data?.found ||
    !institutionalQuery.data?.item;
  const blockingDetailDataMissing =
    priceQuery.data?.source !== "database" ||
    !fundamentalsQuery.data?.item ||
    !rsQuery.data?.found;

  useEffect(() => {
    if (!clean || detailDataLoading || !blockingDetailDataMissing || refreshRunning || refreshStockMutation.isPending || refreshJobId) return;
    const storageKey = `stock-detail-refresh:${clean}:${today()}`;
    if (typeof window !== "undefined" && window.sessionStorage.getItem(storageKey)) return;
    if (typeof window !== "undefined") window.sessionStorage.setItem(storageKey, "1");
    refreshStockMutation.mutate({ includePrices: false, include13f: false });
  }, [
    blockingDetailDataMissing,
    clean,
    detailDataLoading,
    refreshJobId,
    refreshRunning,
    refreshStockMutation
  ]);

  return (
    <section className="rounded border border-[#2d333d] bg-[#171a20] p-5">
      <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-base font-semibold">Arbeitsbereich</h2>
            <StatusChip tone={isWatchlisted ? "good" : "neutral"}>{isWatchlisted ? "Watchlist" : "Nicht vorgemerkt"}</StatusChip>
            <StatusChip tone={priceRefreshRunning ? "warning" : positionDefaults.price ? "good" : loadingPrice ? "warning" : "bad"}>
              {priceRefreshRunning ? "Kurs wird geprüft" : positionDefaults.price ? "Kurs bereit" : loadingPrice ? "Kurs lädt" : "Kurs fehlt"}
            </StatusChip>
            <StatusChip tone={!detailDataMissing ? "good" : refreshRunning ? "warning" : "neutral"}>
              {!detailDataMissing ? "Daten vollständig" : refreshRunning ? "Daten werden ergänzt" : "Daten fehlen"}
            </StatusChip>
            {positionSaved ? <StatusChip tone="good">Position vorgemerkt</StatusChip> : null}
          </div>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-[#a0a7b4]">
            Schnellaktionen aus der alten Aktienbewertung: Watchlist, Kursrefresh und Depot-Vormerkung laufen ohne Seitenreload.
          </p>
        </div>

        <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap xl:justify-end">
          <div className="flex min-w-[235px] flex-col gap-1">
            <button
              className="inline-flex items-center justify-center gap-2 rounded border border-cyan-300/40 bg-cyan-300/10 px-4 py-2 text-sm text-cyan-100 hover:border-cyan-200 disabled:cursor-not-allowed disabled:opacity-50"
              disabled={!clean || priceRefreshRunning}
              type="button"
              onClick={() => refreshPriceMutation.mutate()}
            >
              {priceRefreshRunning ? <Loader2 className="size-4 animate-spin" /> : <RefreshCw size={16} />}
              {priceRefreshRunning ? "yfinance prüft" : "Kursdaten aktualisieren"}
            </button>
            <span className="text-xs leading-5 text-[#8e97a6]">{priceDataStatus(priceQuery.data, priceRefreshRunning)}</span>
          </div>
          <button
            className="inline-flex items-center justify-center gap-2 rounded border border-emerald-300/40 bg-emerald-300/10 px-4 py-2 text-sm text-emerald-100 hover:border-emerald-200 disabled:cursor-not-allowed disabled:opacity-50"
            disabled={!clean || addWatchlistMutation.isPending || isWatchlisted}
            type="button"
            onClick={() => addWatchlistMutation.mutate()}
          >
            {addWatchlistMutation.isPending ? <Loader2 className="size-4 animate-spin" /> : isWatchlisted ? <CheckCircle2 size={16} /> : <BookmarkPlus size={16} />}
            {isWatchlisted ? "Auf Watchlist" : "Zur Watchlist"}
          </button>
          <button
            className="inline-flex items-center justify-center gap-2 rounded border border-sky-300/40 bg-sky-300/10 px-4 py-2 text-sm text-sky-100 hover:border-sky-200 disabled:cursor-not-allowed disabled:opacity-50"
            disabled={!canSavePosition}
            type="button"
            onClick={() => savePositionMutation.mutate()}
          >
            {savePositionMutation.isPending ? <Loader2 className="size-4 animate-spin" /> : <BriefcaseBusiness size={16} />}
            Als Position merken
          </button>
          <button
            className="inline-flex items-center justify-center gap-2 rounded border border-amber-300/40 bg-amber-300/10 px-4 py-2 text-sm text-amber-100 hover:border-amber-200 disabled:cursor-not-allowed disabled:opacity-50"
            disabled={!clean || refreshStockMutation.isPending || refreshRunning}
            type="button"
            onClick={() => refreshStockMutation.mutate({ includePrices: true })}
          >
            {refreshStockMutation.isPending || refreshRunning ? <Loader2 className="size-4 animate-spin" /> : <RefreshCw size={16} />}
            {refreshRunning ? "Daten laufen" : "Alle Daten aktualisieren"}
          </button>
        </div>
      </div>

      {(addWatchlistMutation.error || savePositionMutation.error) && (
        <div className="mt-4 flex gap-2 rounded border border-rose-300/30 bg-rose-300/10 p-3 text-sm text-rose-100">
          <TriangleAlert className="mt-0.5 size-4 shrink-0" />
          <span>{errorText(addWatchlistMutation.error ?? savePositionMutation.error)}</span>
        </div>
      )}
      {refreshPriceMutation.error && (
        <div className="mt-4 flex gap-2 rounded border border-rose-300/30 bg-rose-300/10 p-3 text-sm text-rose-100">
          <TriangleAlert className="mt-0.5 size-4 shrink-0" />
          <span>{errorText(refreshPriceMutation.error)}</span>
        </div>
      )}
      {(refreshStockMutation.error || (refreshJob && refreshJob.status === "failed")) && (
        <div className="mt-4 flex gap-2 rounded border border-rose-300/30 bg-rose-300/10 p-3 text-sm text-rose-100">
          <TriangleAlert className="mt-0.5 size-4 shrink-0" />
          <span>{refreshJob?.error_message || errorText(refreshStockMutation.error)}</span>
        </div>
      )}
      {refreshJob ? (
        <div className="mt-4 rounded border border-[#242a33] bg-[#111419] p-3 text-sm">
          <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
            <div>
              <div className="font-medium">{refreshJob.current_step || "Aktien-Datenrefresh"}</div>
              <div className="mt-1 text-xs leading-5 text-[#8e97a6]">
                {refreshJob.message || "Kurse, RS und Fundamentals werden für diese Aktie aktualisiert. 13F läuft über Smart Refresh."}
              </div>
            </div>
            <StatusChip tone={refreshJob.status === "done" ? "good" : refreshJob.status === "failed" ? "bad" : "warning"}>
              {refreshJob.progress}%
            </StatusChip>
          </div>
          <div className="mt-3 h-2 overflow-hidden rounded bg-[#242a33]">
            <div className="h-full rounded bg-amber-300" style={{ width: `${refreshJob.progress}%` }} />
          </div>
        </div>
      ) : null}
    </section>
  );
}

function priceDataStatus(history: PriceHistory | undefined, isRefreshing: boolean) {
  if (isRefreshing) return "yfinance wird jetzt abgefragt";
  if (!history) return "Kursstand noch nicht geladen";
  const marketDate = formatDateOnly(history.last_date ?? history.as_of);
  const cacheDate = history.cache_updated_at ? formatDateTime(history.cache_updated_at) : "noch nicht geprüft";
  return `Kursstand ${marketDate} · Cache ${cacheDate}`;
}

function buildPositionDefaults(ticker: string, assessment?: StockAssessment, priceHistory?: PriceHistory) {
  const assessmentPrice = finitePositive(assessment?.metrics.last_close);
  const historyPrice = finitePositive(priceHistory?.last_close);
  const lastPoint = priceHistory?.points.at(-1);
  const lastPointPrice = finitePositive(lastPoint?.close);
  const date = dateOnly(assessment?.as_of) ?? dateOnly(priceHistory?.last_date) ?? dateOnly(lastPoint?.date) ?? today();
  return {
    ticker,
    price: assessmentPrice ?? historyPrice ?? lastPointPrice,
    date,
    currency: priceHistory?.currency || "USD"
  };
}

function optimisticWorkspace(previous: WorkspaceState | undefined, patch: Partial<WorkspaceState>): WorkspaceState {
  return {
    source: previous?.source ?? "default",
    updated_at: previous?.updated_at ?? null,
    watchlist: previous?.watchlist ?? [],
    todos: previous?.todos ?? "",
    recent_tickers: previous?.recent_tickers ?? [],
    ...patch
  };
}

function prependTicker(items: string[] | undefined, ticker: string, limit = 100) {
  return [ticker, ...(items ?? []).filter((item) => item !== ticker)].slice(0, limit);
}

function normalizeTicker(value: string) {
  return value
    .trim()
    .toUpperCase()
    .split("")
    .filter((char) => /[A-Z0-9.-]/.test(char))
    .join("")
    .slice(0, 32);
}

function finitePositive(value: number | null | undefined) {
  return typeof value === "number" && Number.isFinite(value) && value > 0 ? value : undefined;
}

function dateOnly(value: string | null | undefined) {
  if (!value) return undefined;
  return value.slice(0, 10);
}

function formatDateOnly(value: string | null | undefined) {
  const raw = dateOnly(value);
  if (!raw) return "unbekannt";
  const [year, month, day] = raw.split("-");
  if (!year || !month || !day) return raw;
  return `${day}.${month}.${year}`;
}

function formatDateTime(value: string | null | undefined) {
  if (!value) return "unbekannt";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return new Intl.DateTimeFormat("de-DE", {
    dateStyle: "short",
    timeStyle: "short"
  }).format(parsed);
}

function today() {
  return new Date().toISOString().slice(0, 10);
}

function errorText(error: unknown) {
  return error instanceof Error ? error.message : "Aktion fehlgeschlagen. Die Oberfläche bleibt bedienbar.";
}

function isTerminalJob(job: Job) {
  return ["done", "failed", "skipped", "cancelled"].includes(job.status);
}
