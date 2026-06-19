import { MarketAmpelPanel } from "@/features/market/market-ampel-panel";
import { MarketBreadthOverviewPanel } from "@/features/market/market-breadth-overview-panel";
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
        title="Marktbreite"
        description="Russell-vs-S&P, Equal-Weight-ETFs, A/D, Volumen, McClellan, NH/NL, MA-Teilnahme und Deemer Ratio."
      >
        <MarketBreadthOverviewPanel />
      </MarketArea>
      <MarketArea
        title="Volatilität"
        description="VIX/VXX-Regime aus dem vorberechneten Price Cache."
      >
        <VolatilityPanel />
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
