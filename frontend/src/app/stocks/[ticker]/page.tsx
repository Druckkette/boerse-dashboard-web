import { StatusChip } from "@/components/ui/status-chip";
import { Institutional13FPanel } from "@/features/stocks/institutional-13f-panel";
import { StockAssessmentPanel } from "@/features/stocks/stock-assessment-panel";
import { StockDetailActions } from "@/features/stocks/stock-detail-actions";
import { StockFundamentalsPanel } from "@/features/stocks/stock-fundamentals-panel";
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
          <StatusChip tone="neutral">Assessment API</StatusChip>
        </div>
      </div>
      <StockDetailActions ticker={clean} />
      <StockAssessmentPanel ticker={clean} />
      <StockFundamentalsPanel ticker={clean} />
      <Institutional13FPanel ticker={clean} />
      <StockPricePanel ticker={clean} title="Kurs" />
      <StockRsPanel ticker={clean} />
    </div>
  );
}
