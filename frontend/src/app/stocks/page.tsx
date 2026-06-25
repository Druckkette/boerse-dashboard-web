import { StatusChip } from "@/components/ui/status-chip";
import { RsRankingPanel } from "@/features/stocks/rs-ranking-panel";
import { StockAssessmentRankingPanel } from "@/features/stocks/stock-assessment-ranking-panel";
import { StockComparePanel } from "@/features/stocks/stock-compare-panel";
import { StockSearchPanel } from "@/features/stocks/stock-search-panel";

export default function StocksPage() {
  return (
    <div className="space-y-5">
      <div className="flex flex-col justify-between gap-4 rounded border border-[#2d333d] bg-[#171a20] p-5 md:flex-row md:items-center">
        <div>
          <h1 className="text-2xl font-semibold">Aktien</h1>
        </div>
        <StatusChip tone="neutral">RS API ready</StatusChip>
      </div>
      <StockSearchPanel />
      <StockComparePanel />
      <StockAssessmentRankingPanel />
      <RsRankingPanel />
    </div>
  );
}
