import { ChartPlaceholder } from "@/components/ui/chart-placeholder";
import { MarketOverviewPanel } from "@/features/market/market-overview-panel";

export default function MarketPage() {
  return (
    <div className="space-y-5">
      <MarketOverviewPanel />
      <div className="grid gap-4 xl:grid-cols-2">
        <ChartPlaceholder title="Breadth" caption="A/D-Linie, McClellan und SMA-Breitenwerte" />
        <ChartPlaceholder title="Volatility" caption="VIX/VIXY-Regime als späterer Lightweight-Chart" />
      </div>
    </div>
  );
}

