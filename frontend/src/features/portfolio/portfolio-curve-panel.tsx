"use client";

import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { LineChartCard } from "@/components/ui/line-chart-card";
import { api } from "@/lib/api/client";

export function PortfolioCurvePanel() {
  const defaultStartDate = useMemo(() => `${new Date().getFullYear()}-01-01`, []);
  const [startDate, setStartDate] = useState(defaultStartDate);
  const query = useQuery({
    queryKey: ["portfolio-curve", startDate],
    queryFn: () => api.portfolioCurve({ startDate }),
    staleTime: 60_000
  });
  const curve = query.data;
  return (
    <div className="space-y-3">
      <div className="flex flex-col gap-3 rounded border border-[#2d333d] bg-[#171a20] p-4 md:flex-row md:items-end md:justify-between">
        <div>
          <h2 className="text-base font-semibold">Depotkurve</h2>
          <p className="mt-1 text-sm leading-5 text-[#a0a7b4]">
            Depot und S&P 500 werden ab dem Basistag gemeinsam auf 100 gesetzt. Standard ist der 01.01. des laufenden Jahres.
          </p>
        </div>
        <label className="w-full text-sm md:w-56">
          <span className="mb-1 block text-[#a0a7b4]">Startdatum</span>
          <input
            className="input-dark"
            type="date"
            value={startDate}
            onChange={(event) => setStartDate(event.target.value || defaultStartDate)}
          />
        </label>
      </div>
      <LineChartCard
        caption={
          curve?.points.length
            ? `Basis ${curve.base_date ?? startDate} · Stand ${curve.as_of}`
            : (curve?.message || "Depotindex aus offenen Positionen und gespeicherten Kursdaten.")
        }
        dateTickMode="weekly"
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
        title="Depotkurve"
      />
    </div>
  );
}
