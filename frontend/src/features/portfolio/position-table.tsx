"use client";

import {
  ColumnDef,
  VisibilityState,
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  SortingState,
  useReactTable
} from "@tanstack/react-table";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useVirtualizer } from "@tanstack/react-virtual";
import { ArrowUpDown, Columns3, ExternalLink, Upload } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { StatusChip } from "@/components/ui/status-chip";
import { api } from "@/lib/api/client";
import { formatMoney, formatNumber, formatPercent, portfolioStatusLabel } from "@/lib/format";
import type { PortfolioAfterHoursPosition, PortfolioPosition, Tone } from "@/lib/types/api";

const SORT_KEY = "portfolio-position-sorting-v1";
const VISIBILITY_KEY = "portfolio-position-columns-v1";
const statusTone: Record<PortfolioPosition["status"], Tone> = {
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
  const [columnVisibility, setColumnVisibility] = useState<VisibilityState>({});
  const showAfterHours = Boolean(afterHoursByTicker?.size);

  useEffect(() => {
    setSorting(readStoredState<SortingState>(SORT_KEY, [{ id: "market_value", desc: true }]));
    setColumnVisibility(readStoredState<VisibilityState>(VISIBILITY_KEY, {}));
  }, []);
  useEffect(() => { window.localStorage.setItem(SORT_KEY, JSON.stringify(sorting)); }, [sorting]);
  useEffect(() => { window.localStorage.setItem(VISIBILITY_KEY, JSON.stringify(columnVisibility)); }, [columnVisibility]);

  const columns = useMemo<ColumnDef<PortfolioPosition>[]>(() => [
    {
      accessorKey: "ticker",
      header: "Position",
      cell: ({ row }) => <div><div className="font-semibold text-[#172033]">{row.original.ticker}</div><div className="max-w-40 truncate text-xs text-[#687386]">{row.original.name}</div></div>
    },
    { accessorKey: "market_value", header: "Wert", cell: ({ row, getValue }) => formatMoney(Number(getValue()), row.original.currency, 0) },
    { accessorKey: "current_price", header: "Kurs", cell: ({ row, getValue }) => formatMoney(Number(getValue()), row.original.currency) },
    ...(showAfterHours ? [{
      id: "after_hours",
      header: "After Market",
      cell: ({ row }: { row: { original: PortfolioPosition } }) => <AfterHoursCell quote={afterHoursByTicker?.get(row.original.ticker)} />
    } satisfies ColumnDef<PortfolioPosition>] : []),
    { accessorKey: "pnl_pct", header: "P&L %", cell: ({ getValue }) => <SignedValue value={Number(getValue())} suffix="%" /> },
    { accessorKey: "pnl_abs", header: "P&L", cell: ({ row, getValue }) => <SignedValue value={Number(getValue())} suffix={` ${row.original.currency}`} digits={0} /> },
    { accessorKey: "weight_pct", header: "Gewicht", cell: ({ getValue }) => formatPercent(Number(getValue()), 1, false) },
    { accessorKey: "atr_pct", header: "ATR", cell: ({ getValue }) => typeof getValue() === "number" ? formatPercent(Number(getValue()), 1, false) : "–" },
    { accessorKey: "beta_balancer_score", header: "Beta-Balancer", cell: ({ getValue }) => formatNumber(getValue() as number | null) },
    { accessorKey: "risk_contribution", header: "Risikobeitrag", cell: ({ getValue }) => formatNumber(getValue() as number | null) },
    { accessorKey: "stop_price", header: "Stopp USD", cell: ({ row }) => <StopPriceCell key={`${row.original.ticker}-${row.original.stop_price ?? "none"}`} position={row.original} /> },
    { accessorKey: "position_loss_risk", header: "Verlustrisiko", cell: ({ row, getValue }) => typeof getValue() === "number" ? formatMoney(Number(getValue()), row.original.currency, 0) : "–" },
    {
      accessorKey: "status",
      header: "Status",
      cell: ({ row }) => {
        const implausible = row.original.pnl_pct > 400 || row.original.pnl_pct < -75;
        return <StatusChip tone={implausible ? "bad" : statusTone[row.original.status]}>{implausible ? "Daten prüfen" : portfolioStatusLabel(row.original.status)}</StatusChip>;
      }
    }
  ], [afterHoursByTicker, showAfterHours]);

  // eslint-disable-next-line react-hooks/incompatible-library
  const table = useReactTable({
    data: positions,
    columns,
    state: { sorting, columnVisibility },
    onSortingChange: setSorting,
    onColumnVisibilityChange: setColumnVisibility,
    getSortedRowModel: getSortedRowModel(),
    getCoreRowModel: getCoreRowModel()
  });
  const rows = table.getRowModel().rows;
  const scrollParentRef = useRef<HTMLDivElement>(null);
  const rowVirtualizer = useVirtualizer({ count: rows.length, getScrollElement: () => scrollParentRef.current, estimateSize: () => 58, overscan: 10 });
  const virtualRows = rowVirtualizer.getVirtualItems();
  const totalSize = rowVirtualizer.getTotalSize();
  const paddingTop = virtualRows.length ? virtualRows[0].start : 0;
  const paddingBottom = virtualRows.length ? totalSize - virtualRows[virtualRows.length - 1].end : 0;

  if (!positions.length) return <EmptyPortfolio />;

  return (
    <section className="overflow-hidden rounded-[14px] border border-[#e3e8ef] bg-white shadow-[0_5px_18px_rgba(15,23,42,0.05)]">
      <div className="flex items-center justify-between gap-3 border-b border-[#e8edf2] px-4 py-3">
        <div><h2 className="text-sm font-semibold text-[#172033]">Positionen</h2><p className="mt-0.5 text-xs text-[#687386]">Sortierung und sichtbare Spalten werden in diesem Browser gespeichert.</p></div>
        <details className="relative">
          <summary className="inline-flex h-9 cursor-pointer list-none items-center gap-2 rounded-[9px] border border-[#d8e1ea] px-3 text-sm font-medium text-[#172033]"><Columns3 size={15} /> Spalten</summary>
          <div className="absolute right-0 z-20 mt-2 w-56 rounded-[10px] border border-[#d8e1ea] bg-white p-2 shadow-[0_14px_32px_rgba(15,23,42,0.14)]">
            {table.getAllLeafColumns().filter((column) => column.getCanHide()).map((column) => (
              <label key={column.id} className="flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 text-sm hover:bg-[#f5f8fa]">
                <input checked={column.getIsVisible()} type="checkbox" onChange={column.getToggleVisibilityHandler()} />
                {columnLabel(column.id)}
              </label>
            ))}
          </div>
        </details>
      </div>

      <div className="divide-y divide-[#e8edf2] md:hidden">
        {rows.map((row) => <MobilePositionCard key={row.id} position={row.original} quote={afterHoursByTicker?.get(row.original.ticker)} />)}
      </div>

      <div ref={scrollParentRef} className="hidden max-h-[520px] overflow-auto md:block">
        <table className="w-full min-w-[1320px] border-collapse text-sm">
          <thead className="sticky top-0 z-10 bg-[#f6f8fb] text-left text-[10px] uppercase tracking-[0.06em] text-[#687386]">
            {table.getHeaderGroups().map((group) => <tr key={group.id}>{group.headers.map((header) => (
              <th key={header.id} className="border-b border-[#e3e8ef] px-3 py-3 font-semibold">
                {header.isPlaceholder ? null : header.column.getCanSort() ? (
                  <button className="inline-flex items-center gap-1.5" type="button" onClick={header.column.getToggleSortingHandler()}>
                    {flexRender(header.column.columnDef.header, header.getContext())}<ArrowUpDown size={12} />
                  </button>
                ) : flexRender(header.column.columnDef.header, header.getContext())}
              </th>
            ))}</tr>)}
          </thead>
          <tbody>
            {paddingTop > 0 ? <tr aria-hidden="true"><td colSpan={table.getVisibleLeafColumns().length} style={{ height: paddingTop }} /></tr> : null}
            {virtualRows.map((virtualRow) => {
              const row = rows[virtualRow.index];
              return <tr key={row.id} className="cursor-pointer border-b border-[#eef2f6] transition hover:bg-[#f6faf9]" onClick={() => router.push(`/sell-monitor/${row.original.ticker}`)}>
                {row.getVisibleCells().map((cell) => <td key={cell.id} className="px-3 py-3">{flexRender(cell.column.columnDef.cell, cell.getContext())}</td>)}
              </tr>;
            })}
            {paddingBottom > 0 ? <tr aria-hidden="true"><td colSpan={table.getVisibleLeafColumns().length} style={{ height: paddingBottom }} /></tr> : null}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function MobilePositionCard({ position, quote }: { position: PortfolioPosition; quote?: PortfolioAfterHoursPosition }) {
  const implausible = position.pnl_pct > 400 || position.pnl_pct < -75;
  return <div className="p-4">
    <div className="flex items-start justify-between gap-3">
      <div><Link className="inline-flex items-center gap-1.5 font-semibold text-[#172033]" href={`/sell-monitor/${position.ticker}`}>{position.ticker}<ExternalLink size={13} /></Link><div className="mt-0.5 text-xs text-[#687386]">{position.name}</div></div>
      <StatusChip tone={implausible ? "bad" : statusTone[position.status]}>{implausible ? "Daten prüfen" : portfolioStatusLabel(position.status)}</StatusChip>
    </div>
    <div className="mt-3 grid grid-cols-2 gap-2 text-sm">
      <MobileMetric label="Wert" value={formatMoney(position.market_value, position.currency, 0)} />
      <MobileMetric label="P&L" value={formatPercent(position.pnl_pct)} tone={position.pnl_pct >= 0 ? "good" : "bad"} />
      <MobileMetric label="Kurs" value={formatMoney(position.current_price, position.currency)} />
      <MobileMetric label="Stopp" value={position.stop_price ? formatMoney(position.stop_price, "USD") : "Nicht gepflegt"} />
      {quote?.available ? <MobileMetric label="After Market" value={formatPercent(quote.after_hours_change_pct)} tone={(quote.after_hours_change_pct ?? 0) >= 0 ? "good" : "bad"} /> : null}
    </div>
  </div>;
}

function MobileMetric({ label, value, tone = "neutral" }: { label: string; value: string; tone?: Tone }) {
  const color = tone === "good" ? "text-[#138a57]" : tone === "bad" ? "text-[#c2413b]" : "text-[#172033]";
  return <div className="rounded-[8px] bg-[#f7f9fb] px-2.5 py-2"><div className="text-[10px] uppercase text-[#687386]">{label}</div><div className={`mt-0.5 font-semibold ${color}`}>{value}</div></div>;
}

function AfterHoursCell({ quote }: { quote?: PortfolioAfterHoursPosition }) {
  if (!quote) return <span className="text-[#8b95a5]">Nicht geladen</span>;
  if (!quote.available || typeof quote.after_hours_price !== "number") return <span className="text-[#8b95a5]">Nicht verfügbar</span>;
  const value = quote.after_hours_change_pct ?? 0;
  return <div className={value >= 0 ? "text-[#138a57]" : "text-[#c2413b]"}><div className="font-medium">{formatMoney(quote.after_hours_price, quote.currency)}</div><div className="text-xs">{formatPercent(value, 2)}</div></div>;
}

function SignedValue({ value, suffix, digits = 1 }: { value: number; suffix: string; digits?: number }) {
  return <span className={value >= 0 ? "font-medium text-[#138a57]" : "font-medium text-[#c2413b]"}>{value > 0 ? "+" : ""}{formatNumber(value, digits)}{suffix}</span>;
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
  return <div className="flex items-center gap-2" onClick={(event) => event.stopPropagation()}>
    <input
      aria-label={`${position.ticker} Stopp USD`}
      className="h-8 w-24 rounded-[7px] border border-[#d8e1ea] bg-white px-2 text-right text-sm tabular-nums text-[#172033] outline-none focus:border-[#0f766e]"
      inputMode="decimal" placeholder="–" value={value} disabled={mutation.isPending}
      onBlur={save} onChange={(event) => setValue(event.target.value)}
      onKeyDown={(event) => { if (event.key === "Enter") event.currentTarget.blur(); if (event.key === "Escape") { setValue(formatEditableNumber(position.stop_price)); event.currentTarget.blur(); } }}
    />
    {mutation.isPending ? <span className="text-xs text-[#687386]">speichert</span> : null}
    {mutation.isError ? <span className="text-xs text-[#c2413b]">Fehler</span> : null}
  </div>;
}

function EmptyPortfolio() {
  return <div className="rounded-[14px] border border-[#e3e8ef] bg-white p-5"><div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between"><div><h2 className="font-semibold text-[#172033]">Keine offenen Positionen</h2><p className="mt-1 text-sm text-[#687386]">Importiere dein Depot, damit Portfolio und Verkaufsmonitor echte Daten nutzen.</p></div><Link className="inline-flex items-center justify-center gap-2 rounded-[9px] bg-[#0f766e] px-4 py-2 text-sm font-semibold text-white" href="/portfolio/imports"><Upload size={16} /> Import öffnen</Link></div></div>;
}

function columnLabel(id: string) {
  return ({ ticker: "Position", market_value: "Wert", current_price: "Kurs", after_hours: "After Market", pnl_pct: "P&L %", pnl_abs: "P&L absolut", weight_pct: "Gewicht", atr_pct: "ATR", beta_balancer_score: "Beta-Balancer", risk_contribution: "Risikobeitrag", stop_price: "Stopp", position_loss_risk: "Verlustrisiko", status: "Status" } as Record<string, string>)[id] ?? id;
}

function readStoredState<T>(key: string, fallback: T): T {
  try { const raw = window.localStorage.getItem(key); return raw ? JSON.parse(raw) as T : fallback; } catch { return fallback; }
}

function invalidatePortfolioTable(queryClient: ReturnType<typeof useQueryClient>) {
  void queryClient.invalidateQueries({ queryKey: ["portfolio-snapshot"] });
  void queryClient.invalidateQueries({ queryKey: ["portfolio-positions"] });
  void queryClient.invalidateQueries({ queryKey: ["portfolio-curve"] });
  void queryClient.invalidateQueries({ queryKey: ["sell-ranking"] });
}

function formatEditableNumber(value: number | null | undefined) { return typeof value === "number" && Number.isFinite(value) ? String(Number(value.toFixed(2))) : ""; }
function parseEditableNumber(value: string) { const parsed = Number(value.trim().replace(",", ".")); return Number.isFinite(parsed) && parsed > 0 ? Number(parsed.toFixed(4)) : null; }
function numbersEqual(left: number | null, right: number | null) { return left === null || right === null ? left === right : Math.abs(left - right) < 0.0001; }
