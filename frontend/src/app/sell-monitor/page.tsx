"use client";

import {
  ColumnDef,
  Table,
  VisibilityState,
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  SortingState,
  useReactTable
} from "@tanstack/react-table";
import { useVirtualizer } from "@tanstack/react-virtual";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowUpDown, Columns3, ExternalLink, RefreshCw } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { KpiCard } from "@/components/ui/kpi-card";
import { StatusChip } from "@/components/ui/status-chip";
import { api } from "@/lib/api/client";
import { formatPercent, qualityLabel } from "@/lib/format";
import type { PendingStatus, SellRankingRow, Tone } from "@/lib/types/api";

const SORT_KEY = "sell-ranking-sorting-v1";
const VISIBILITY_KEY = "sell-ranking-columns-v1";
const toneByStatus: Record<SellRankingRow["status"], Tone> = { Halten: "good", Beobachten: "warning", Verkaufen: "bad" };
const toneByPending: Record<PendingStatus, Tone> = { halten: "good", in_bestaetigung: "warning", snoozed: "neutral", scharf: "bad" };

export default function SellMonitorPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { data, isLoading } = useQuery({ queryKey: ["sell-ranking"], queryFn: api.sellRanking });
  const monitorMutation = useMutation({
    mutationFn: () => api.startJob({ type: "position_atr_monitor", payload: { mode: "manual", source: "sell_monitor", force: true } }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["jobs"] });
      window.setTimeout(() => void queryClient.invalidateQueries({ queryKey: ["sell-ranking"] }), 2500);
    }
  });
  const rows = data?.rows ?? [];
  const [sorting, setSorting] = useState<SortingState>([{ id: "recommendation_pct", desc: true }]);
  const [columnVisibility, setColumnVisibility] = useState<VisibilityState>({});
  useEffect(() => {
    setSorting(readStoredState(SORT_KEY, [{ id: "recommendation_pct", desc: true }]));
    setColumnVisibility(readStoredState(VISIBILITY_KEY, {}));
  }, []);
  useEffect(() => { window.localStorage.setItem(SORT_KEY, JSON.stringify(sorting)); }, [sorting]);
  useEffect(() => { window.localStorage.setItem(VISIBILITY_KEY, JSON.stringify(columnVisibility)); }, [columnVisibility]);

  const columns = useMemo<ColumnDef<SellRankingRow>[]>(() => [
    { accessorKey: "ticker", header: "Position", cell: ({ row }) => <div><div className="font-semibold text-[#172033]">{row.original.ticker}</div><div className="text-xs text-[#687386]">{row.original.name}</div></div> },
    { accessorKey: "pnl_pct", header: "P&L", cell: ({ getValue }) => <span className={Number(getValue()) >= 0 ? "font-medium text-[#138a57]" : "font-medium text-[#c2413b]"}>{formatPercent(Number(getValue()))}</span> },
    { accessorKey: "health_score", header: "Gesundheit", cell: ({ row, getValue }) => row.original.data_quality_status === "blocked" ? "–" : Number(getValue()).toFixed(0) },
    { accessorKey: "recommendation_pct", header: "Tranche", cell: ({ row, getValue }) => row.original.data_quality_status === "blocked" ? "–" : `${Number(getValue())}%` },
    {
      accessorKey: "status", header: "Entscheidung", cell: ({ row }) => {
        const quality = row.original.data_quality_status;
        return <StatusChip tone={quality === "blocked" ? "bad" : toneByStatus[row.original.status]}>{quality === "blocked" ? "Daten prüfen" : row.original.status}</StatusChip>;
      }
    },
    {
      accessorKey: "pending_status", header: "Bestätigung", cell: ({ row }) => <div className="space-y-1"><StatusChip tone={toneByPending[row.original.pending_status]}>{pendingLabel(row.original.pending_status)}</StatusChip><div className="text-xs text-[#687386]">{row.original.pending_status === "snoozed" && row.original.snoozed_until ? `bis ${row.original.snoozed_until}` : `${row.original.consecutive_days} Tage`}</div></div>
    },
    { accessorKey: "primary_signal", header: "Grund", cell: ({ row }) => <div className="max-w-[420px] truncate text-[#4b5565]" title={row.original.data_quality_status === "trusted" ? row.original.primary_signal : row.original.data_quality_detail}>{row.original.data_quality_status === "trusted" ? row.original.primary_signal || row.original.reason : row.original.data_quality_detail}</div> },
    { accessorKey: "data_quality_status", header: "Datenbasis", cell: ({ row }) => <StatusChip tone={qualityTone(row.original.data_quality_status)}>{qualityLabel(row.original.data_quality_status)}</StatusChip> }
  ], []);

  // eslint-disable-next-line react-hooks/incompatible-library
  const table = useReactTable({ data: rows, columns, state: { sorting, columnVisibility }, onSortingChange: setSorting, onColumnVisibilityChange: setColumnVisibility, getCoreRowModel: getCoreRowModel(), getSortedRowModel: getSortedRowModel() });
  const tableRows = table.getRowModel().rows;
  const scrollParentRef = useRef<HTMLDivElement>(null);
  const virtualizer = useVirtualizer({ count: tableRows.length, getScrollElement: () => scrollParentRef.current, estimateSize: () => 60, overscan: 10 });
  const virtualRows = virtualizer.getVirtualItems();
  const totalSize = virtualizer.getTotalSize();
  const paddingTop = virtualRows.length ? virtualRows[0].start : 0;
  const paddingBottom = virtualRows.length ? totalSize - virtualRows[virtualRows.length - 1].end : 0;

  const trustedRows = rows.filter((row) => row.data_quality_status !== "blocked");
  const sellCount = trustedRows.filter((row) => row.status === "Verkaufen").length;
  const watchCount = trustedRows.filter((row) => row.status === "Beobachten").length;
  const blockedCount = rows.length - trustedRows.length;
  const averageHealth = trustedRows.length ? trustedRows.reduce((sum, row) => sum + row.health_score, 0) / trustedRows.length : 0;

  return <div className="space-y-4">
    <div className="flex flex-col gap-3 rounded-[14px] border border-[#e3e8ef] bg-white px-4 py-3 shadow-[0_5px_18px_rgba(15,23,42,0.05)] lg:flex-row lg:items-center lg:justify-between">
      <div className="flex flex-wrap items-center gap-2 text-xs text-[#687386]"><span className="font-semibold uppercase tracking-[0.08em]">Stand</span><StatusChip tone={data?.source === "snapshot" ? "good" : "warning"}>{data?.source === "snapshot" ? "Vorberechnet" : "Direkt berechnet"}</StatusChip><span>{data?.generated_at ? new Date(data.generated_at).toLocaleString("de-DE") : "noch nicht verfügbar"}</span></div>
      <div className="flex items-center gap-2">
        <button className="inline-flex h-9 items-center gap-2 rounded-[9px] border border-[#d8e1ea] px-3 text-sm font-medium text-[#172033] disabled:opacity-55" type="button" disabled={monitorMutation.isPending} onClick={() => monitorMutation.mutate()}><RefreshCw size={15} className={monitorMutation.isPending ? "animate-spin" : ""} />{monitorMutation.isPending ? "Startet" : "Monitor aktualisieren"}</button>
        <StatusChip tone={isLoading ? "warning" : "good"}>{isLoading ? "Lädt" : `${rows.length} Positionen`}</StatusChip>
      </div>
    </div>

    <div className="grid gap-2.5 sm:grid-cols-2 xl:grid-cols-4">
      <KpiCard item={{ label: "Verkaufen", value: String(sellCount), detail: "nur bei verlässlicher Datenbasis", tone: sellCount ? "bad" : "good" }} />
      <KpiCard item={{ label: "Beobachten", value: String(watchCount), detail: "Bestätigung ausstehend", tone: watchCount ? "warning" : "neutral" }} />
      <KpiCard item={{ label: "Daten prüfen", value: String(blockedCount), detail: "Empfehlung bewusst unterdrückt", tone: blockedCount ? "bad" : "good" }} />
      <KpiCard item={{ label: "Ø Gesundheit", value: averageHealth.toFixed(0), detail: "nur verlässliche Positionen", tone: averageHealth >= 65 ? "good" : averageHealth >= 40 ? "warning" : "bad" }} />
    </div>

    <section className="overflow-hidden rounded-[14px] border border-[#e3e8ef] bg-white shadow-[0_5px_18px_rgba(15,23,42,0.05)]">
      <div className="flex items-center justify-between border-b border-[#e8edf2] px-4 py-3"><div><h2 className="text-sm font-semibold text-[#172033]">Positionssignale</h2><p className="mt-0.5 text-xs text-[#687386]">Sortierung und Spaltenauswahl werden lokal gespeichert.</p></div><ColumnMenu table={table} /></div>
      <div className="divide-y divide-[#e8edf2] md:hidden">{tableRows.map((row) => <MobileSellRow key={row.id} row={row.original} />)}</div>
      <div ref={scrollParentRef} className="hidden max-h-[560px] overflow-auto md:block">
        <table className="w-full min-w-[1100px] border-collapse text-sm">
          <thead className="sticky top-0 z-10 bg-[#f6f8fb] text-left text-[10px] uppercase tracking-[0.06em] text-[#687386]">{table.getHeaderGroups().map((group) => <tr key={group.id}>{group.headers.map((header) => <th key={header.id} className="border-b border-[#e3e8ef] px-3 py-3 font-semibold">{header.isPlaceholder ? null : <button className="inline-flex items-center gap-1.5" type="button" onClick={header.column.getToggleSortingHandler()}>{flexRender(header.column.columnDef.header, header.getContext())}<ArrowUpDown size={12} /></button>}</th>)}</tr>)}</thead>
          <tbody>
            {paddingTop > 0 ? <tr aria-hidden="true"><td colSpan={table.getVisibleLeafColumns().length} style={{ height: paddingTop }} /></tr> : null}
            {virtualRows.map((virtualRow) => { const row = tableRows[virtualRow.index]; return <tr key={row.id} className="cursor-pointer border-b border-[#eef2f6] transition hover:bg-[#f6faf9]" onClick={() => router.push(`/sell-monitor/${row.original.ticker}`)}>{row.getVisibleCells().map((cell) => <td key={cell.id} className="px-3 py-3">{flexRender(cell.column.columnDef.cell, cell.getContext())}</td>)}</tr>; })}
            {paddingBottom > 0 ? <tr aria-hidden="true"><td colSpan={table.getVisibleLeafColumns().length} style={{ height: paddingBottom }} /></tr> : null}
          </tbody>
        </table>
      </div>
    </section>
  </div>;
}

