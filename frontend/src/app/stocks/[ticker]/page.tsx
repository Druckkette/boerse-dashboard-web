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
    <div className="space-y-4">
      <div className="flex items-center justify-between rounded-[14px] border border-[#e3e8ef] bg-white px-4 py-3 shadow-[0_5px_18px_rgba(15,23,42,0.05)]">
        <div className="flex min-w-0 items-baseline gap-3">
          <h1 className="text-2xl font-semibold text-[#172033]">{clean}</h1>
          <span className="text-xs font-medium uppercase tracking-[0.1em] text-[#687386]">Aktienanalyse</span>
        </div>
        <div className="shrink-0">
          <StatusChip tone="neutral">Bewertung</StatusChip>
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
