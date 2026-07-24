import { RsRankingPanel } from "@/features/stocks/rs-ranking-panel";
import { StockAssessmentRankingPanel } from "@/features/stocks/stock-assessment-ranking-panel";
import { StockComparePanel } from "@/features/stocks/stock-compare-panel";
import { StockSearchPanel } from "@/features/stocks/stock-search-panel";

export default function StocksPage() {
  return (
    <div className="space-y-4">
      <StockSearchPanel />
      <StockComparePanel />
      <StockAssessmentRankingPanel />
      <RsRankingPanel />
    </div>
  );
}
