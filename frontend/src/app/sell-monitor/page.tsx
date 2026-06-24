"use client";

import {
  ColumnDef,
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  SortingState,
  useReactTable
} from "@tanstack/react-table";
import { useVirtualizer } from "@tanstack/react-virtual";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowUpDown, RefreshCw } from "lucide-react";
import { useRouter } from "next/navigation";
import { useMemo, useRef, useState } from "react";
import { KpiCard } from "@/components/ui/kpi-card";
import { StatusChip } from "@/components/ui/status-chip";
import { api } from "@/lib/api/client";
import type { PendingStatus, SellRankingRow } from "@/lib/types/api";

const toneByStatus: Record<SellRankingRow["status"], "good" | "neutral" | "warning" | "bad"> = {
  Halten: "good",
  Beobachten: "warning",
  Verkaufen: "bad"
};

const toneByPending: Record<PendingStatus, "good" | "neutral" | "warning" | "bad"> = {
  halten: "good",
  in_bestaetigung: "warning",
  snoozed: "neutral",
  scharf: "bad"
};

export default function SellMonitorPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { data, isLoading } = useQuery({ queryKey: ["sell-ranking"], queryFn: api.sellRanking });
  const monitorMutation = useMutation({
    mutationFn: () =>
      api.startJob({
        type: "position_atr_monitor",
        payload: { mode: "manual", source: "sell_monitor", force: true }
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["jobs"] });
      queryClient.invalidateQueries({ queryKey: ["sell-ranking"] });
      window.setTimeout(() => queryClient.invalidateQueries({ queryKey: ["sell-ranking"] }), 2500);
    }
  });
  const rows = data?.rows ?? [];
  const [sorting, setSorting] = useState<SortingState>([
    { id: "recommendation_pct", desc: true }
  ]);

  const columns = useMemo<ColumnDef<SellRankingRow>[]>(
    () => [
      {
        accessorKey: "ticker",
        header: "Position",
        cell: ({ row }) => (
          <div>
            <div className="font-semibold">{row.original.ticker}</div>
            <div className="text-xs text-[#a0a7b4]">{row.original.name}</div>
          </div>
        )
      },
      {
        accessorKey: "pnl_pct",
        header: "P&L",
        cell: ({ getValue }) => {
          const value = Number(getValue());
          return (
            <span className={value >= 0 ? "text-emerald-300" : "text-rose-300"}>
              {value.toFixed(1)}%
            </span>
          );
        }
      },
      {
        accessorKey: "health_score",
        header: "Health",
        cell: ({ getValue }) => `${Number(getValue()).toFixed(1)}`
      },
      {
        accessorKey: "recommendation_pct",
        header: "Empfehlung",
        cell: ({ getValue }) => `${Number(getValue())}%`
      },
      {
        accessorKey: "status",
        header: "Status",
        cell: ({ row }) => (
          <StatusChip tone={toneByStatus[row.original.status]}>{row.original.status}</StatusChip>
        )
      },
      {
        accessorKey: "pending_status",
        header: "State",
        cell: ({ row }) => (
          <div className="space-y-1">
            <StatusChip tone={toneByPending[row.original.pending_status]}>
              {row.original.pending_status}
            </StatusChip>
            <div className="text-xs text-[#77808f]">
              {row.original.pending_status === "snoozed" && row.original.snoozed_until
                ? `bis ${row.original.snoozed_until}`
                : `${row.original.consecutive_days} Tage`}
            </div>
          </div>
        )
      },
      {
        accessorKey: "primary_signal",
        header: "Signal",
        cell: ({ row }) => (
          <div className="max-w-[360px] truncate text-[#d8dde6]" title={row.original.primary_signal}>
            {row.original.primary_signal}
          </div>
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
  const tableRows = table.getRowModel().rows;
  const scrollParentRef = useRef<HTMLDivElement>(null);
  const rowVirtualizer = useVirtualizer({
    count: tableRows.length,
    getScrollElement: () => scrollParentRef.current,
    estimateSize: () => 60,
    overscan: 10
  });
  const virtualRows = rowVirtualizer.getVirtualItems();
  const totalSize = rowVirtualizer.getTotalSize();
  const paddingTop = virtualRows.length > 0 ? virtualRows[0].start : 0;
  const paddingBottom =
    virtualRows.length > 0 ? totalSize - virtualRows[virtualRows.length - 1].end : 0;
  const visibleColumnCount = table.getVisibleLeafColumns().length;

  const sellCount = rows.filter((row) => row.status === "Verkaufen").length;
  const watchCount = rows.filter((row) => row.status === "Beobachten").length;
  const maxRecommendation = rows.reduce((max, row) => Math.max(max, row.recommendation_pct), 0);
  const averageHealth =
    rows.length > 0 ? rows.reduce((sum, row) => sum + row.health_score, 0) / rows.length : 0;

  return (
    <div className="space-y-5">
      <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-[#172033]">Sell Monitor</h1>
          <p className="mt-1 text-sm leading-6 text-[#687386]">
            Ranking aus der extrahierten Sell-Engine, ohne Jobs im Click-Pfad.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button
            className="inline-flex min-h-11 items-center gap-2 rounded-full border border-[#d8e1ea] bg-white px-4 text-sm font-medium text-[#172033] shadow-sm transition hover:border-[#0f766e] disabled:cursor-not-allowed disabled:opacity-55"
            type="button"
            disabled={monitorMutation.isPending}
            onClick={() => monitorMutation.mutate()}
          >
            <RefreshCw size={15} className={monitorMutation.isPending ? "animate-spin" : ""} />
            {monitorMutation.isPending ? "Monitor startet" : "Positionsmonitor starten"}
          </button>
          <StatusChip tone={isLoading ? "warning" : "good"}>
            {isLoading ? "lädt" : `${rows.length} Positionen`}
          </StatusChip>
        </div>
      </div>

      <div className="grid gap-3 md:grid-cols-[1.2fr_2fr]">
        <div className="rounded-[24px] border border-[#e3e8ef] bg-white p-5 shadow-[0_10px_28px_rgba(15,23,42,0.06)]">
          <div className="text-xs font-semibold uppercase tracking-[0.12em] text-[#687386]">Ranking-Quelle</div>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <StatusChip tone={data?.source === "snapshot" ? "good" : "warning"}>
              {data?.source === "snapshot" ? "Worker Snapshot" : "Live Fallback"}
            </StatusChip>
            <span className="text-sm text-[#172033]">
              {data?.generated_at ? new Date(data.generated_at).toLocaleString("de-DE") : "noch nicht vorcomputet"}
            </span>
          </div>
        </div>
        <div className="rounded-[24px] border border-[#e3e8ef] bg-white p-5 text-sm leading-6 text-[#687386] shadow-[0_10px_28px_rgba(15,23,42,0.06)]">
          {monitorMutation.data
            ? `Positionsmonitor gestartet: ${monitorMutation.data.job_id}`
            : data?.message || "Nach dem ersten Positionsmonitor-Lauf liest diese Seite den vorcomputeten Snapshot."}
          {data?.source_job_id ? <span className="ml-2 text-[#687386]">Job: {data.source_job_id}</span> : null}
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <KpiCard item={{ label: "Verkaufen", value: String(sellCount), detail: "aktive Exit-Fälle", tone: sellCount > 0 ? "bad" : "good" }} />
        <KpiCard item={{ label: "Beobachten", value: String(watchCount), detail: "Review nötig", tone: watchCount > 0 ? "warning" : "neutral" }} />
        <KpiCard item={{ label: "Max Empfehlung", value: `${maxRecommendation}%`, detail: "höchste aktuelle Tranche", tone: maxRecommendation >= 75 ? "bad" : "warning" }} />
        <KpiCard item={{ label: "Ø Health", value: averageHealth.toFixed(1), detail: "Score über Ranking", tone: averageHealth >= 65 ? "good" : averageHealth >= 40 ? "warning" : "bad" }} />
      </div>

      <div className="overflow-hidden rounded-[24px] border border-[#e3e8ef] bg-white shadow-[0_10px_28px_rgba(15,23,42,0.06)]">
        <div ref={scrollParentRef} className="max-h-[560px] overflow-auto">
          <table className="w-full min-w-[980px] border-collapse text-sm">
            <thead className="sticky top-0 bg-[#f6f8fb] text-left text-xs uppercase text-[#687386]">
              {table.getHeaderGroups().map((headerGroup) => (
                <tr key={headerGroup.id}>
                  {headerGroup.headers.map((header) => (
                    <th key={header.id} className="border-b border-[#e3e8ef] px-4 py-3 font-semibold">
                      {header.isPlaceholder ? null : (
                        <button
                          className="inline-flex items-center gap-2 text-left uppercase"
                          type="button"
                          onClick={header.column.getToggleSortingHandler()}
                        >
                          {flexRender(header.column.columnDef.header, header.getContext())}
                          <ArrowUpDown size={13} className="text-[#687386]" />
                        </button>
                      )}
                    </th>
                  ))}
                </tr>
              ))}
            </thead>
            <tbody>
              {paddingTop > 0 && (
                <tr aria-hidden="true">
                  <td colSpan={visibleColumnCount} style={{ height: paddingTop }} />
                </tr>
              )}
              {virtualRows.map((virtualRow) => {
                const row = tableRows[virtualRow.index];
                return (
                  <tr
                    key={row.id}
                    className="cursor-pointer border-b border-[#eef2f6] transition hover:bg-[#f6faf9]"
                    onClick={() => router.push(`/sell-monitor/${row.original.ticker}`)}
                  >
                    {row.getVisibleCells().map((cell) => (
                      <td key={cell.id} className="px-4 py-3">
                        {flexRender(cell.column.columnDef.cell, cell.getContext())}
                      </td>
                    ))}
                  </tr>
                );
              })}
              {paddingBottom > 0 && (
                <tr aria-hidden="true">
                  <td colSpan={visibleColumnCount} style={{ height: paddingBottom }} />
                </tr>
              )}
            </tbody>
          </table>
        </div>
        <div className="border-t border-[#e3e8ef] bg-[#f9fbfd] px-4 py-3 text-xs text-[#687386]">
          Sortierbare, klickbare TanStack Table mit Virtualisierung. State zeigt Streak oder Snooze-Fenster aus Postgres.
        </div>
      </div>
    </div>
  );
}
