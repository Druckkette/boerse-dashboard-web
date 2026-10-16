"use client";

import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { LineChartCard } from "@/components/ui/line-chart-card";
import { api } from "@/lib/api/client";

export function PortfolioCurvePanel() {
  const defaultStartDate = useMemo(() => `${new Date().getFullYear()}-01-01`, []);
  const [startDate, setStartDate] = useState(defaultStartDate);
  const [model, setModel] = useState<"auto" | "execution_history" | "current_holdings">("auto");
  const query = useQuery({
    queryKey: ["portfolio-curve", startDate, model],
    queryFn: () => api.portfolioCurve({ startDate, model }),
    staleTime: 60_000
  });
  const curve = query.data;
  return (
    <div className="space-y-2.5">
      <div className="flex flex-col gap-2.5 rounded-[14px] border border-[#e3e8ef] bg-white px-4 py-3 shadow-[0_5px_18px_rgba(15,23,42,0.05)] md:flex-row md:items-center md:justify-between">
        <div>
          <h2 className="text-base font-semibold">{curve?.model === "execution_history" ? "Depotkurve aus Ausführungen" : curve?.model === "current_holdings" ? "Simulation des heutigen Bestands" : "Depotkurve"}</h2>
          <p className="mt-0.5 text-xs leading-5 text-[#687386]">
            Depot und S&P 500 werden ab dem Basistag gemeinsam auf 100 gesetzt. Standard ist der 01.01. des laufenden Jahres.
          </p>
        </div>
        <label className="w-full text-sm md:w-64">
          <span className="mb-1 block text-[10px] font-semibold uppercase tracking-[0.08em] text-[#687386]">Darstellung</span>
          <select className="input-dark" value={model} onChange={event => setModel(event.target.value as typeof model)}>
            <option value="auto">Automatisch nach Datenlage</option>
            <option value="execution_history">TR-Ausführungshistorie</option>
            <option value="current_holdings">Heutiger Bestand als Simulation</option>
          </select>
        </label>
        <label className="w-full text-sm md:w-56">
          <span className="mb-1 block text-[10px] font-semibold uppercase tracking-[0.08em] text-[#687386]">Startdatum</span>
          <input
            className="input-dark"
            type="date"
            value={startDate}
            onChange={(event) => setStartDate(event.target.value || defaultStartDate)}
          />
        </label>
      </div>
      {curve && <p className="app-notice">{curve.model === "current_holdings" ? "Keine historische Depotperformance. " : "Cashbewegungen werden am Tagesende berücksichtigt. "}{curve.message} · Bewertbare Tage {curve.complete_points ?? "–"}/{curve.total_points ?? curve.points.length}. Lücken werden nicht durch zukünftige Kurse ersetzt.</p>}
      {curve && !curve.points.some(point => point.portfolio_index != null) && <p role="status" className="app-notice">Für diese Auswahl fehlen vollständige Depotbewertungen. Die TR-Buchungen bleiben dokumentiert. Für die Depotkurve werden die historischen Tageskurse der damals gehaltenen Instrumente benötigt.</p>}
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
