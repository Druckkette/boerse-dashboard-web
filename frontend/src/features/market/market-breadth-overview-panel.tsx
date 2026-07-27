"use client";

import { useQuery } from "@tanstack/react-query";
import { ChevronDown, RotateCw } from "lucide-react";
import { StatusChip } from "@/components/ui/status-chip";
import { api } from "@/lib/api/client";
import { formatPercent } from "@/lib/format";
import type { MarketBreadthSignal, Tone } from "@/lib/types/api";
import { labelForStatus, toneForStatus } from "./data-status";
import { MARKET_REFETCH_INTERVAL_MS } from "./query-timing";

export function MarketBreadthOverviewPanel({ ticker = "^GSPC" }: { ticker?: string }) {
  const query = useQuery({
    queryKey: ["market-breadth-overview", ticker],
    queryFn: () => api.marketBreadthOverview(260, ticker),
    staleTime: 60_000,
    refetchInterval: MARKET_REFETCH_INTERVAL_MS
  });
  if (query.isLoading) return <section className="rounded-[12px] border border-[#e3e8ef] bg-white p-4 text-sm text-[#687386]">Marktbreite lädt...</section>;
  if (query.error || !query.data) return <section className="rounded-[12px] border border-[#f0b9b5] bg-[#fff0ef] p-4 text-sm font-medium text-[#c2413b]">Marktbreite ist aktuell nicht erreichbar.</section>;
  const data = query.data;
  return <section className="overflow-hidden rounded-[14px] border border-[#e3e8ef] bg-white shadow-[0_5px_18px_rgba(15,23,42,0.05)]">
    <div className="flex flex-col gap-3 border-b border-[#e8edf2] px-4 py-3 lg:flex-row lg:items-center lg:justify-between">
      <div className="flex flex-wrap items-center gap-2">
        <StatusChip tone={toneForStatus(data.data_status)}>{labelForStatus(data.data_status)}</StatusChip>
        <span className="text-xs text-[#687386]">Abdeckung {(data.coverage_ratio * 100).toFixed(0)}% · {data.loaded_universe}/{data.requested_universe || data.loaded_universe} Titel · Stand {data.as_of}</span>
      </div>
      <button aria-label="Marktbreite aktualisieren" className="inline-flex h-8 w-fit items-center gap-2 rounded-[8px] border border-[#d8e1ea] px-2.5 text-xs font-semibold text-[#172033]" type="button" onClick={() => query.refetch()}><RotateCw size={14} className={query.isFetching ? "animate-spin text-[#0f766e]" : "text-[#687386]"} /> Aktualisieren</button>
    </div>
    {data.signals.length ? <div className="divide-y divide-[#e8edf2]">{data.signals.map((signal) => <BreadthSignalRow key={signal.key} signal={signal} />)}</div> : <div className="p-4 text-sm text-[#687386]">Keine Marktbreite-Signale im Cache.</div>}
  </section>;
}

function BreadthSignalRow({ signal }: { signal: MarketBreadthSignal }) {
  const hasDetails = signal.key === "equal_weight_etfs" || signal.key === "russell_vs_sp500";
  const content = <>
    <div className="min-w-0"><div className="text-sm font-semibold text-[#172033]">{signal.title}</div><div className="mt-0.5 text-xs leading-5 text-[#687386]">{signal.detail}</div>{signal.comment ? <div className="mt-0.5 text-[11px] leading-4 text-[#8b95a5]">{signal.comment}</div> : null}</div>
    <div className={`text-right text-lg font-semibold tabular-nums ${toneText(signal.tone)}`}>{signal.value}</div>
    <div className="flex justify-end"><StatusChip tone={signal.tone}>{toneLabel(signal.tone)}</StatusChip></div>
  </>;
  if (!hasDetails) return <div className="grid gap-2 px-4 py-3 sm:grid-cols-[minmax(0,1fr)_150px_110px] sm:items-center">{content}</div>;
  return <details className="group px-4 py-3">
    <summary className="grid cursor-pointer list-none gap-2 sm:grid-cols-[minmax(0,1fr)_150px_110px_20px] sm:items-center">{content}<ChevronDown className="size-4 text-[#8b95a5] transition group-open:rotate-180" /></summary>
    <div className="mt-3 border-t border-[#edf1f5] pt-3">{signal.key === "equal_weight_etfs" ? <EqualWeightDetails signal={signal} /> : <RussellDetails signal={signal} />}</div>
  </details>;
}

function EqualWeightDetails({ signal }: { signal: MarketBreadthSignal }) {
  const tickers = readRecord(signal.metrics.tickers);
  return <div className="grid gap-2 sm:grid-cols-2"><EtfMetric label="RSP" values={readRecord(tickers.RSP)} /><EtfMetric label="QQEW" values={readRecord(tickers.QQEW)} /></div>;
}

function EtfMetric({ label, values }: { label: string; values: Record<string, unknown> }) {
  const drawdown = readNumber(values.drawdown_from_high_pct);
  return <div className="grid grid-cols-3 items-center gap-2 rounded-[9px] bg-[#f7f9fb] px-3 py-2 text-xs"><span className="font-semibold text-[#172033]">{label}</span><span className={toneText((readNumber(values.day_pct) ?? 0) >= 0 ? "good" : "bad")}>Tag {formatPercent(readNumber(values.day_pct))}</span><span className="text-right text-[#687386]">52W {drawdown === undefined ? "–" : `-${drawdown.toFixed(1)}%`}</span></div>;
}

function RussellDetails({ signal }: { signal: MarketBreadthSignal }) {
  return <div className="grid gap-2 sm:grid-cols-3"><Mini label="Russell 20T" value={formatPercent(readNumber(signal.metrics.russell_return_20d_pct))} /><Mini label="S&P 20T" value={formatPercent(readNumber(signal.metrics.sp500_return_20d_pct))} /><Mini label="Relativ" value={formatPercent(readNumber(signal.metrics.relative_return_20d_pct))} /></div>;
}

function Mini({ label, value }: { label: string; value: string }) { return <div className="rounded-[9px] bg-[#f7f9fb] px-3 py-2"><div className="text-[10px] uppercase text-[#687386]">{label}</div><div className="mt-0.5 text-sm font-semibold text-[#172033]">{value}</div></div>; }
function readRecord(value: unknown): Record<string, unknown> { return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {}; }
function readNumber(value: unknown) { return typeof value === "number" && Number.isFinite(value) ? value : undefined; }
function toneText(tone: Tone) { return tone === "good" ? "text-[#138a57]" : tone === "bad" ? "text-[#c2413b]" : tone === "warning" ? "text-[#9a650f]" : "text-[#2563eb]"; }
function toneLabel(tone: Tone) { return tone === "good" ? "Bestanden" : tone === "bad" ? "Warnung" : tone === "warning" ? "Wachsam" : "Neutral"; }
