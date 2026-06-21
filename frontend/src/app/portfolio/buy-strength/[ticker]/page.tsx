import { StatusChip } from "@/components/ui/status-chip";
import { BuyStrengthDetail } from "@/features/portfolio/buy-strength-detail";

export default async function PortfolioBuyStrengthPage({
  params
}: {
  params: Promise<{ ticker: string }>;
}) {
  const { ticker } = await params;

  return (
    <div className="space-y-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Stärke nach Kauf</h1>
          <p className="mt-1 text-sm text-[#a0a7b4]">
            Bewertung der ersten Handelstage nach Kaufdatum für {ticker.toUpperCase()}.
          </p>
        </div>
        <StatusChip tone="neutral">Portfolio</StatusChip>
      </div>
      <BuyStrengthDetail ticker={ticker.toUpperCase()} />
    </div>
  );
}
