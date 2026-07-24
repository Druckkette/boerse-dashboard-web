import { BuyStrengthPanel } from "@/features/portfolio/buy-strength-panel";
import { normalizeBuyStrengthWeeks } from "@/features/portfolio/buy-strength-window";

export default async function PortfolioBuyStrengthOverviewPage({
  searchParams
}: {
  searchParams?: Promise<{ weeks?: string | string[] }>;
}) {
  const resolvedSearchParams = searchParams ? await searchParams : {};
  const initialWeeks = normalizeBuyStrengthWeeks(resolvedSearchParams.weeks);

  return <BuyStrengthPanel initialWeeks={initialWeeks} />;
}
