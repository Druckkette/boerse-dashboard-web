"use client";
import { useProductUi } from "./ui-mode-provider";
import { localizeKpiValue, localizeKpiDetail } from "@/lib/kpi-format";
import { StatusChip } from "@/components/ui/status-chip";
import type { KpiCard as KpiCardType } from "@/lib/types/api";

export function KpiCard({ item }: { item: KpiCardType }) {
  const product = useProductUi();
  const neutral = product && item.label === "Positionen";
  const performance = product && ["Unrealisiert", "Gewinn/Verlust zum Vortagsschluss"].includes(item.label);
  return (
    <div className={`${product && item.label === "Depotwert" ? "col-span-2 md:col-span-1" : ""} relative min-h-[108px] overflow-hidden rounded-[14px] border border-[#e3e8ef] bg-white px-3.5 py-3 shadow-[0_5px_18px_rgba(15,23,42,0.05)]`}>
      <span className={`absolute inset-y-3 left-0 w-0.5 rounded-r-full ${accentClass(neutral ? "neutral" : item.tone)}`} />
      <div className="flex items-start justify-between gap-2">
        <div className="text-xs font-semibold uppercase tracking-[0.08em] text-[#687386]">{item.label}</div>
        <StatusChip tone={neutral ? "neutral" : item.tone}>{neutral ? "Bestand" : performance ? (item.value === "n/a" ? "Daten prüfen" : item.tone === "bad" ? "Minus" : item.tone === "good" ? "Plus" : "Ergebnis") : toneLabel(item.tone)}</StatusChip>
      </div>
      <div className={`${product ? "break-words text-[clamp(1.05rem,3.8vw,1.5rem)] leading-tight" : "text-2xl leading-none"} mt-2 font-semibold tabular-nums text-[#172033]`}>{product ? localizeKpiValue(item.value) : item.value}</div>
      <div className="mt-2 text-xs leading-5 text-[#687386]">{product ? localizeKpiDetail(item.detail) : item.detail}</div>
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
