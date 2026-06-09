"use client";

import { useQuery } from "@tanstack/react-query";
import { LineChartCard } from "@/components/ui/line-chart-card";
import { api } from "@/lib/api/client";
import type { PriceRange } from "@/lib/types/api";

export function StockPricePanel({
  ticker,
  range = "1y",
  title = "Kursverlauf"
}: {
  ticker: string;
  range?: PriceRange;
  title?: string;
}) {
  const clean = ticker.toUpperCase();
  const query = useQuery({
    queryKey: ["stock-prices", clean, range],
    queryFn: () => api.stockPrices(clean, range),
    staleTime: 60_000
  });
  const history = query.data;
  const statusTone = history?.source === "database" ? "good" : "warning";
  const statusLabel = history?.source === "database" ? "Price Cache" : "Fallback";

  return (
    <LineChartCard
      caption={
        history
          ? `${history.points.length} Tagesbars, Stand ${history.as_of}, ${formatPct(history.change_pct)} im Zeitraum`
          : "Historische OHLC-Daten aus dem Backend"
      }
      error={query.error}
      isLoading={query.isLoading}
      points={history?.points ?? []}
      series={[
        {
          key: "close",
          label: "Close",
          color: "#34d399",
          formatter: (value) => `${value.toFixed(2)} ${history?.currency ?? "USD"}`
        }
      ]}
      statusLabel={history ? statusLabel : "lädt"}
      statusTone={history ? statusTone : "neutral"}
      title={`${clean} ${title}`}
    />
  );
}

function formatPct(value?: number | null) {
  if (typeof value !== "number") return "-";
  return `${value >= 0 ? "+" : ""}${value.toFixed(1)}%`;
}
