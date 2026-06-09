import { StatusChip } from "@/components/ui/status-chip";
import { StockPricePanel } from "@/features/stocks/stock-price-panel";
import { StockRsPanel } from "@/features/stocks/stock-rs-panel";

export default async function StockDetailPage({ params }: { params: Promise<{ ticker: string }> }) {
  const { ticker } = await params;
  const clean = ticker.toUpperCase();
  return (
    <div className="space-y-5">
      <div className="rounded border border-[#2d333d] bg-[#171a20] p-5">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-sm text-[#a0a7b4]">Stock Detail</div>
            <h1 className="text-3xl font-semibold">{clean}</h1>
          </div>
          <StatusChip tone="neutral">API contract ready</StatusChip>
        </div>
      </div>
      <div className="grid gap-4 xl:grid-cols-2">
        <StockPricePanel ticker={clean} title="Price" />
        <StockPricePanel ticker="SPY" title="Benchmark" />
      </div>
      <StockRsPanel ticker={clean} />
    </div>
  );
}
