import { RsRankingPanel } from "@/features/stocks/rs-ranking-panel";
import { StockAssessmentRankingPanel } from "@/features/stocks/stock-assessment-ranking-panel";
import { StockComparePanel } from "@/features/stocks/stock-compare-panel";
import { StockSearchPanel } from "@/features/stocks/stock-search-panel";
import { TopDailyStocksPanel } from "@/features/stocks/top-daily-stocks-panel";

export default function StocksPage() {
  return (
    <div className="space-y-4">
      <StockSearchPanel />
      <TopDailyStocksPanel />
      <StockComparePanel />
      <StockAssessmentRankingPanel />
      <RsRankingPanel />
    </div>
  );
}
