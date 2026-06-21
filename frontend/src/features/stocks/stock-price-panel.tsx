"use client";

import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { LineChartCard } from "@/components/ui/line-chart-card";
import type { ChartLevel, ChartMarker } from "@/components/ui/line-chart-card";
import { api } from "@/lib/api/client";
import type { PriceBarPoint, PriceRange } from "@/lib/types/api";

export function StockPricePanel({
  ticker,
  range = "1y",
  title = "Kursverlauf",
  levels = [],
  markers = []
}: {
  ticker: string;
  range?: PriceRange;
  title?: string;
  levels?: ChartLevel[];
  markers?: ChartMarker[];
}) {
  const clean = ticker.toUpperCase();
  const query = useQuery({
    queryKey: ["stock-prices", clean, range],
    queryFn: () => api.stockPrices(clean, range),
    staleTime: 60_000
  });
  const benchmarkQuery = useQuery({
    queryKey: ["stock-prices", "SPY", range],
    queryFn: () => api.stockPrices("SPY", range),
    staleTime: 60_000,
    enabled: clean !== "SPY"
  });
  const rsQuery = useQuery({
    queryKey: ["stock-rs", clean],
    queryFn: () => api.stockRs(clean),
    staleTime: 60_000,
    enabled: clean !== "SPY"
  });
  const history = query.data;
  const rsHistory = useMemo(() => rsQuery.data?.item?.rs_history ?? [], [rsQuery.data?.item?.rs_history]);
  const chartPoints = useMemo(
    () => buildTechnicalOverlayPoints(history?.points ?? [], benchmarkQuery.data?.points ?? [], rsHistory),
    [benchmarkQuery.data?.points, history?.points, rsHistory]
  );
  const autoMarkers = useMemo(() => buildAutoMarkers(chartPoints), [chartPoints]);
  const statusTone = history?.source === "database" ? "good" : "warning";
  const statusLabel = history?.source === "database" ? "Price Cache" : "Fallback";
  const hasBenchmark = clean !== "SPY" && Boolean(benchmarkQuery.data?.points.length);
  const hasRsHistory = clean !== "SPY" && rsHistory.length > 0;

  return (
    <LineChartCard
      caption={
        history
          ? `${history.points.length} Tagesbars, Stand ${history.as_of}, ${formatPct(history.change_pct)} im Zeitraum${
              hasRsHistory ? ", RS-Linie aktiv" : hasBenchmark ? ", RS vs SPY aktiv" : ""
            }`
          : "Historische OHLC-Daten aus dem Backend"
      }
      error={query.error}
      isLoading={query.isLoading}
      points={chartPoints}
      chartMode="candlestick"
      series={[
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
      levels={levels}
      markers={[...markers, ...autoMarkers]}
      subSeries={
        hasRsHistory
          ? [
              {
                key: "rs",
                label: "RS vs SPY",
                color: "#f472b6",
                formatter: (value) => value.toFixed(2)
              },
              {
                key: "rsEma21",
                label: "RS 21-EMA",
                color: "#38bdf8",
                formatter: (value) => value.toFixed(2)
              },
              {
                key: "rsEma50",
                label: "RS 50-EMA",
                color: "#fbbf24",
                formatter: (value) => value.toFixed(2)
              }
            ]
          : hasBenchmark
            ? [
                {
                  key: "rs",
                  label: "RS vs SPY",
                  color: "#f472b6",
                  formatter: (value) => value.toFixed(1)
                }
              ]
            : []
      }
      subTitle={
        hasRsHistory
          ? "Relative Stärke vs SPY mit eigenem 21-EMA und 50-EMA"
          : hasBenchmark
            ? "Relative Stärke vs SPY, Start = 100"
            : ""
      }
      volumeKey="volume"
      statusLabel={history ? statusLabel : "lädt"}
      statusTone={history ? statusTone : "neutral"}
      title={`${clean} ${title}`}
    />
  );
}

function buildTechnicalOverlayPoints(
  points: PriceBarPoint[],
  benchmarkPoints: PriceBarPoint[],
  rsHistory: Array<{ date: string; rs: number; rs_ema21?: number | null; rs_ema50?: number | null }>
) {
  const closes = points.map((point) => point.close);
  const ema21 = ema(closes, 21);
  const rsVsSpy = buildRelativeStrength(points, benchmarkPoints);
  const rsByDate = new Map(rsHistory.map((point) => [point.date, point]));
  return points.map((point, index) => {
    const rsPoint = rsByDate.get(point.date);
    return {
      ...point,
      ema21: ema21[index],
      sma50: sma(closes, index, 50),
      sma200: sma(closes, index, 200),
      rs: rsPoint?.rs ?? rsVsSpy[index],
      rsEma21: rsPoint?.rs_ema21 ?? null,
      rsEma50: rsPoint?.rs_ema50 ?? null
    };
  });
}

function buildRelativeStrength(points: PriceBarPoint[], benchmarkPoints: PriceBarPoint[]) {
  const benchmarkByDate = new Map(benchmarkPoints.map((point) => [point.date, point.close]));
  const ratios = points.map((point) => {
    const benchmarkClose = benchmarkByDate.get(point.date);
    if (!benchmarkClose || benchmarkClose <= 0) return null;
    return point.close / benchmarkClose;
  });
  const first = ratios.find((value): value is number => typeof value === "number" && Number.isFinite(value));
  if (!first) return ratios.map(() => null);
  return ratios.map((value) => (typeof value === "number" && Number.isFinite(value) ? (value / first) * 100 : null));
}

function buildAutoMarkers(
  points: Array<PriceBarPoint & { ema21?: number | null; sma50?: number | null; sma200?: number | null }>
): ChartMarker[] {
  if (points.length < 20) return [];
  const markers: ChartMarker[] = [];
  const recent = points.slice(-252);
  const highPoint = recent.reduce((best, point) => ((point.high ?? point.close) > (best.high ?? best.close) ? point : best), recent[0]);
  markers.push({
    key: "auto-52w-high",
    date: highPoint.date,
    label: "52W High",
    value: highPoint.high ?? highPoint.close,
    color: "#38bdf8"
  });

  const latest = points.at(-1);
  if (latest?.ema21 && latest.close < latest.ema21) {
    markers.push({
      key: "auto-ema21-lost",
      date: latest.date,
      label: "<21EMA",
      value: latest.close,
      color: "#fbbf24"
    });
  }
  if (latest?.sma50 && latest.close < latest.sma50) {
    markers.push({
      key: "auto-sma50-lost",
      date: latest.date,
      label: "<50SMA",
      value: latest.close,
      color: "#fb7185"
    });
  }

  const volumeWindow = points.slice(-90).filter((point) => typeof point.volume === "number");
  const volumePoint = volumeWindow.reduce((best, point) => ((point.volume ?? 0) > (best.volume ?? 0) ? point : best), volumeWindow[0]);
  if (volumePoint && volumePoint.volume && volumePoint.volume > 0) {
    markers.push({
      key: "auto-volume-spike",
      date: volumePoint.date,
      label: "Vol Spike",
      value: volumePoint.close,
      color: "#a78bfa"
    });
  }

  return markers;
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
