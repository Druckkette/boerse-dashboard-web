import { BuyStrengthDetail } from "@/features/portfolio/buy-strength-detail";
import { normalizeBuyStrengthWeeks } from "@/features/portfolio/buy-strength-window";

export default async function PortfolioBuyStrengthPage({
  params,
  searchParams
}: {
  params: Promise<{ ticker: string }>;
  searchParams?: Promise<{ weeks?: string | string[] }>;
}) {
  const { ticker } = await params;
  const resolvedSearchParams = searchParams ? await searchParams : {};
  const initialWeeks = normalizeBuyStrengthWeeks(resolvedSearchParams.weeks);

  return <BuyStrengthDetail ticker={ticker.toUpperCase()} initialWeeks={initialWeeks} />;
}
