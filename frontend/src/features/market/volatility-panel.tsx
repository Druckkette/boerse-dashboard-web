"use client";

import { useQuery } from "@tanstack/react-query";
import { LineChartCard } from "@/components/ui/line-chart-card";
import { StatusChip } from "@/components/ui/status-chip";
import { api } from "@/lib/api/client";
import type { Tone } from "@/lib/types/api";
import { labelForSource, toneForSource } from "./data-status";
import { MARKET_REFETCH_INTERVAL_MS } from "./query-timing";

export function VolatilityPanel() {
  const query = useQuery({
    queryKey: ["market-volatility"],
    queryFn: api.marketVolatility,
    staleTime: 60_000,
    refetchInterval: MARKET_REFETCH_INTERVAL_MS
  });
  const volatility = query.data;
  const chartPoints =
    volatility?.points.map((point) => ({
      date: point.date,
      vix_close: point.vix_close,
      vix_sma10: point.vix_sma10,
      vix_ema21: point.vix_ema21,
      vxx_close: point.vxx_close,
      vxx_ema21: point.vxx_ema21
    })) ?? [];

  return (
    <div className="space-y-4">
      <LineChartCard
        caption={
          volatility
            ? `${volatility.regime}, Stand ${volatility.as_of}`
            : "VIX/VXX-Regime aus gecachten Price-Bars"
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
            key: "vix_sma10",
            label: "VIX 10-SMA",
            color: "#7dd3fc",
            formatter: (value) => value.toFixed(1)
          },
          {
            key: "vix_ema21",
            label: "VIX 21-EMA",
            color: "#c084fc",
            formatter: (value) => value.toFixed(1)
          },
          {
            key: "vxx_close",
            label: "VXX",
            color: "#fbbf24",
            formatter: (value) => value.toFixed(1)
          },
          {
            key: "vxx_ema21",
            label: "VXX 21-EMA",
            color: "#22c55e",
            formatter: (value) => value.toFixed(1)
          }
        ]}
        statusLabel={volatility ? labelForSource(volatility.source) : "lädt"}
        statusTone={volatility ? toneForSource(volatility.source) : "neutral"}
        title="Volatility"
      />

      <div className="grid gap-3 md:grid-cols-2 2xl:grid-cols-4">
        {(volatility?.status_cards ?? []).map((item) => (
          <div key={item.title} className={["rounded border border-l-4 bg-[#171a20] p-4", cardClass(item.tone)].join(" ")}>
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

function cardClass(tone: Tone) {
  if (tone === "good") return "border-emerald-300/35 border-l-emerald-300 bg-emerald-300/10";
  if (tone === "bad") return "border-rose-300/35 border-l-rose-300 bg-rose-300/10";
  if (tone === "warning") return "border-amber-300/35 border-l-amber-300 bg-amber-300/10";
  return "border-[#2d333d] border-l-[#586071]";
}
