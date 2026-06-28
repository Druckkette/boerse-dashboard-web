"use client";

import {
  ColumnDef,
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  SortingState,
  useReactTable
} from "@tanstack/react-table";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useVirtualizer } from "@tanstack/react-virtual";
import { ArrowUpDown, Upload } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useRef, useState } from "react";
import { StatusChip } from "@/components/ui/status-chip";
import { api } from "@/lib/api/client";
import type { PortfolioAfterHoursPosition, PortfolioPosition } from "@/lib/types/api";

const statusTone: Record<PortfolioPosition["status"], "good" | "neutral" | "warning" | "bad"> = {
  ok: "good",
  watch: "warning",
  risk: "warning",
  sell: "bad"
};

export function PositionTable({
  positions,
  afterHoursByTicker
}: {
  positions: PortfolioPosition[];
  afterHoursByTicker?: Map<string, PortfolioAfterHoursPosition>;
}) {
  const router = useRouter();
  const [sorting, setSorting] = useState<SortingState>([{ id: "market_value", desc: true }]);
  const showAfterHours = Boolean(afterHoursByTicker?.size);
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
        cell: ({ row, getValue }) => `${Number(getValue()).toLocaleString("de-DE")} ${row.original.currency}`
      },
      {
        accessorKey: "current_price",
        header: "Aktueller Preis",
        cell: ({ row, getValue }) =>
          `${Number(getValue()).toLocaleString("de-DE", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${row.original.currency}`
      },
      ...(showAfterHours
        ? [
            {
              id: "after_hours",
              header: "After Hours",
              cell: ({ row }) => {
                const quote = afterHoursByTicker?.get(row.original.ticker);
                if (!quote) return <span className="text-[#a0a7b4]">nicht geladen</span>;
                if (!quote.available || typeof quote.after_hours_price !== "number") {
                  return (
                    <div>
                      <div className="text-[#a0a7b4]">n/a</div>
                      {quote.error_message ? (
                        <div className="max-w-40 truncate text-xs text-[#687386]" title={quote.error_message}>
                          {quote.error_message}
                        </div>
                      ) : null}
                    </div>
                  );
                }
                const pct = quote.after_hours_change_pct ?? 0;
                const change = quote.after_hours_change ?? 0;
                return (
                  <div className={pct >= 0 ? "text-emerald-300" : "text-rose-300"}>
                    <div className="font-medium tabular-nums">
                      {quote.after_hours_price.toLocaleString("de-DE", {
                        minimumFractionDigits: 2,
                        maximumFractionDigits: 2
                      })}{" "}
                      {quote.currency}
                    </div>
                    <div className="text-xs tabular-nums">
                      {pct >= 0 ? "+" : ""}
                      {pct.toFixed(2)}% · {change >= 0 ? "+" : ""}
                      {change.toFixed(2)}
                    </div>
                  </div>
                );
              }
            } satisfies ColumnDef<PortfolioPosition>
          ]
        : []),
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
        header: "P&L",
        cell: ({ row, getValue }) => {
          const value = Number(getValue());
          return (
            <span className={value >= 0 ? "text-emerald-300" : "text-rose-300"}>
              {value.toLocaleString("de-DE", { maximumFractionDigits: 0 })} {row.original.currency}
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
        accessorKey: "beta_balancer_score",
        header: "Beta-Balancer",
        cell: ({ getValue }) => {
          const value = getValue();
          return typeof value === "number" ? value.toFixed(2) : "-";
        }
      },
      {
        accessorKey: "risk_contribution",
        header: "Risikobeitrag",
        cell: ({ getValue }) => {
          const value = getValue();
          return typeof value === "number" ? value.toFixed(2) : "-";
        }
      },
      {
        accessorKey: "stop_price",
        header: "Stopp USD",
        cell: ({ row }) => (
          <StopPriceCell
            key={`${row.original.ticker}-${row.original.stop_price ?? "none"}`}
            position={row.original}
          />
        )
      },
      {
        accessorKey: "position_loss_risk",
        header: "Positionsverlustrisiko",
        cell: ({ row, getValue }) => {
          const value = getValue();
          return typeof value === "number"
            ? `${value.toLocaleString("de-DE", { maximumFractionDigits: 0 })} ${row.original.currency}`
            : "-";
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
    [afterHoursByTicker, showAfterHours]
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
  const rows = table.getRowModel().rows;
  const scrollParentRef = useRef<HTMLDivElement>(null);
  const rowVirtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => scrollParentRef.current,
    estimateSize: () => 56,
    overscan: 10
  });
  const virtualRows = rowVirtualizer.getVirtualItems();
  const totalSize = rowVirtualizer.getTotalSize();
  const paddingTop = virtualRows.length > 0 ? virtualRows[0].start : 0;
  const paddingBottom =
    virtualRows.length > 0 ? totalSize - virtualRows[virtualRows.length - 1].end : 0;
  const visibleColumnCount = table.getVisibleLeafColumns().length;

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
      <div ref={scrollParentRef} className="max-h-[460px] overflow-auto">
        <table className="w-full min-w-[1360px] border-collapse text-sm">
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
            {paddingTop > 0 && (
              <tr aria-hidden="true">
                <td colSpan={visibleColumnCount} style={{ height: paddingTop }} />
              </tr>
            )}
            {virtualRows.map((virtualRow) => {
              const row = rows[virtualRow.index];
              return (
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
    </div>
  );
}

function StopPriceCell({ position }: { position: PortfolioPosition }) {
  const queryClient = useQueryClient();
  const [value, setValue] = useState(formatEditableNumber(position.stop_price));
  const mutation = useMutation({
    mutationFn: (stopPrice: number | null) => api.updatePortfolioStop(position.ticker, stopPrice),
    onSuccess: () => invalidatePortfolioTable(queryClient)
  });

  function save() {
    const nextStop = parseEditableNumber(value);
    const currentStop = typeof position.stop_price === "number" ? position.stop_price : null;
    if (numbersEqual(nextStop, currentStop) || mutation.isPending) return;
    mutation.mutate(nextStop);
  }

  return (
    <div className="flex items-center gap-2" onClick={(event) => event.stopPropagation()}>
      <input
        aria-label={`${position.ticker} Stopp USD`}
        className="h-8 w-28 rounded border border-[#2d333d] bg-[#111419] px-2 text-right text-sm tabular-nums text-[#d8dde6] outline-none transition focus:border-emerald-300/70 disabled:opacity-60"
        inputMode="decimal"
        placeholder="-"
        value={value}
        disabled={mutation.isPending}
        onBlur={save}
        onChange={(event) => setValue(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter") event.currentTarget.blur();
          if (event.key === "Escape") {
            setValue(formatEditableNumber(position.stop_price));
            event.currentTarget.blur();
          }
        }}
      />
      {mutation.isPending && <span className="text-xs text-[#a0a7b4]">speichert</span>}
      {mutation.isError && <span className="text-xs text-rose-300">Fehler</span>}
    </div>
  );
}

function invalidatePortfolioTable(queryClient: ReturnType<typeof useQueryClient>) {
  queryClient.invalidateQueries({ queryKey: ["portfolio-snapshot"] });
  queryClient.invalidateQueries({ queryKey: ["portfolio-positions"] });
  queryClient.invalidateQueries({ queryKey: ["portfolio-curve"] });
  queryClient.invalidateQueries({ queryKey: ["sell-ranking"] });
}

function formatEditableNumber(value: number | null | undefined) {
  return typeof value === "number" && Number.isFinite(value) ? String(Number(value.toFixed(2))) : "";
}

function parseEditableNumber(value: string) {
  const clean = value.trim().replace(",", ".");
  if (!clean) return null;
  const parsed = Number(clean);
  return Number.isFinite(parsed) && parsed > 0 ? Number(parsed.toFixed(4)) : null;
}

function numbersEqual(left: number | null, right: number | null) {
  if (left === null || right === null) return left === right;
  return Math.abs(left - right) < 0.0001;
}
