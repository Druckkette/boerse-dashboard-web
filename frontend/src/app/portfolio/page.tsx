"use client";

import { useQuery } from "@tanstack/react-query";
import { KpiCard } from "@/components/ui/kpi-card";
import { PortfolioCurvePanel } from "@/features/portfolio/portfolio-curve-panel";
import { PortfolioManagementPanel } from "@/features/portfolio/portfolio-management-panel";
import { PositionTable } from "@/features/portfolio/position-table";
import { api } from "@/lib/api/client";

export default function PortfolioPage() {
  const { data } = useQuery({ queryKey: ["portfolio-snapshot"], queryFn: api.portfolioSnapshot });
  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-semibold">Portfolio</h1>
        <p className="mt-1 text-sm text-[#a0a7b4]">Snapshot, Risiko und klickbare Positionen.</p>
      </div>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {data?.kpis.map((item) => <KpiCard key={item.label} item={item} />)}
      </div>
      {data ? (
        <>
          <PortfolioCurvePanel />
          <PositionTable positions={data.positions} />
          <PortfolioManagementPanel positions={data.positions} />
        </>
      ) : (
        <div className="rounded border border-[#2d333d] p-4">Portfolio lädt...</div>
      )}
    </div>
  );
}
