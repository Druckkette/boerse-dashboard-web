import { BreadthChartPanel } from "@/features/market/breadth-chart-panel";
import { MarketAmpelPanel } from "@/features/market/market-ampel-panel";
import { MarketDiagnosticsPanel } from "@/features/market/market-diagnostics-panel";
import { MarketOverviewPanel } from "@/features/market/market-overview-panel";
import { VolatilityPanel } from "@/features/market/volatility-panel";

export default function MarketPage() {
  return (
    <div className="space-y-5">
      <MarketAmpelPanel />
      <MarketOverviewPanel />
      <MarketDiagnosticsPanel />
      <div className="grid gap-4 xl:grid-cols-2">
        <BreadthChartPanel />
        <VolatilityPanel />
      </div>
    </div>
  );
}
