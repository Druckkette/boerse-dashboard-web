"use client";

import { useBetaMode } from "@/components/beta-mode-provider";

import {
  ColumnDef,
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  SortingState,
  useReactTable
} from "@tanstack/react-table";
import { ArrowUpDown, Play, RefreshCw } from "lucide-react";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ResearchTableTools } from "@/components/ui/research-table-tools";
import { CollapsiblePanel } from "@/components/ui/collapsible-panel";
import { StatusChip } from "@/components/ui/status-chip";
import { api } from "@/lib/api/client";
import type { RsRatingItem, RsRatingRanking } from "@/lib/types/api";

export function RsRankingPanel() {
  const beta = useBetaMode();
  const router = useRouter();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [sorting, setSorting] = useState<SortingState>([{ id: "rating", desc: true }]);
  const limit = 120;
  const query = useQuery({
    queryKey: ["stocks-rs-ranking", limit],
    queryFn: () => api.rsRanking(limit),
    enabled: open,
    staleTime: 60_000
  });
  const ranking = query.data;
  const rows = ranking?.rows ?? [];
  const totalCount = ranking?.total_count ?? 0;
  const hasRanking = Boolean(ranking && ranking.source !== "missing");
  const startMutation = useMutation({
    mutationFn: () =>
      (beta ? Promise.reject(new Error("In der Beta nicht verfügbar")) : api.startJob({
        type: "refresh_relative_strength",
        payload: { mode: "manual", lookback_days: 430 }
      })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["jobs"] })
  });

  const columns = useMemo<ColumnDef<RsRatingItem>[]>(
    () => [
      {
        accessorKey: "ticker",
        header: "Ticker",
        cell: ({ row }) => (
          <div>
            <div className="font-semibold">{row.original.ticker}</div>
            <div className="max-w-48 truncate text-xs text-[var(--muted)]">{row.original.name}</div>
          </div>
        )
      },
      {
        accessorKey: "rating",
        header: "RS",
        cell: ({ row }) => (
          <StatusChip tone={toneForRating(row.original.rating)}>{row.original.rating ?? "-"}</StatusChip>
        )
      },
      {
        accessorKey: "percentile",
        header: "Perzentil",
        cell: ({ getValue }) => formatPct(getValue<number | null>())
      },
      {
        accessorKey: "ret_3m",
        header: "3M",
        cell: ({ getValue }) => <PctCell value={getValue<number | null>()} />
      },
      {
        accessorKey: "ret_6m",
        header: "6M",
        cell: ({ getValue }) => <PctCell value={getValue<number | null>()} />
      },
      {
        accessorKey: "excess_return_6m",
        header: "vs SPY 6M",
        cell: ({ getValue }) => <PctCell value={getValue<number | null>()} />
      },
      {
        accessorKey: "new_high_52w",
        header: "RS-Hoch",
        cell: ({ row }) => (
          <StatusChip tone={row.original.new_high_52w ? "good" : row.original.near_high_52w ? "neutral" : "warning"}>
            {row.original.new_high_52w ? "Neu" : row.original.near_high_52w ? "Nahe" : "Entfernt"}
          </StatusChip>
        )
      }
    ],
    []
  );

  // TanStack Table intentionally returns function-heavy table instances.
  // eslint-disable-next-line react-hooks/incompatible-library
  const table = useReactTable({
    data: rows,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel()
  });

  return (
    <CollapsiblePanel
      title="Relative Stärke · Top 120 nach RS"
      subtitle="Die 120 Aktien mit dem höchsten gespeicherten RS-Rating. Sortierung gilt für diese Auswahl."
      open={open}
      onOpenChange={setOpen}
      summary={
        <>
          <StatusChip tone={!query.isFetched ? "neutral" : hasRanking ? "good" : "warning"}>
            {!query.isFetched ? "nicht geladen" : hasRanking ? sourceLabel(ranking?.source) : "Cache fehlt"}
          </StatusChip>
          <StatusChip tone="neutral">
            {hasRanking ? `${rows.length}/${totalCount || rows.length}` : `${limit} Limit`}
          </StatusChip>
        </>
      }
    >
      <div className="flex flex-col gap-3 border-b border-[var(--border)] p-5 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <div className="mt-1 text-sm text-[var(--muted)]">
            {hasRanking
              ? `${rows.length} angezeigt von ${totalCount || rows.length} aktuellen RS-Ratings · Stand ${ranking?.as_of ?? "-"}`
              : "Noch keine gespeicherten RS-Ratings. Erst Prices aktualisieren, dann RS Ratings starten."}
            <div className="mt-1 text-xs text-[var(--muted)]">
              Das Limit ist {limit}; die Datenbank kann mehr Ratings enthalten.
            </div>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            className="inline-flex items-center gap-2 rounded border border-[var(--border)] bg-[var(--panel)] px-3 py-2 text-sm transition hover:border-emerald-300/60"
            type="button"
            onClick={() => query.refetch()}
          >
            <RefreshCw size={15} className={query.isFetching ? "animate-spin text-[var(--green)]" : "text-[var(--muted)]"} />
            Aktualisieren
          </button>
          {!beta && (<button
            className="inline-flex items-center gap-2 rounded border border-emerald-300/40 bg-[var(--green-soft)] px-3 py-2 text-sm text-[var(--green)] transition hover:border-emerald-200 disabled:cursor-not-allowed disabled:opacity-50"
            disabled={startMutation.isPending}
            type="button"
            onClick={() => startMutation.mutate()}
          >
            <Play size={15} />
            {startMutation.isPending ? "Startet" : "RS Job"}
          </button>)}
        </div>
      </div>

      {query.isError && (
        <div className="border-b border-[var(--border)] px-5 py-3 text-sm text-[var(--red)]">
          {query.error instanceof Error ? query.error.message : "RS-Ranking konnte nicht geladen werden."}
        </div>
      )}
      {startMutation.isError && (
        <div className="border-b border-[var(--border)] px-5 py-3 text-sm text-[var(--yellow)]">
          {startMutation.error instanceof Error ? startMutation.error.message : "RS-Job konnte nicht gestartet werden."}
        </div>
      )}

      {query.isLoading ? (
        <div className="p-5 text-sm text-[var(--muted)]">Relative-Stärke-Ranking lädt...</div>
      ) : query.isError ? null : rows.length === 0 ? (
        <div className="p-5 text-sm text-[var(--muted)]">
          Die Tabelle wird gefüllt, sobald Prices und danach RS Ratings erfolgreich gelaufen sind.
        </div>
      ) : (
        <><ResearchTableTools id="rs" columns={["Aktie","RS","Perzentil","3 Monate","6 Monate","vs. SPY 6 Monate","RS-Hoch"]}/>
      <div className="max-h-[580px] overflow-auto">
          <table data-research="rs" className="research-table w-full min-w-[860px] border-collapse text-sm">
            <thead className="sticky top-0 bg-[var(--panel)] text-left text-xs uppercase text-[var(--muted)]">
              {table.getHeaderGroups().map((headerGroup) => (
                <tr key={headerGroup.id}>
                  {headerGroup.headers.map((header) => (
                    <th key={header.id} className="border-b border-[var(--border)] px-4 py-3 font-medium">
                      <button
                        className="inline-flex items-center gap-1"
                        type="button"
                        onClick={header.column.getToggleSortingHandler()}
                      >
                        {flexRender(header.column.columnDef.header, header.getContext())}
                        <ArrowUpDown size={13} className="text-[var(--muted)]" />
                      </button>
                    </th>
                  ))}
                </tr>
              ))}
            </thead>
            <tbody>
              {table.getRowModel().rows.map((row) => (
                <tr
                  key={row.id}
                  className="cursor-pointer border-b border-[var(--border)] transition hover:bg-[var(--panel)]"
                  onClick={() => router.push(`/stocks/${row.original.ticker}`)}
                >
                  {row.getVisibleCells().map((cell) => (
                    <td key={cell.id} className="px-4 py-3">
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div></>
      )}
      <div className="border-t border-[var(--border)] px-5 py-2 text-xs text-[var(--muted)]">
        Sortierung gilt für die angezeigten Top 120. Weitere Aktien findest du über die Suche und das Bewertungsranking.
      </div>
    </CollapsiblePanel>
  );
}

function PctCell({ value }: { value?: number | null }) {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return <span className="text-[var(--muted)]">-</span>;
  }
  return <span className={value >= 0 ? "text-[var(--green)]" : "text-[var(--red)]"}>{formatPct(value)}</span>;
}

function formatPct(value?: number | null) {
  if (typeof value !== "number" || Number.isNaN(value)) return "-";
  return `${value >= 0 ? "+" : ""}${value.toFixed(1)}%`;
}

function toneForRating(value?: number | null): "good" | "neutral" | "warning" | "bad" {
  if (typeof value !== "number") return "neutral";
  if (value >= 80) return "good";
  if (value >= 60) return "neutral";
  if (value >= 40) return "warning";
  return "bad";
}

function sourceLabel(source?: RsRatingRanking["source"]) {
  if (source === "csv_latest") return "RS-Datenquelle CSV";
  if (source === "computed") return "intern berechnet";
  if (source === "database") return "aktuell";
  return "Cache fehlt";
}
