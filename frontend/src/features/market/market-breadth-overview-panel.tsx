"use client";

import { useQuery } from "@tanstack/react-query";
import { RotateCw } from "lucide-react";
import { StatusChip } from "@/components/ui/status-chip";
import { api } from "@/lib/api/client";
import type { MarketBreadthSignal, Tone } from "@/lib/types/api";
import { labelForSource, labelForStatus, toneForSource, toneForStatus } from "./data-status";
import { MARKET_REFETCH_INTERVAL_MS } from "./query-timing";

export function MarketBreadthOverviewPanel({ ticker = "^GSPC" }: { ticker?: string }) {
  const query = useQuery({
    queryKey: ["market-breadth-overview", ticker],
    queryFn: () => api.marketBreadthOverview(260, ticker),
    staleTime: 60_000,
    refetchInterval: MARKET_REFETCH_INTERVAL_MS
  });
  const data = query.data;

  if (query.isLoading) {
    return (
      <section className="rounded-[24px] border border-[#e3e8ef] bg-white p-5 text-sm text-[#687386] shadow-[0_10px_28px_rgba(15,23,42,0.06)]">
        Marktbreite lädt...
      </section>
    );
  }

  if (query.error || !data) {
    return (
      <section className="rounded-[24px] border border-[#f0b9b5] bg-[#fff0ef] p-5 text-sm font-medium text-[#c2413b]">
        Marktbreite ist aktuell nicht erreichbar.
      </section>
    );
  }

  return (
    <section className="space-y-4">
      <div className="rounded-[24px] border border-[#e3e8ef] bg-white p-5 shadow-[0_10px_28px_rgba(15,23,42,0.06)]">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <div className="mb-3 flex flex-wrap items-center gap-2">
              <StatusChip tone={toneForSource(data.source)}>{labelForSource(data.source)}</StatusChip>
              <StatusChip tone={toneForStatus(data.data_status)}>{labelForStatus(data.data_status)}</StatusChip>
              <StatusChip tone={coverageTone(data.coverage_ratio)}>
                Coverage {(data.coverage_ratio * 100).toFixed(0)}%
              </StatusChip>
              {data.requested_universe ? (
                <StatusChip tone="neutral">
                  {data.loaded_universe}/{data.requested_universe} Titel
                </StatusChip>
              ) : (
                <StatusChip tone="neutral">{data.loaded_universe} Titel</StatusChip>
              )}
            </div>
            <h3 className="text-xl font-semibold tracking-normal">Signalübersicht</h3>
            <p className="mt-2 max-w-4xl text-sm leading-6 text-[#687386]">{data.message}</p>
            <p className="mt-2 text-xs font-medium text-[#687386]">Stand {data.as_of}</p>
          </div>
          <button
            className="inline-flex w-fit items-center gap-2 rounded-full border border-[#d8e1ea] bg-white px-4 py-2 text-sm font-medium text-[#172033] shadow-sm transition hover:border-[#0f766e]"
            type="button"
            onClick={() => query.refetch()}
          >
            <RotateCw size={15} className={query.isFetching ? "animate-spin text-[#0f766e]" : "text-[#687386]"} />
            Aktualisieren
          </button>
        </div>
      </div>

      {data.signals.length === 0 ? (
        <div className="rounded-[24px] border border-[#e3e8ef] bg-white p-4 text-sm text-[#687386] shadow-[0_10px_28px_rgba(15,23,42,0.06)]">
          Keine Marktbreite-Signale im Cache.
        </div>
      ) : (
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {data.signals.map((signal) => (
            <BreadthSignalCard key={signal.key} signal={signal} />
          ))}
        </div>
      )}
    </section>
  );
}

