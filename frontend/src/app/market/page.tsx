import { BreadthChartPanel } from "@/features/market/breadth-chart-panel";
import { MarketOverviewPanel } from "@/features/market/market-overview-panel";
import { VolatilityPanel } from "@/features/market/volatility-panel";

export default function MarketPage() {
  return (
    <div className="space-y-5">
      <MarketOverviewPanel />
      <div className="grid gap-4 xl:grid-cols-2">
        <BreadthChartPanel />
        <VolatilityPanel />
      </div>
    </div>
  );
}
