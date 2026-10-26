import { ChartAnalysisDetail } from "@/features/chart-analysis/chart-analysis";
import { notFound } from "next/navigation";

export default async function PatternChartPage({
  params,
  searchParams,
}: {
  params: Promise<{ ticker: string }>;
  searchParams: Promise<{ pattern?: string; rules?: string; refresh?: string }>;
}) {
  const { ticker } = await params;
  const query = await searchParams;
  if (!/^[A-Za-z0-9][A-Za-z0-9.=_^-]{0,31}$/.test(ticker)) notFound();
  return (
    <ChartAnalysisDetail
      key={`${ticker}:${query.pattern || ""}`}
      ticker={ticker.toUpperCase()}
      patternId={query.pattern}
      rules={query.rules}
      autoRefresh={query.refresh === "1"}
    />
  );
}
