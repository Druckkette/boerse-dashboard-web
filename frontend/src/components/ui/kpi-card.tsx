import { StatusChip } from "@/components/ui/status-chip";
import type { KpiCard as KpiCardType } from "@/lib/types/api";

export function KpiCard({ item }: { item: KpiCardType }) {
  return (
    <div className="rounded border border-[#2d333d] bg-[#171a20] p-4">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div className="text-sm text-[#a0a7b4]">{item.label}</div>
        <StatusChip tone={item.tone}>{item.tone}</StatusChip>
      </div>
      <div className="text-2xl font-semibold tracking-normal">{item.value}</div>
      <div className="mt-2 text-sm text-[#a0a7b4]">{item.detail}</div>
    </div>
  );
}

