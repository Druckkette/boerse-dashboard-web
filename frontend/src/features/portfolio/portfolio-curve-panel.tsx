"use client";

import { useQuery } from "@tanstack/react-query";
import { LineChartCard } from "@/components/ui/line-chart-card";
import { api } from "@/lib/api/client";

export function PortfolioCurvePanel() {
  const query = useQuery({
    queryKey: ["portfolio-curve", 370],
    queryFn: () => api.portfolioCurve(370),
    staleTime: 60_000
  });
  const curve = query.data;
  return (
    <LineChartCard
      caption={
        curve?.points.length
          ? `${curve.points.length} Punkte, Stand ${curve.as_of}. ${curve.message}`
          : "Depotindex aus offenen Positionen und Price Cache."
      }
      error={query.error}
      isLoading={query.isLoading}
      points={curve?.points ?? []}
      series={[
        {
          key: "portfolio_index",
          label: "Depotindex",
          color: "#34d399",
          formatter: (value) => value.toFixed(2)
        },
        {
          key: "portfolio_index_sma10",
          label: "SMA 10",
          color: "#60a5fa",
          formatter: (value) => value.toFixed(2)
        },
        {
          key: "portfolio_index_sma21",
          label: "SMA 21",
          color: "#fbbf24",
          formatter: (value) => value.toFixed(2)
        },
        {
          key: "sp500_index",
          label: "S&P 500",
          color: "#f472b6",
          formatter: (value) => value.toFixed(2)
        }
      ]}
      statusLabel={
        curve?.source === "trade_republic_transactions"
          ? "TR-Transaktionen"
          : curve?.source === "database"
            ? "Price Cache"
            : "Cache fehlt"
      }
      statusTone={curve?.source === "missing" ? "warning" : "good"}
      title="Depotkurve"
    />
  );
}
