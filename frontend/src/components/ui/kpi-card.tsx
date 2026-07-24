import { StatusChip } from "@/components/ui/status-chip";
import type { KpiCard as KpiCardType } from "@/lib/types/api";

export function KpiCard({ item }: { item: KpiCardType }) {
  return (
    <div className="relative min-h-[108px] overflow-hidden rounded-[14px] border border-[#e3e8ef] bg-white px-3.5 py-3 shadow-[0_5px_18px_rgba(15,23,42,0.05)]">
      <span className={`absolute inset-y-3 left-0 w-0.5 rounded-r-full ${accentClass(item.tone)}`} />
      <div className="flex items-start justify-between gap-2">
        <div className="text-xs font-semibold uppercase tracking-[0.08em] text-[#687386]">{item.label}</div>
        <StatusChip tone={item.tone}>{toneLabel(item.tone)}</StatusChip>
      </div>
      <div className="mt-2 text-2xl font-semibold leading-none tabular-nums text-[#172033]">{item.value}</div>
      <div className="mt-2 text-xs leading-5 text-[#687386]">{item.detail}</div>
    </div>
  );
}

function accentClass(tone: KpiCardType["tone"]) {
  if (tone === "good") return "bg-[#138a57]";
  if (tone === "warning") return "bg-[#b7791f]";
  if (tone === "bad") return "bg-[#c2413b]";
  return "bg-[#2563eb]";
}

function toneLabel(tone: KpiCardType["tone"]) {
  if (tone === "good") return "positiv";
  if (tone === "warning") return "wachsam";
  if (tone === "bad") return "Warnung";
  return "Info";
}
