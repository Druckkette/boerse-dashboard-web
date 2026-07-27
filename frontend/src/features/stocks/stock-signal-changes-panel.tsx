"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowRight, CheckCircle2, Sparkles } from "lucide-react";
import { StatusChip } from "@/components/ui/status-chip";
import { api } from "@/lib/api/client";

export function StockSignalChangesPanel({ ticker }: { ticker: string }) {
  const query = useQuery({
    queryKey: ["stock-signal-changes", ticker],
    queryFn: () => api.stockSignalChanges(ticker),
    staleTime: 60_000
  });
  if (query.isLoading) return <div className="h-24 animate-pulse rounded-[12px] bg-[#eef2f6]" />;
  if (!query.data) return null;
  const changes = query.data.changes.filter((item) => item.kind !== "unchanged");
  return (
    <section className="rounded-[14px] border border-[#e3e8ef] bg-white p-4 shadow-[0_5px_18px_rgba(15,23,42,0.05)]">
      <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
        <div><h2 className="flex items-center gap-2 text-sm font-semibold text-[#172033]"><Sparkles size={16} className="text-[#0f766e]" /> Seit dem vorherigen Handelstag</h2><p className="mt-1 text-xs text-[#687386]">{query.data.previous_as_of || "–"} <ArrowRight className="mx-1 inline size-3" /> {query.data.current_as_of || "–"}</p></div>
        <StatusChip tone={changes.some((item) => item.kind === "new") ? "warning" : "good"}>{changes.length ? `${changes.length} Änderungen` : "Unverändert"}</StatusChip>
      </div>
      {changes.length ? <div className="grid gap-2 md:grid-cols-2">{changes.map((item, index) => <div key={`${item.label}-${index}`} className="flex gap-2 rounded-[9px] bg-[#f7f9fb] px-3 py-2"><CheckCircle2 className={`mt-0.5 size-4 shrink-0 ${item.kind === "resolved" ? "text-[#138a57]" : "text-[#b7791f]"}`} /><div><div className="text-sm font-medium text-[#172033]">{item.kind === "resolved" ? "Entschärft" : "Neu"}: {item.label}</div><div className="mt-0.5 text-xs leading-5 text-[#687386]">{item.detail}</div></div></div>)}</div> : <div className="rounded-[9px] bg-[#f3faf8] px-3 py-2 text-sm text-[#31766c]">Keine Regel oder kein Chartsignal hat seinen Zustand geändert.</div>}
    </section>
  );
}
