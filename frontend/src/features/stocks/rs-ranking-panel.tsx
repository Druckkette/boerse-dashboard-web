"use client";

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
import { CollapsiblePanel } from "@/components/ui/collapsible-panel";
import { StatusChip } from "@/components/ui/status-chip";
import { api } from "@/lib/api/client";
import type { RsRatingItem, RsRatingRanking } from "@/lib/types/api";

export function RsRankingPanel() {
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
      api.startJob({
        type: "refresh_relative_strength",
        payload: { mode: "manual", lookback_days: 430 }
      }),
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
            <div className="max-w-48 truncate text-xs text-[#a0a7b4]">{row.original.name}</div>
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
        header: "Percentile",
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
        header: "RS High",
        cell: ({ row }) => (
          <StatusChip tone={row.original.new_high_52w ? "good" : row.original.near_high_52w ? "neutral" : "warning"}>
            {row.original.new_high_52w ? "New" : row.original.near_high_52w ? "Near" : "Off"}
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
      title="Relative Stärke Ranking"
      subtitle="Vorberechnete RS-Ratings aus dem Worker. Die Tabelle zeigt nur die obersten Werte bis zum Limit."
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
      <div className="flex flex-col gap-3 border-b border-[#2d333d] p-5 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <div className="mt-1 text-sm text-[#a0a7b4]">
            {hasRanking
              ? `${rows.length} angezeigt von ${totalCount || rows.length} aktuellen RS-Ratings · Stand ${ranking?.as_of ?? "-"}`
              : "Noch keine gespeicherten RS-Ratings. Erst Prices aktualisieren, dann RS Ratings starten."}
            <div className="mt-1 text-xs text-[#77808f]">
              Das Limit ist {limit}; die Datenbank kann mehr Ratings enthalten.
            </div>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            className="inline-flex items-center gap-2 rounded border border-[#2d333d] bg-[#111419] px-3 py-2 text-sm transition hover:border-emerald-300/60"
            type="button"
            onClick={() => query.refetch()}
          >
            <RefreshCw size={15} className={query.isFetching ? "animate-spin text-emerald-300" : "text-[#a0a7b4]"} />
            Aktualisieren
          </button>
          <button
            className="inline-flex items-center gap-2 rounded border border-emerald-300/40 bg-emerald-300/10 px-3 py-2 text-sm text-emerald-100 transition hover:border-emerald-200 disabled:cursor-not-allowed disabled:opacity-50"
            disabled={startMutation.isPending}
            type="button"
            onClick={() => startMutation.mutate()}
          >
            <Play size={15} />
            {startMutation.isPending ? "Startet" : "RS Job"}
          </button>
        </div>
      </div>

      {query.isError && (
        <div className="border-b border-[#2d333d] px-5 py-3 text-sm text-rose-200">
          {query.error instanceof Error ? query.error.message : "RS-Ranking konnte nicht geladen werden."}
        </div>
      )}
      {startMutation.isError && (
        <div className="border-b border-[#2d333d] px-5 py-3 text-sm text-amber-100">
          {startMutation.error instanceof Error ? startMutation.error.message : "RS-Job konnte nicht gestartet werden."}
        </div>
      )}

      {query.isLoading ? (
        <div className="p-5 text-sm text-[#a0a7b4]">Relative-Stärke-Ranking lädt...</div>
      ) : query.isError ? null : rows.length === 0 ? (
        <div className="p-5 text-sm text-[#a0a7b4]">
          Die Tabelle wird gefüllt, sobald Prices und danach RS Ratings erfolgreich gelaufen sind.
        </div>
      ) : (
        <div className="max-h-[580px] overflow-auto">
          <table className="w-full min-w-[860px] border-collapse text-sm">
            <thead className="sticky top-0 bg-[#1f242c] text-left text-xs uppercase text-[#a0a7b4]">
              {table.getHeaderGroups().map((headerGroup) => (
                <tr key={headerGroup.id}>
                  {headerGroup.headers.map((header) => (
                    <th key={header.id} className="border-b border-[#2d333d] px-4 py-3 font-medium">
                      <button
                        className="inline-flex items-center gap-1"
                        type="button"
                        onClick={header.column.getToggleSortingHandler()}
                      >
                        {flexRender(header.column.columnDef.header, header.getContext())}
                        <ArrowUpDown size={13} className="text-[#697386]" />
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
                  className="cursor-pointer border-b border-[#242a33] transition hover:bg-[#20262f]"
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
        </div>
      )}
      <div className="border-t border-[#2d333d] px-5 py-2 text-xs text-[#a0a7b4]">
        TanStack Table mit Sortierung; Virtualisierung kann bei großem Universe ergänzt werden.
      </div>
    </CollapsiblePanel>
  );
}

function PctCell({ value }: { value?: number | null }) {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return <span className="text-[#697386]">-</span>;
  }
  return <span className={value >= 0 ? "text-emerald-300" : "text-rose-300"}>{formatPct(value)}</span>;
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
