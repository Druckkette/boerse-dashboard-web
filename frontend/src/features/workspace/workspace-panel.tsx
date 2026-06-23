"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BookmarkPlus, BriefcaseBusiness, Clock3, ExternalLink, Save, Trash2 } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";
import { StatusChip } from "@/components/ui/status-chip";
import { api } from "@/lib/api/client";
import type { PortfolioPosition, WorkspaceState } from "@/lib/types/api";

const workspaceKey = ["workspace"];
const portfolioKey = ["portfolio-snapshot"];

const emptyWorkspace: WorkspaceState = {
  source: "default",
  updated_at: null,
  watchlist: [],
  todos: "",
  recent_tickers: []
};

export function WorkspacePanel() {
  const queryClient = useQueryClient();
  const workspaceQuery = useQuery({ queryKey: workspaceKey, queryFn: api.workspace, staleTime: 30_000 });
  const portfolioQuery = useQuery({ queryKey: portfolioKey, queryFn: api.portfolioSnapshot, staleTime: 30_000 });
  const workspace = workspaceQuery.data ?? emptyWorkspace;
  const [tickerInput, setTickerInput] = useState("");
  const [todoDraft, setTodoDraft] = useState<{ dirty: boolean; value: string }>({ dirty: false, value: "" });
  const todos = todoDraft.dirty ? todoDraft.value : workspace.todos;

  const addWatchlistMutation = useMutation({
    mutationFn: (ticker: string) => api.addWorkspaceTicker(ticker),
    onMutate: async (ticker) => {
      const clean = normalizeTicker(ticker);
      if (!clean) return {};
      await queryClient.cancelQueries({ queryKey: workspaceKey });
      const previous = queryClient.getQueryData<WorkspaceState>(workspaceKey);
      queryClient.setQueryData<WorkspaceState>(workspaceKey, optimisticWorkspace(previous, { watchlist: prependTicker(previous?.watchlist, clean) }));
      return { previous };
    },
    onError: (_error, _ticker, context) => rollbackWorkspace(queryClient, context?.previous),
    onSuccess: (state) => queryClient.setQueryData(workspaceKey, state),
    onSettled: () => queryClient.invalidateQueries({ queryKey: workspaceKey })
  });

  const removeWatchlistMutation = useMutation({
    mutationFn: (ticker: string) => api.removeWorkspaceTicker(ticker),
    onMutate: async (ticker) => {
      const clean = normalizeTicker(ticker);
      await queryClient.cancelQueries({ queryKey: workspaceKey });
      const previous = queryClient.getQueryData<WorkspaceState>(workspaceKey);
      queryClient.setQueryData<WorkspaceState>(
        workspaceKey,
        optimisticWorkspace(previous, { watchlist: (previous?.watchlist ?? []).filter((item) => item !== clean) })
      );
      return { previous };
    },
    onError: (_error, _ticker, context) => rollbackWorkspace(queryClient, context?.previous),
    onSuccess: (state) => queryClient.setQueryData(workspaceKey, state),
    onSettled: () => queryClient.invalidateQueries({ queryKey: workspaceKey })
  });

  const recentTickerMutation = useMutation({
    mutationFn: (ticker: string) => api.addRecentTicker(ticker),
    onMutate: async (ticker) => {
      const clean = normalizeTicker(ticker);
      if (!clean) return {};
      await queryClient.cancelQueries({ queryKey: workspaceKey });
      const previous = queryClient.getQueryData<WorkspaceState>(workspaceKey);
      queryClient.setQueryData<WorkspaceState>(
        workspaceKey,
        optimisticWorkspace(previous, { recent_tickers: prependTicker(previous?.recent_tickers, clean, 24) })
      );
      return { previous };
    },
    onError: (_error, _ticker, context) => rollbackWorkspace(queryClient, context?.previous),
    onSuccess: (state) => queryClient.setQueryData(workspaceKey, state),
    onSettled: () => queryClient.invalidateQueries({ queryKey: workspaceKey })
  });

  const saveTodosMutation = useMutation({
    mutationFn: () => api.patchWorkspace({ todos }),
    onSuccess: (state) => {
      queryClient.setQueryData(workspaceKey, state);
      setTodoDraft({ dirty: false, value: "" });
    }
  });

  function submitTicker() {
    const clean = normalizeTicker(tickerInput);
    if (!clean) return;
    addWatchlistMutation.mutate(clean);
    setTickerInput("");
  }

  const topPositions = useMemo(
    () => [...(portfolioQuery.data?.positions ?? [])].sort((a, b) => Math.abs(b.pnl_pct) - Math.abs(a.pnl_pct)).slice(0, 12),
    [portfolioQuery.data?.positions]
  );

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Workspace</h1>
          <p className="mt-1 text-sm text-[#a0a7b4]">Persönliche Watchlist, Tagesplan und schneller Zugriff auf relevante Ticker.</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <StatusChip tone={workspace.source === "database" ? "good" : "warning"}>
            {workspace.source === "database" ? "Persistiert" : "DB-Fallback"}
          </StatusChip>
          {workspace.updated_at ? <StatusChip tone="neutral">Gespeichert {formatDateTime(workspace.updated_at)}</StatusChip> : null}
        </div>
      </div>

      <div className="grid gap-4 xl:grid-cols-[1fr_0.9fr]">
        <section className="rounded border border-[#2d333d] bg-[#171a20] p-5">
          <div className="mb-4 flex items-start justify-between gap-3">
            <div>
              <h2 className="text-base font-semibold">Watchlist</h2>
              <p className="mt-1 text-sm text-[#a0a7b4]">Ticker direkt im Workspace pflegen, ohne Dateiablage.</p>
            </div>
            <BookmarkPlus className="text-emerald-300" size={20} />
          </div>

          <div className="flex flex-col gap-3 sm:flex-row">
            <input
              className="input-dark"
              placeholder="NVDA"
              value={tickerInput}
              onChange={(event) => setTickerInput(event.target.value.toUpperCase())}
              onKeyDown={(event) => {
                if (event.key === "Enter") submitTicker();
              }}
            />
            <button
              className="inline-flex items-center justify-center gap-2 rounded border border-emerald-300/40 bg-emerald-300/10 px-4 py-2 text-sm text-emerald-100 disabled:cursor-not-allowed disabled:opacity-50"
              disabled={!normalizeTicker(tickerInput) || addWatchlistMutation.isPending}
              type="button"
              onClick={submitTicker}
            >
              <BookmarkPlus size={16} />
              Hinzufügen
            </button>
          </div>

          <TickerChipList
            emptyText="Noch keine Ticker in der Watchlist."
            tickers={workspace.watchlist}
            onOpen={(ticker) => recentTickerMutation.mutate(ticker)}
            onRemove={(ticker) => removeWatchlistMutation.mutate(ticker)}
          />
        </section>

        <section className="rounded border border-[#2d333d] bg-[#171a20] p-5">
          <div className="mb-4 flex items-start justify-between gap-3">
            <div>
              <h2 className="text-base font-semibold">Heutige To-dos</h2>
              <p className="mt-1 text-sm text-[#a0a7b4]">Lokales Tippen ist sofort flüssig; gespeichert wird erst per Button.</p>
            </div>
            <StatusChip tone={todoDraft.dirty ? "warning" : "neutral"}>{todoDraft.dirty ? "Ungespeichert" : "Aktuell"}</StatusChip>
          </div>
          <textarea
            className="input-dark min-h-56 resize-y"
            placeholder={"Zum Beispiel\nNVDA nach Earnings prüfen\nWatchlist nach Breakouts filtern"}
            value={todos}
            onChange={(event) => {
              setTodoDraft({ dirty: true, value: event.target.value });
            }}
          />
          <button
            className="mt-4 inline-flex w-full items-center justify-center gap-2 rounded border border-[#2d333d] bg-[#111419] px-4 py-2 text-sm hover:border-emerald-300/60 disabled:cursor-not-allowed disabled:opacity-50"
            disabled={!todoDraft.dirty || saveTodosMutation.isPending}
            type="button"
            onClick={() => saveTodosMutation.mutate()}
          >
            <Save size={16} />
            {saveTodosMutation.isPending ? "Speichert" : "To-dos speichern"}
          </button>
        </section>
      </div>

      <div className="grid gap-4 xl:grid-cols-[0.8fr_1.2fr]">
        <section className="rounded border border-[#2d333d] bg-[#171a20] p-5">
          <div className="mb-4 flex items-start justify-between gap-3">
            <div>
              <h2 className="text-base font-semibold">Schnellzugriff</h2>
              <p className="mt-1 text-sm text-[#a0a7b4]">Zuletzt geöffnete Ticker aus deinem Workspace.</p>
            </div>
            <Clock3 className="text-sky-200" size={20} />
          </div>
          <TickerChipList
            emptyText="Noch keine zuletzt genutzten Ticker."
            tickers={workspace.recent_tickers}
            onOpen={(ticker) => recentTickerMutation.mutate(ticker)}
          />
        </section>

        <section className="rounded border border-[#2d333d] bg-[#171a20] p-5">
          <div className="mb-4 flex items-start justify-between gap-3">
            <div>
              <h2 className="text-base font-semibold">Gespeicherte Positionen</h2>
              <p className="mt-1 text-sm text-[#a0a7b4]">Direkter Wechsel in Sell-Monitor oder Aktienanalyse.</p>
            </div>
            <BriefcaseBusiness className="text-emerald-300" size={20} />
          </div>
          {topPositions.length ? (
            <div className="overflow-hidden rounded border border-[#2d333d]">
              <table className="w-full text-left text-sm">
                <thead className="bg-[#111419] text-xs uppercase text-[#a0a7b4]">
                  <tr>
                    <th className="px-3 py-2">Ticker</th>
                    <th className="px-3 py-2">Stück</th>
                    <th className="px-3 py-2">P&L</th>
                    <th className="px-3 py-2">Status</th>
                    <th className="px-3 py-2 text-right">Aktion</th>
                  </tr>
                </thead>
                <tbody>
                  {topPositions.map((position) => (
                    <PositionRow key={position.ticker} position={position} onOpen={(ticker) => recentTickerMutation.mutate(ticker)} />
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="rounded border border-dashed border-[#2d333d] bg-[#111419] p-4 text-sm text-[#a0a7b4]">
              Noch keine Positionen gespeichert. Importiere dein Depot oder erfasse Positionen manuell im Portfolio.
            </div>
          )}
        </section>
      </div>

      {(workspaceQuery.error || addWatchlistMutation.error || removeWatchlistMutation.error || saveTodosMutation.error) && (
        <div className="rounded border border-rose-300/30 bg-rose-300/10 p-3 text-sm text-rose-100">
          Workspace-Aktion fehlgeschlagen. Die Oberfläche bleibt bedienbar; bitte Backend-Logs prüfen, falls das wiederholt passiert.
        </div>
      )}
    </div>
  );
}

function TickerChipList({
  tickers,
  emptyText,
  onOpen,
  onRemove
}: {
  tickers: string[];
  emptyText: string;
  onOpen: (ticker: string) => void;
  onRemove?: (ticker: string) => void;
}) {
  if (!tickers.length) {
    return <div className="mt-4 rounded border border-dashed border-[#2d333d] bg-[#111419] p-4 text-sm text-[#a0a7b4]">{emptyText}</div>;
  }
  return (
    <div className="mt-4 flex flex-wrap gap-2">
      {tickers.map((ticker) => (
        <span key={ticker} className="inline-flex items-center overflow-hidden rounded border border-[#2d333d] bg-[#111419] text-sm">
          <Link
            className="inline-flex items-center gap-2 px-3 py-2 text-emerald-100 hover:bg-[#1f242c]"
            href={`/stocks/${encodeURIComponent(ticker)}`}
            onClick={() => onOpen(ticker)}
          >
            {ticker}
            <ExternalLink size={14} />
          </Link>
          {onRemove ? (
            <button
              aria-label={`${ticker} entfernen`}
              className="border-l border-[#2d333d] px-2 py-2 text-[#a0a7b4] hover:bg-rose-300/10 hover:text-rose-100"
              type="button"
              onClick={() => onRemove(ticker)}
            >
              <Trash2 size={14} />
            </button>
          ) : null}
        </span>
      ))}
    </div>
  );
}

function PositionRow({ position, onOpen }: { position: PortfolioPosition; onOpen: (ticker: string) => void }) {
  const pnlTone = position.pnl_pct >= 8 ? "good" : position.pnl_pct < 0 ? "bad" : "neutral";
  return (
    <tr className="border-t border-[#2d333d] hover:bg-[#1b2027]">
      <td className="px-3 py-2 font-medium text-emerald-100">{position.ticker}</td>
      <td className="px-3 py-2 text-[#d7dde6]">{formatNumber(position.shares)}</td>
      <td className="px-3 py-2">
        <StatusChip tone={pnlTone}>{formatPercent(position.pnl_pct)}</StatusChip>
      </td>
      <td className="px-3 py-2 capitalize text-[#d7dde6]">{position.status}</td>
      <td className="px-3 py-2 text-right">
        <Link
          className="inline-flex items-center justify-end gap-2 rounded border border-[#2d333d] px-3 py-1.5 text-xs hover:border-emerald-300/60"
          href={`/sell-monitor/${encodeURIComponent(position.ticker)}`}
          onClick={() => onOpen(position.ticker)}
        >
          Sell-Monitor
          <ExternalLink size={13} />
        </Link>
      </td>
    </tr>
  );
}

function optimisticWorkspace(previous: WorkspaceState | undefined, patch: Partial<WorkspaceState>): WorkspaceState {
  return {
    ...(previous ?? emptyWorkspace),
    ...patch
  };
}

function rollbackWorkspace(queryClient: ReturnType<typeof useQueryClient>, previous: WorkspaceState | undefined) {
  if (previous) {
    queryClient.setQueryData(workspaceKey, previous);
  }
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

function formatDateTime(value: string) {
  return new Intl.DateTimeFormat("de-DE", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit"
  }).format(new Date(value));
}

function formatNumber(value: number) {
  return new Intl.NumberFormat("de-DE", { maximumFractionDigits: 2 }).format(value);
}

function formatPercent(value: number) {
  return `${value >= 0 ? "+" : ""}${value.toFixed(1)}%`;
}
