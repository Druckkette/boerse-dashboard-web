import { BreadthChartPanel } from "@/features/market/breadth-chart-panel";
import { DeepAnalysisPanel } from "@/features/market/deep-analysis-panel";
import { MarketAmpelPanel } from "@/features/market/market-ampel-panel";
import { MarketDiagnosticsPanel } from "@/features/market/market-diagnostics-panel";
import { MarketOverviewPanel } from "@/features/market/market-overview-panel";
import { VolatilityPanel } from "@/features/market/volatility-panel";
import type { ReactNode } from "react";

export default function MarketPage() {
  return (
    <div className="space-y-5">
      <MarketAmpelPanel />
      <MarketOverviewPanel />
      <MarketArea
        title="Trendcheck, Ordnung und Sektorrotation"
        description="Entspricht dem Streamlit-Bereich mit Trendprüfung, MA-Ordnung, Sektorrotation und Intermarket-Bild."
      >
        <MarketDiagnosticsPanel />
      </MarketArea>
      <MarketArea
        title="Marktbreite und Volatilität"
        description="Equal-Weight-Breadth, Breadth-Snapshot und VIX/VIXY-Regime aus dem vorberechneten Cache."
      >
        <div className="grid gap-4 xl:grid-cols-2">
          <BreadthChartPanel />
          <VolatilityPanel />
        </div>
      </MarketArea>
      <MarketArea
        title="Tiefenanalyse"
        description="McClellan, NH/NL, Deemer Ratio und Divergenzprüfungen aus dem gespeicherten Aktienuniversum."
      >
        <DeepAnalysisPanel />
      </MarketArea>
    </div>
  );
}

function MarketArea({
  children,
  description,
  title
}: {
  children: ReactNode;
  description: string;
  title: string;
}) {
  return (
    <section className="space-y-3">
      <div>
        <h2 className="text-lg font-semibold tracking-normal">{title}</h2>
        <p className="mt-1 max-w-4xl text-sm leading-6 text-[#a0a7b4]">{description}</p>
      </div>
      {children}
    </section>
  );
}