function BreadthSignalCard({ signal }: { signal: MarketBreadthSignal }) {
  return (
    <div className={["min-h-[188px] rounded-[24px] border p-5 shadow-[0_10px_28px_rgba(15,23,42,0.06)]", cardClass(signal.tone)].join(" ")}>
      <div className="mb-3 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-xs font-semibold uppercase tracking-[0.12em] text-[#687386]">{signal.title}</div>
          <div className={["mt-2 break-words text-2xl font-semibold leading-tight tracking-normal tabular-nums", toneText(signal.tone)].join(" ")}>
            {signal.value}
          </div>
        </div>
        <StatusChip tone={signal.tone}>{toneLabel(signal.tone)}</StatusChip>
      </div>
      <div className="text-sm leading-6 text-[#172033]">{signal.detail}</div>
      {signal.comment && <div className="mt-2 text-xs leading-5 text-[#687386]">{signal.comment}</div>}
      {signal.key === "equal_weight_etfs" && <EqualWeightDetails signal={signal} />}
      {signal.key === "russell_vs_sp500" && <RussellDetails signal={signal} />}
    </div>
  );
}

function EqualWeightDetails({ signal }: { signal: MarketBreadthSignal }) {
  const tickers = readRecord(signal.metrics.tickers);
  const rsp = readRecord(tickers.RSP);
  const qqew = readRecord(tickers.QQEW);
  return (
    <div className="mt-3 grid gap-2 text-xs text-[#687386] sm:grid-cols-2">
      <EtfMiniRow label="RSP" dayPct={readNumber(rsp.day_pct)} drawdown={readNumber(rsp.drawdown_from_high_pct)} />
      <EtfMiniRow label="QQEW" dayPct={readNumber(qqew.day_pct)} drawdown={readNumber(qqew.drawdown_from_high_pct)} />
    </div>
  );
}

function EtfMiniRow({ dayPct, drawdown, label }: { dayPct?: number; drawdown?: number; label: string }) {
  return (
    <div className="rounded-2xl border border-[#e3e8ef] bg-white/82 px-3 py-2">
      <div className="font-semibold text-[#172033]">{label}</div>
      <div className={pctClass(dayPct)}>Tag {formatPct(dayPct)}</div>
      <div>52W-Abstand {drawdown === undefined ? "-" : `-${drawdown.toFixed(1)}%`}</div>
    </div>
  );
}

function RussellDetails({ signal }: { signal: MarketBreadthSignal }) {
  return (
    <div className="mt-3 grid gap-2 text-xs text-[#687386] sm:grid-cols-3">
      <MiniMetric label="Russell 20T" value={formatPct(readNumber(signal.metrics.russell_return_20d_pct))} />
      <MiniMetric label="S&P 20T" value={formatPct(readNumber(signal.metrics.sp500_return_20d_pct))} />
      <MiniMetric label="Relativ" value={formatPct(readNumber(signal.metrics.relative_return_20d_pct))} />
    </div>
  );
}

function MiniMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl border border-[#e3e8ef] bg-white/82 px-3 py-2">
      <div>{label}</div>
      <div className="mt-1 font-semibold text-[#172033]">{value}</div>
    </div>
  );
}

function readRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function readNumber(value: unknown) {
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

function coverageTone(value: number): Tone {
  if (value >= 0.8) return "good";
  if (value >= 0.5) return "warning";
  return "bad";
}

function cardClass(tone: Tone) {
  if (tone === "good") return "border-[#b7e2cf] bg-[#eaf7ef]";
  if (tone === "bad") return "border-[#f0b9b5] bg-[#fff0ef]";
  if (tone === "warning") return "border-[#efd58f] bg-[#fff7df]";
  return "border-[#d8e1ea] bg-white";
}

function toneText(tone: Tone) {
  if (tone === "good") return "text-[#138a57]";
  if (tone === "bad") return "text-[#c2413b]";
  if (tone === "warning") return "text-[#9a650f]";
  return "text-[#2563eb]";
}

function toneLabel(tone: Tone) {
  if (tone === "good") return "positiv";
  if (tone === "bad") return "negativ";
  if (tone === "warning") return "warnend";
  return "neutral";
}

function pctClass(value?: number) {
  if (value === undefined) return "text-[#687386]";
  return value >= 0 ? "font-medium text-[#138a57]" : "font-medium text-[#c2413b]";
}

function formatPct(value?: number) {
  if (value === undefined) return "-";
  return `${value >= 0 ? "+" : ""}${value.toFixed(1)}%`;
}
