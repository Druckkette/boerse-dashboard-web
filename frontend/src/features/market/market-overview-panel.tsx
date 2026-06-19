"use client";

import { useQuery } from "@tanstack/react-query";
import { KpiCard } from "@/components/ui/kpi-card";
import { StatusChip } from "@/components/ui/status-chip";
import { api } from "@/lib/api/client";
import { labelForSource, labelForStatus, toneForSource, toneForStatus } from "./data-status";
import { MARKET_REFETCH_INTERVAL_MS } from "./query-timing";

export function MarketOverviewPanel() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["market-overview"],
    queryFn: api.marketOverview,
    staleTime: 60_000,
    refetchInterval: MARKET_REFETCH_INTERVAL_MS
  });

  if (isLoading) return <div className="rounded border border-[#2d333d] p-4">Market lädt...</div>;
  if (error || !data) return <div className="rounded border border-rose-400/40 p-4">Market API nicht erreichbar.</div>;

  return (
    <section className="space-y-4">
      <div className="rounded border border-[#2d333d] bg-[#171a20] p-5">
        <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
          <div>
            <div className="mb-3 flex flex-wrap items-center gap-2">
              <StatusChip tone={toneForPhase(data.phase)}>{data.phase_label}</StatusChip>
              {data.trend_ampel && (
                <StatusChip tone={toneForPhase(data.trend_ampel.phase)}>
                  {data.trend_ampel.ticker} {data.trend_ampel.phase_label}
                </StatusChip>
              )}
              <StatusChip tone={toneForBreadthMode(data.breadth_mode)}>
                EW-Breite: {breadthLabel(data.breadth_mode)}
              </StatusChip>
              <StatusChip tone="neutral">{data.volatility_regime}</StatusChip>
              <StatusChip tone={toneForSource(data.source)}>{labelForSource(data.source)}</StatusChip>
              <StatusChip tone={toneForStatus(data.data_status)}>{labelForStatus(data.data_status)}</StatusChip>
            </div>
            <h1 className="text-2xl font-semibold tracking-normal md:text-3xl">Marktstatus</h1>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-[#a0a7b4]">{data.action}</p>
            {data.message && <p className="mt-2 max-w-3xl text-xs leading-5 text-[#77808f]">{data.message}</p>}
          </div>
          <div className="rounded border border-[#2d333d] bg-[#111419] px-4 py-3 text-left md:text-right">
            <div className="text-xs uppercase text-[#a0a7b4]">Warnzeichen</div>
            <div className="mt-1 text-3xl font-semibold">{data.warning_count}</div>
            <div className="mt-1 text-xs text-[#77808f]">Stand {data.as_of}</div>
          </div>
        </div>
      </div>
      {data.trend_ampel && (
        <div className="grid gap-3 md:grid-cols-4">
          <div className="rounded border border-[#2d333d] bg-[#171a20] p-4">
            <div className="mb-3 flex items-center justify-between gap-3">
              <div className="text-sm text-[#a0a7b4]">Trend-Ampel</div>
              <StatusChip tone={toneForPhase(data.trend_ampel.phase)}>{data.trend_ampel.phase_label}</StatusChip>
            </div>
            <div className="text-2xl font-semibold tracking-normal">{data.trend_ampel.ticker}</div>
            <div className="mt-2 text-sm text-[#a0a7b4]">Stand {data.trend_ampel.as_of}</div>
          </div>
          <div className="rounded border border-[#2d333d] bg-[#171a20] p-4">
            <div className="text-sm text-[#a0a7b4]">Close</div>
            <div className="mt-3 text-2xl font-semibold tracking-normal">
              {formatNumber(data.trend_ampel.close)}
            </div>
            <div className="mt-2 text-sm text-[#a0a7b4]">Distribution {data.trend_ampel.dist_count_25}</div>
          </div>
          <div className="rounded border border-[#2d333d] bg-[#171a20] p-4">
            <div className="text-sm text-[#a0a7b4]">Anchor</div>
            <div className="mt-3 text-2xl font-semibold tracking-normal">{data.trend_ampel.anchor_date ?? "-"}</div>
            <div className="mt-2 text-sm text-[#a0a7b4]">Floor {formatNumber(data.trend_ampel.floor_mark)}</div>
          </div>
          <div className="rounded border border-[#2d333d] bg-[#171a20] p-4">
            <div className="text-sm text-[#a0a7b4]">Startschuss</div>
            <div className="mt-3 text-2xl font-semibold tracking-normal">
              {formatNumber(data.trend_ampel.startschuss_low)}
            </div>
            <div className="mt-2 text-sm text-[#a0a7b4]">
              Bonus {data.trend_ampel.startschuss_bonus ? "aktiv" : "inaktiv"}
            </div>
          </div>
        </div>
      )}
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {data.kpis.map((item) => (
          <KpiCard key={item.label} item={item} />
        ))}
      </div>
    </section>
  );
}

function toneForPhase(phase: string) {
  if (phase === "gruen" || phase === "aufwaertstrend") return "good";
  if (phase === "gelb" || phase === "neutral") return "warning";
  return "bad";
}

function toneForBreadthMode(mode: string) {
  if (mode === "rueckenwind") return "good";
  if (mode === "wachsam") return "warning";
  return "bad";
}

function breadthLabel(mode: string) {
  if (mode === "rueckenwind") return "Rückenwind";
  if (mode === "wachsam") return "Wachsam";
  return "Schutz";
}

function formatNumber(value?: number | null) {
  if (value === null || value === undefined) return "-";
  return new Intl.NumberFormat("de-DE", { maximumFractionDigits: 2 }).format(value);
}
