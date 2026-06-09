"use client";

import { useQuery } from "@tanstack/react-query";
import { LineChartCard } from "@/components/ui/line-chart-card";
import { StatusChip } from "@/components/ui/status-chip";
import { api } from "@/lib/api/client";

export function VolatilityPanel() {
  const query = useQuery({
    queryKey: ["market-volatility"],
    queryFn: api.marketVolatility,
    staleTime: 60_000
  });
  const volatility = query.data;
  const chartPoints =
    volatility?.points.map((point) => ({
      date: point.date,
      vix_close: point.vix_close,
      vixy_close: point.vixy_close
    })) ?? [];

  return (
    <div className="space-y-4">
      <LineChartCard
        caption={
          volatility
            ? `${volatility.regime}, Stand ${volatility.as_of}`
            : "VIX/VIXY-Regime aus gecachten Price-Bars"
        }
        error={query.error}
        isLoading={query.isLoading}
        points={chartPoints}
        series={[
          {
            key: "vix_close",
            label: "VIX",
            color: "#fb7185",
            formatter: (value) => value.toFixed(1)
          },
          {
            key: "vixy_close",
            label: "VIXY",
            color: "#fbbf24",
            formatter: (value) => value.toFixed(1)
          }
        ]}
        statusLabel={volatility?.source === "database" ? "Volatility API" : "Cache fehlt"}
        statusTone={volatility?.source === "database" ? "good" : "warning"}
        title="Volatility"
      />

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        {(volatility?.status_cards ?? []).map((item) => (
          <div key={item.title} className="rounded border border-[#2d333d] bg-[#171a20] p-4">
            <div className="mb-3 flex items-center justify-between gap-3">
              <div className="text-xs uppercase text-[#a0a7b4]">{item.title}</div>
              <StatusChip tone={item.tone}>{item.status}</StatusChip>
            </div>
            <div className="text-sm leading-5 text-[#d8dde6]">{item.detail}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
