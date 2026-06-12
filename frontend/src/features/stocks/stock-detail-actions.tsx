"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BookmarkPlus, BriefcaseBusiness, CheckCircle2, Clock3, Loader2, TriangleAlert } from "lucide-react";
import type { ReactNode } from "react";
import { useEffect, useMemo, useState } from "react";
import { StatusChip } from "@/components/ui/status-chip";
import { api } from "@/lib/api/client";
import type { PriceHistory, StockAssessment, WorkspaceState } from "@/lib/types/api";

const workspaceKey = ["workspace"];
const portfolioSnapshotKey = ["portfolio-snapshot"];
const portfolioPositionsKey = ["portfolio-positions"];

export function StockDetailActions({ ticker }: { ticker: string }) {
  const clean = normalizeTicker(ticker);
  const queryClient = useQueryClient();
  const [positionSaved, setPositionSaved] = useState(false);

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
      if (!positionDefaults.price) throw new Error("Kein Kurs im Price Cache vorhanden.");
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

  const loadingPrice = assessmentQuery.isLoading || priceQuery.isLoading;
  const canSavePosition = Boolean(clean && positionDefaults.price && !savePositionMutation.isPending);

  return (
    <section className="rounded border border-[#2d333d] bg-[#171a20] p-5">
      <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-base font-semibold">Arbeitsbereich</h2>
            <StatusChip tone={isWatchlisted ? "good" : "neutral"}>{isWatchlisted ? "Watchlist" : "Nicht vorgemerkt"}</StatusChip>
            <StatusChip tone={positionDefaults.price ? "good" : loadingPrice ? "warning" : "bad"}>
              {positionDefaults.price ? "Kurs bereit" : loadingPrice ? "Kurs lädt" : "Kurs fehlt"}
            </StatusChip>
            {positionSaved ? <StatusChip tone="good">Position vorgemerkt</StatusChip> : null}
          </div>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-[#a0a7b4]">
            Schnellaktionen aus der alten Aktienbewertung: Watchlist, zuletzt angesehen und Depot-Vormerkung laufen ohne Seitenreload.
          </p>
        </div>

        <div className="flex flex-col gap-2 sm:flex-row xl:justify-end">
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
        </div>
      </div>

      <div className="mt-4 grid gap-3 md:grid-cols-3">
        <ActionMetric icon={<Clock3 size={16} />} label="Recent" value={clean} detail="Beim Öffnen gespeichert" />
        <ActionMetric label="Einstand" value={positionDefaults.price ? money(positionDefaults.price) : "-"} detail={positionDefaults.date ?? "Price Cache fehlt"} />
        <ActionMetric label="Währung" value={positionDefaults.currency} detail={priceQuery.data?.source === "database" ? "Price Cache" : "Fallback"} />
      </div>

      {(addWatchlistMutation.error || savePositionMutation.error) && (
        <div className="mt-4 flex gap-2 rounded border border-rose-300/30 bg-rose-300/10 p-3 text-sm text-rose-100">
          <TriangleAlert className="mt-0.5 size-4 shrink-0" />
          <span>{errorText(addWatchlistMutation.error ?? savePositionMutation.error)}</span>
        </div>
      )}
    </section>
  );
}

function ActionMetric({
  icon,
  label,
  value,
  detail
}: {
  icon?: ReactNode;
  label: string;
  value: string;
  detail: string;
}) {
  return (
    <div className="rounded border border-[#242a33] bg-[#111419] p-4">
      <div className="mb-2 flex items-center gap-2 text-xs uppercase text-[#a0a7b4]">
        {icon}
        {label}
      </div>
      <div className="text-xl font-semibold tabular-nums">{value}</div>
      <div className="mt-1 text-xs text-[#7f8794]">{detail}</div>
    </div>
  );
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

function today() {
  return new Date().toISOString().slice(0, 10);
}

function money(value: number) {
  return new Intl.NumberFormat("de-DE", { maximumFractionDigits: 2, minimumFractionDigits: 2 }).format(value);
}

function errorText(error: unknown) {
  return error instanceof Error ? error.message : "Aktion fehlgeschlagen. Die Oberfläche bleibt bedienbar.";
}
