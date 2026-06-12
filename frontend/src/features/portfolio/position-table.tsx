"use client";

import {
  ColumnDef,
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  SortingState,
  useReactTable
} from "@tanstack/react-table";
import { ArrowUpDown, Upload } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { StatusChip } from "@/components/ui/status-chip";
import type { PortfolioPosition } from "@/lib/types/api";

const statusTone: Record<PortfolioPosition["status"], "good" | "neutral" | "warning" | "bad"> = {
  ok: "good",
  watch: "warning",
  risk: "warning",
  sell: "bad"
};

export function PositionTable({ positions }: { positions: PortfolioPosition[] }) {
  const router = useRouter();
  const [sorting, setSorting] = useState<SortingState>([{ id: "market_value", desc: true }]);
  const columns = useMemo<ColumnDef<PortfolioPosition>[]>(
    () => [
      {
        accessorKey: "ticker",
        header: "Ticker",
        cell: ({ row }) => (
          <div>
            <div className="font-semibold">{row.original.ticker}</div>
            <div className="text-xs text-[#a0a7b4]">{row.original.name}</div>
          </div>
        )
      },
      {
        accessorKey: "market_value",
        header: "Wert",
        cell: ({ getValue }) => `${Number(getValue()).toLocaleString("de-DE")} EUR`
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
        accessorKey: "pnl_abs",
        header: "P&L EUR",
        cell: ({ getValue }) => {
          const value = Number(getValue());
          return (
            <span className={value >= 0 ? "text-emerald-300" : "text-rose-300"}>
              {value.toLocaleString("de-DE", { maximumFractionDigits: 0 })} EUR
            </span>
          );
        }
      },
      {
        accessorKey: "weight_pct",
        header: "Gewicht",
        cell: ({ getValue }) => `${Number(getValue()).toFixed(1)}%`
      },
      {
        accessorKey: "atr_pct",
        header: "ATR",
        cell: ({ getValue }) => `${Number(getValue()).toFixed(1)}%`
      },
      {
        accessorKey: "stop_pct",
        header: "Stopp",
        cell: ({ getValue }) => {
          const value = getValue();
          return typeof value === "number" ? `${value.toFixed(1)}%` : "-";
        }
      },
      {
        accessorKey: "status",
        header: "Status",
        cell: ({ row }) => (
          <StatusChip tone={statusTone[row.original.status]}>{row.original.status}</StatusChip>
        )
      }
    ],
    []
  );

  // TanStack Table intentionally returns function-heavy table instances.
  // eslint-disable-next-line react-hooks/incompatible-library
  const table = useReactTable({
    data: positions,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getSortedRowModel: getSortedRowModel(),
    getCoreRowModel: getCoreRowModel()
  });

  if (positions.length === 0) {
    return (
      <div className="rounded border border-[#2d333d] bg-[#171a20] p-5">
        <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div>
            <h2 className="text-base font-semibold">Keine offenen Positionen</h2>
            <p className="mt-1 text-sm text-[#a0a7b4]">
              Importiere dein Depot direkt über die Weboberfläche, damit Portfolio, Sell-Monitor und Charts echte Daten nutzen.
            </p>
          </div>
          <Link
            className="inline-flex items-center justify-center gap-2 rounded border border-emerald-300/40 bg-emerald-300/10 px-4 py-2 text-sm text-emerald-100 transition hover:border-emerald-200"
            href="/portfolio/imports"
          >
            <Upload size={16} />
            Import öffnen
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded border border-[#2d333d] bg-[#171a20]">
      <div className="max-h-[460px] overflow-auto">
        <table className="w-full min-w-[760px] border-collapse text-sm">
          <thead className="sticky top-0 bg-[#1f242c] text-left text-xs uppercase text-[#a0a7b4]">
            {table.getHeaderGroups().map((headerGroup) => (
              <tr key={headerGroup.id}>
                {headerGroup.headers.map((header) => (
                  <th key={header.id} className="border-b border-[#2d333d] px-4 py-3 font-medium">
                    {header.column.getCanSort() ? (
                      <button
                        className="inline-flex items-center gap-1 text-left hover:text-white"
                        type="button"
                        onClick={header.column.getToggleSortingHandler()}
                      >
                        {flexRender(header.column.columnDef.header, header.getContext())}
                        <ArrowUpDown size={13} />
                      </button>
                    ) : (
                      flexRender(header.column.columnDef.header, header.getContext())
                    )}
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
                onClick={() => router.push(`/sell-monitor/${row.original.ticker}`)}
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
      <div className="border-t border-[#2d333d] px-4 py-2 text-xs text-[#a0a7b4]">
        Sortierbare TanStack Table; Virtualisierung wird bei sehr großen Depots ergänzt.
      </div>
    </div>
  );
}