function ColumnMenu({ table }: { table: Table<SellRankingRow> }) {
  return <details className="relative"><summary className="inline-flex h-9 cursor-pointer list-none items-center gap-2 rounded-[9px] border border-[#d8e1ea] px-3 text-sm font-medium"><Columns3 size={15} /> Spalten</summary><div className="absolute right-0 z-20 mt-2 w-52 rounded-[10px] border border-[#d8e1ea] bg-white p-2 shadow-[0_14px_32px_rgba(15,23,42,0.14)]">{table.getAllLeafColumns().filter((column) => column.getCanHide()).map((column) => <label key={column.id} className="flex items-center gap-2 rounded px-2 py-1.5 text-sm hover:bg-[#f5f8fa]"><input checked={column.getIsVisible()} type="checkbox" onChange={column.getToggleVisibilityHandler()} />{columnLabel(column.id)}</label>)}</div></details>;
}

function MobileSellRow({ row }: { row: SellRankingRow }) {
  const blocked = row.data_quality_status === "blocked";
  return <div className="p-4"><div className="flex items-start justify-between gap-3"><div><Link className="inline-flex items-center gap-1.5 font-semibold text-[#172033]" href={`/sell-monitor/${row.ticker}`}>{row.ticker}<ExternalLink size={13} /></Link><div className="text-xs text-[#687386]">{row.name}</div></div><StatusChip tone={blocked ? "bad" : toneByStatus[row.status]}>{blocked ? "Daten prüfen" : row.status}</StatusChip></div><div className="mt-3 grid grid-cols-3 gap-2 text-sm"><Mini label="P&L" value={formatPercent(row.pnl_pct)} /><Mini label="Gesundheit" value={blocked ? "–" : row.health_score.toFixed(0)} /><Mini label="Tranche" value={blocked ? "–" : `${row.recommendation_pct}%`} /></div><p className="mt-2 text-xs leading-5 text-[#687386]">{blocked ? row.data_quality_detail : row.primary_signal || row.reason}</p></div>;
}

function Mini({ label, value }: { label: string; value: string }) { return <div className="rounded-[8px] bg-[#f7f9fb] px-2 py-2"><div className="text-[9px] uppercase text-[#687386]">{label}</div><div className="mt-0.5 font-semibold text-[#172033]">{value}</div></div>; }
function qualityTone(status: SellRankingRow["data_quality_status"]): Tone { return status === "trusted" ? "good" : status === "blocked" ? "bad" : "warning"; }
function pendingLabel(status: PendingStatus) { return ({ halten: "Intakt", in_bestaetigung: "Bestätigung", snoozed: "Pausiert", scharf: "Aktiv" } as const)[status]; }
function columnLabel(id: string) { return ({ ticker: "Position", pnl_pct: "P&L", health_score: "Gesundheit", recommendation_pct: "Tranche", status: "Entscheidung", pending_status: "Bestätigung", primary_signal: "Grund", data_quality_status: "Datenbasis" } as Record<string, string>)[id] ?? id; }
function readStoredState<T>(key: string, fallback: T): T { try { const raw = window.localStorage.getItem(key); return raw ? JSON.parse(raw) as T : fallback; } catch { return fallback; } }
