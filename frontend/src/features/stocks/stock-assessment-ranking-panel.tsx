"use client";

import {
  ColumnDef,
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  SortingState,
  useReactTable
} from "@tanstack/react-table";
import { ArrowUpDown, RefreshCw } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { CollapsiblePanel } from "@/components/ui/collapsible-panel";
import { StatusChip } from "@/components/ui/status-chip";
import { api } from "@/lib/api/client";
import type { StockAssessmentRankingItem } from "@/lib/types/api";

export function StockAssessmentRankingPanel() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [sorting, setSorting] = useState<SortingState>([{ id: "overall_score", desc: true }]);
  const limit = 60;
  const query = useQuery({
    queryKey: ["stock-assessment-ranking", limit],
    queryFn: () => api.stockAssessmentRanking(limit),
    enabled: open,
    staleTime: 60_000
  });
  const rows = query.data?.rows ?? [];
  const totalCount = query.data?.total_count ?? 0;

  const columns = useMemo<ColumnDef<StockAssessmentRankingItem>[]>(
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
        accessorKey: "overall_score",
        header: "Score",
        cell: ({ row }) => <StatusChip tone={row.original.verdict_tone}>{row.original.overall_score}</StatusChip>
      },
      {
        accessorKey: "last_close",
        header: "Preis",
        cell: ({ getValue }) => money(getValue<number | null>())
      },
      {
        accessorKey: "technical_score",
        header: "Technisch",
        cell: ({ getValue }) => number(getValue<number>())
      },
      {
        accessorKey: "moving_average_score",
        header: "Trend",
        cell: ({ getValue }) => number(getValue<number>())
      },
      {
        accessorKey: "chart_behavior_score",
        header: "Chart",
        cell: ({ getValue }) => number(getValue<number>())
      },
      {
        accessorKey: "rs_rating",
        header: "RS",
        cell: ({ getValue }) => number(getValue<number | null>())
      },
      {
        accessorKey: "dollar_volume_mio",
        header: "$ Vol.",
        cell: ({ getValue }) => mio(getValue<number | null>())
      },
      {
        accessorKey: "top_warning",
        header: "Kontext",
        cell: ({ row }) => (
          <div className="max-w-80 truncate text-xs text-[#a0a7b4]">
            {row.original.top_warning || row.original.top_driver || row.original.verdict_label}
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

  return (
    <CollapsiblePanel
      title="Aktienbewertung Ranking"
      subtitle="Bewertung der stärksten RS-Kandidaten auf Basis Price Cache, RS, Fundamentals und 13F. Lädt erst beim Öffnen."
      open={open}
      onOpenChange={setOpen}
      summary={
        <>
          <StatusChip tone={!query.isFetched ? "neutral" : query.data?.source === "database" ? "good" : "warning"}>
            {!query.isFetched ? "nicht geladen" : query.data?.source === "database" ? "Assessment Cache" : "Cache fehlt"}
          </StatusChip>
          <StatusChip tone="neutral">
            {query.data?.source === "database" ? `${rows.length}/${totalCount || rows.length}` : `${limit} Limit`}
          </StatusChip>
        </>
      }
    >
      <div className="flex flex-col gap-3 border-b border-[#2d333d] p-5 lg:flex-row lg:items-start lg:justify-between">
        <div className="text-sm text-[#a0a7b4]">
          {query.data?.source === "database"
            ? `${rows.length} angezeigt von ${totalCount || rows.length} aktuellen RS-Kandidaten · Stand ${query.data.as_of}`
            : "Noch keine ausreichenden RS- und Price-Cache-Daten für ein Ranking."}
          <div className="mt-1 text-xs text-[#77808f]">
            Das API-Limit ist {limit}; die Bewertung wird hier nicht live für das komplette Universe neu gerechnet.
          </div>
        </div>
        <button
          className="inline-flex items-center gap-2 rounded border border-[#2d333d] bg-[#111419] px-3 py-2 text-sm transition hover:border-emerald-300/60"
          type="button"
          onClick={() => query.refetch()}
        >
          <RefreshCw size={15} className={query.isFetching ? "animate-spin text-emerald-300" : "text-[#a0a7b4]"} />
          Aktualisieren
        </button>
      </div>

      {query.isError && (
        <div className="border-b border-[#2d333d] px-5 py-3 text-sm text-rose-200">
          {query.error instanceof Error ? query.error.message : "Aktienbewertung-Ranking konnte nicht geladen werden."}
        </div>
      )}

      {query.isLoading ? (
        <div className="p-5 text-sm text-[#a0a7b4]">Aktienbewertung-Ranking lädt...</div>
      ) : rows.length === 0 ? (
        <div className="p-5 text-sm text-[#a0a7b4]">
          Die Tabelle wird gefüllt, sobald Price Cache und RS Ratings vorhanden sind.
        </div>
      ) : (
        <div className="max-h-[520px] overflow-auto">
          <table className="w-full min-w-[980px] border-collapse text-sm">
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
    </CollapsiblePanel>
  );
}

function number(value?: number | null) {
  if (typeof value !== "number" || Number.isNaN(value)) return "-";
  return value.toFixed(0);
}

function mio(value?: number | null) {
  if (typeof value !== "number" || Number.isNaN(value)) return "-";
  return `$${value.toFixed(0)} Mio.`;
}

function money(value?: number | null) {
  if (typeof value !== "number" || Number.isNaN(value)) return "-";
  return new Intl.NumberFormat("de-DE", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2
  }).format(value);
}
