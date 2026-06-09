"use client";

import { useQuery } from "@tanstack/react-query";
import { LineChartCard } from "@/components/ui/line-chart-card";
import { api } from "@/lib/api/client";

export function BreadthChartPanel() {
  const query = useQuery({
    queryKey: ["market-breadth"],
    queryFn: api.marketBreadth,
    staleTime: 60_000
  });
  const breadth = query.data;

  return (
    <LineChartCard
      caption={
        breadth
          ? `${breadth.universe}, Coverage ${(breadth.coverage_ratio * 100).toFixed(0)}%, Stand ${breadth.as_of}`
          : "A/D- und SMA-Breitenwerte aus dem Market-Backend"
      }
      error={query.error}
      isLoading={query.isLoading}
      points={breadth?.points ?? []}
      series={[
        {
          key: "pct_above_50sma",
          label: "> 50-SMA",
          color: "#22d3ee",
          formatter: (value) => `${value.toFixed(1)}%`
        },
        {
          key: "pct_above_200sma",
          label: "> 200-SMA",
          color: "#a78bfa",
          formatter: (value) => `${value.toFixed(1)}%`
        }
      ]}
      statusLabel={breadth ? "Breadth API" : "lädt"}
      title="Market Breadth"
    />
  );
}
