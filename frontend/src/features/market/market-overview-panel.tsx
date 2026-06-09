"use client";

import { useQuery } from "@tanstack/react-query";
import { KpiCard } from "@/components/ui/kpi-card";
import { StatusChip } from "@/components/ui/status-chip";
import { api } from "@/lib/api/client";
import { labelForSource, labelForStatus, toneForSource, toneForStatus } from "./data-status";

export function MarketOverviewPanel() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["market-overview"],
    queryFn: api.marketOverview
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
              <StatusChip tone={toneForBreadthMode(data.breadth_mode)}>{data.breadth_mode}</StatusChip>
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
