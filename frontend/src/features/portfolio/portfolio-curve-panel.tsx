"use client";

import { ProductDetails } from "@/components/ui/product-details";
import { useProductUi } from "@/components/ui/ui-mode-provider";
import { curveGaps } from "./curve-gaps";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { LineChartCard } from "@/components/ui/line-chart-card";
import { api } from "@/lib/api/client";
import { nextPortfolioYearCheck, portfolioYearStart } from "./portfolio-year";
import Link from "next/link";

export function PortfolioCurvePanel() {
  const product = useProductUi();
  const [defaultStartDate, setDefaultStartDate] = useState("");
  const [selectedStartDate, setSelectedStartDate] = useState<string | null>(null);
  const startDate = selectedStartDate ?? defaultStartDate;
  useEffect(() => {
    let timer: ReturnType<typeof setTimeout>;
    const update = () => {
      clearTimeout(timer);
      setDefaultStartDate(portfolioYearStart());
      timer = setTimeout(update, nextPortfolioYearCheck());
    };
    update();
    window.addEventListener("focus", update);
    document.addEventListener("visibilitychange", update);
    return () => {
      clearTimeout(timer);
      window.removeEventListener("focus", update);
      document.removeEventListener("visibilitychange", update);
    };
  }, []);
  const [model, setModel] = useState<"auto" | "execution_history" | "current_holdings">("auto");
  const [averages,setAverages]=useState(false);
  const query = useQuery({
    queryKey: ["portfolio-curve", startDate, model],
    queryFn: () => api.portfolioCurve({ startDate, model }),
    enabled: Boolean(startDate),
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
        <ProductDetails title="Darstellung & Zeitraum ändern"><Link href="/portfolio/performance" className="app-button mb-3">Performance & Benchmark vergleichen</Link><label className="mb-3 flex items-center gap-2 text-sm"><input type="checkbox" checked={averages} onChange={event=>setAverages(event.target.checked)}/>SMA 10 und SMA 21 anzeigen</label><div className="flex flex-col gap-3 md:flex-row">
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
            onChange={(event) => setSelectedStartDate(event.target.value || null)}
          />
        </label>
        </div></ProductDetails>
      </div>
      {product && curve && <details className="dashboard-section"><summary className="cursor-pointer text-sm font-semibold">{curve.complete_points ?? "–"} von {curve.total_points ?? curve.points.length} Tagen bewertet · Lücken & Berechnungsgrundlage</summary><div className="mt-3 space-y-2 text-sm"><p>{curve.message}</p><p>{curve.model === "current_holdings" ? "Simulation des heutigen Bestands, keine historische Depotperformance." : "Basis: importierte TR-Ausführungen und historische Tageskurse. Cashbewegungen am Tagesende."}</p>{curveGaps(curve.points).map(gap => <p key={gap.from}>Fehlende Depotbewertung: {gap.from} bis {gap.to} · {gap.count} {gap.count === 1 ? "Tag" : "Tage"}{gap.instruments.length > 0 && <> · Betroffene Instrumente: {gap.instruments.join(", ")}</>}</p>)}<p>Lücken bleiben sichtbar. Es werden keine zukünftigen Kurse oder erfundenen Bewertungen ergänzt.</p></div></details>}
      {!product && curve && <p className="app-notice">{curve.model === "current_holdings" ? "Keine historische Depotperformance. " : "Cashbewegungen werden am Tagesende berücksichtigt. "}{curve.message} · Bewertbare Tage {curve.complete_points ?? "–"}/{curve.total_points ?? curve.points.length}. Lücken werden nicht durch zukünftige Kurse ersetzt.</p>}
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
        points={(curve?.points ?? []).map(point => ({ date: point.date, portfolio_index: point.portfolio_index, portfolio_index_sma10: point.portfolio_index_sma10, portfolio_index_sma21: point.portfolio_index_sma21, sp500_index: point.sp500_index }))}
        series={[
          {
            key: "portfolio_index",
            label: "Depotindex",
            color: "#34d399",
            formatter: (value: number) => product ? value.toLocaleString("de-DE", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : value.toFixed(2)
          },
          {
            key: "portfolio_index_sma10",
            label: "SMA 10",
            color: "#60a5fa",
            formatter: (value: number) => product ? value.toLocaleString("de-DE", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : value.toFixed(2)
          },
          {
            key: "portfolio_index_sma21",
            label: "SMA 21",
            color: "#fbbf24",
            formatter: (value: number) => product ? value.toLocaleString("de-DE", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : value.toFixed(2)
          },
          {
            key: "sp500_index",
            label: "S&P 500",
            color: "#f472b6",
            formatter: (value: number) => product ? value.toLocaleString("de-DE", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : value.toFixed(2)
          }
        ].filter(item=>averages||!item.key.startsWith("portfolio_index_sma"))}
        title="Depotkurve"
      />
    </div>
  );
}
