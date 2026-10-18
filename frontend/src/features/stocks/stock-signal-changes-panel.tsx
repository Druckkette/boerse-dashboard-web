"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowRight, CircleMinus, Sparkles, TrendingDown, TrendingUp } from "lucide-react";
import { StatusChip } from "@/components/ui/status-chip";
import { api } from "@/lib/api/client";
import { signalChangePresentation } from "./signal-change-presentation";

const effectStyles = {
  good: { icon: TrendingUp, color: "text-[#138a57]", background: "bg-[#f3faf8]" },
  bad: { icon: TrendingDown, color: "text-[#c2413b]", background: "bg-[#fff0ef]" },
  neutral: { icon: CircleMinus, color: "text-[#687386]", background: "bg-[#f7f9fb]" }
};

export function StockSignalChangesPanel({ ticker }: { ticker: string }) {
  const query = useQuery({
    queryKey: ["stock-signal-changes", ticker],
    queryFn: () => api.stockSignalChanges(ticker),
    staleTime: 60_000
  });
  if (query.isLoading) return <div className="h-24 animate-pulse rounded-[12px] bg-[#eef2f6]" />;
  if (!query.data) return null;
  const changes = query.data.changes.filter((item) => item.kind !== "unchanged");
  const tone = changes.some((item) => item.effect === "deterioration") ? "bad"
    : changes.some((item) => item.effect === "improvement") ? "good" : "neutral";
  return (
    <section className="rounded-[14px] border border-[#e3e8ef] bg-white p-4 shadow-[0_5px_18px_rgba(15,23,42,0.05)]">
      <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
        <div><h2 className="flex items-center gap-2 text-sm font-semibold text-[#172033]"><Sparkles size={16} className="text-[#0f766e]" /> Seit dem vorherigen Handelstag</h2><p className="mt-1 text-xs text-[#687386]">{query.data.previous_as_of || "–"} <ArrowRight className="mx-1 inline size-3" /> {query.data.current_as_of || "–"}</p></div>
        <StatusChip tone={tone}>{changes.length ? `${changes.length} Änderungen` : "Unverändert"}</StatusChip>
      </div>
      {changes.length ? <div className="grid gap-2 md:grid-cols-2">{changes.map((item, index) => {
        const presentation = signalChangePresentation(item);
        const style = effectStyles[presentation.tone];
        const Icon = style.icon;
        return <div key={`${item.label}-${index}`} data-effect={item.effect} className={`flex min-w-0 gap-2 rounded-[9px] px-3 py-2 ${style.background}`}>
          <Icon aria-hidden="true" className={`mt-0.5 size-4 shrink-0 ${style.color}`} />
          <div className="min-w-0 break-words"><div className={`text-sm font-medium ${style.color}`}>{presentation.title}: {item.label}</div>
            <div className="mt-0.5 text-xs leading-5 text-[#687386]">{item.detail}</div></div>
        </div>;
      })}</div> : <div className="rounded-[9px] bg-[#f7f9fb] px-3 py-2 text-sm text-[#687386]">Keine Regel oder kein Chartsignal hat seinen Zustand geändert.</div>}
    </section>
  );
}
