import { StatusChip } from "@/components/ui/status-chip";
import { BuyStrengthPanel } from "@/features/portfolio/buy-strength-panel";

export default function PortfolioBuyStrengthOverviewPage() {
  return (
    <div className="space-y-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Stärke nach Kauf</h1>
          <p className="mt-1 max-w-3xl text-sm leading-6 text-[#a0a7b4]">
            Frische Käufe unter drei Wochen aus manueller Erfassung, CSV-Import oder Trade-Republic-Import.
          </p>
        </div>
        <StatusChip tone="neutral">Portfolio-Check</StatusChip>
      </div>
      <BuyStrengthPanel />
    </div>
  );
}
