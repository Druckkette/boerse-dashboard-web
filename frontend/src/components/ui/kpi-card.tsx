import { StatusChip } from "@/components/ui/status-chip";
import type { KpiCard as KpiCardType } from "@/lib/types/api";

export function KpiCard({ item }: { item: KpiCardType }) {
  return (
    <div className="rounded-[24px] border border-[#e3e8ef] bg-white p-5 shadow-[0_10px_28px_rgba(15,23,42,0.06)]">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div className="text-sm font-medium text-[#687386]">{item.label}</div>
        <StatusChip tone={item.tone}>{item.tone}</StatusChip>
      </div>
      <div className="text-3xl font-semibold tracking-normal text-[#172033]">{item.value}</div>
      <div className="mt-2 text-sm leading-6 text-[#687386]">{item.detail}</div>
    </div>
  );
}
