"use client";

import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { LineChartCard } from "@/components/ui/line-chart-card";
import { api } from "@/lib/api/client";
import type { PriceBarPoint, PriceRange } from "@/lib/types/api";

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
  const chartPoints = useMemo(() => buildTechnicalOverlayPoints(history?.points ?? []), [history?.points]);
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
      points={chartPoints}
      series={[
        {
          key: "close",
          label: "Close",
          color: "#34d399",
          formatter: (value) => `${value.toFixed(2)} ${history?.currency ?? "USD"}`
        },
        {
          key: "ema21",
          label: "21-EMA",
          color: "#38bdf8",
          formatter: (value) => `${value.toFixed(2)} ${history?.currency ?? "USD"}`
        },
        {
          key: "sma50",
          label: "50-SMA",
          color: "#fbbf24",
          formatter: (value) => `${value.toFixed(2)} ${history?.currency ?? "USD"}`
        },
        {
          key: "sma200",
          label: "200-SMA",
          color: "#c084fc",
          formatter: (value) => `${value.toFixed(2)} ${history?.currency ?? "USD"}`
        }
      ]}
      volumeKey="volume"
      statusLabel={history ? statusLabel : "lädt"}
      statusTone={history ? statusTone : "neutral"}
      title={`${clean} ${title}`}
    />
  );
}

function buildTechnicalOverlayPoints(points: PriceBarPoint[]) {
  const closes = points.map((point) => point.close);
  const ema21 = ema(closes, 21);
  return points.map((point, index) => ({
    ...point,
    ema21: ema21[index],
    sma50: sma(closes, index, 50),
    sma200: sma(closes, index, 200)
  }));
}

function sma(values: number[], index: number, period: number) {
  if (index + 1 < period) return null;
  const window = values.slice(index + 1 - period, index + 1);
  return window.reduce((sum, value) => sum + value, 0) / period;
}

function ema(values: number[], period: number) {
  const alpha = 2 / (period + 1);
  let previous: number | null = null;
  return values.map((value) => {
    previous = previous === null ? value : value * alpha + previous * (1 - alpha);
    return previous;
  });
}

function formatPct(value?: number | null) {
  if (typeof value !== "number") return "-";
  return `${value >= 0 ? "+" : ""}${value.toFixed(1)}%`;
}
