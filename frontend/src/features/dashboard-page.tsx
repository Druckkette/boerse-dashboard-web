"use client";

import { useQuery } from "@tanstack/react-query";
import { ChartPlaceholder } from "@/components/ui/chart-placeholder";
import { KpiCard } from "@/components/ui/kpi-card";
import { StatusChip } from "@/components/ui/status-chip";
import { MarketOverviewPanel } from "@/features/market/market-overview-panel";
import { PositionTable } from "@/features/portfolio/position-table";
import { api } from "@/lib/api/client";

export function DashboardPage() {
  const portfolio = useQuery({ queryKey: ["portfolio-snapshot"], queryFn: api.portfolioSnapshot });
  const freshness = useQuery({ queryKey: ["freshness"], queryFn: api.freshness });

  return (
    <div className="space-y-6">
      <MarketOverviewPanel />

      <section className="grid gap-4 xl:grid-cols-[1.5fr_1fr]">
        <div className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {portfolio.data?.kpis.map((item) => <KpiCard key={item.label} item={item} />)}
          </div>
          {portfolio.data ? (
            <PositionTable positions={portfolio.data.positions} />
          ) : (
            <div className="rounded border border-[#2d333d] p-4">Portfolio lädt...</div>
          )}
        </div>

        <div className="space-y-4">
          <ChartPlaceholder title="Portfolio Index" caption="Platzhalter bis Lightweight Charts angebunden wird" />
          <div className="rounded border border-[#2d333d] bg-[#171a20] p-4">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-base font-semibold">Job Freshness</h2>
              <StatusChip tone="neutral">Live API</StatusChip>
            </div>
            <div className="space-y-3">
              {freshness.data?.services.map((service) => (
                <div key={service.name} className="flex items-center justify-between gap-4 border-b border-[#242a33] pb-3 last:border-0 last:pb-0">
                  <div>
                    <div className="text-sm font-medium">{service.name}</div>
                    <div className="text-xs text-[#a0a7b4]">Stand {service.as_of}</div>
                  </div>
                  <StatusChip tone={service.status === "fresh" ? "good" : "warning"}>
                    {service.status}
                  </StatusChip>
                </div>
              )) ?? <div className="text-sm text-[#a0a7b4]">Freshness lädt...</div>}
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}

