"use client";

import { Building2, TrendingDown, TrendingUp } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { StatusChip } from "@/components/ui/status-chip";
import { api } from "@/lib/api/client";
import type { Institutional13FTrendItem, Tone } from "@/lib/types/api";

export function Institutional13FPanel({ ticker }: { ticker: string }) {
  const clean = ticker.toUpperCase();
  const query = useQuery({
    queryKey: ["institutional-13f", clean],
    queryFn: () => api.stockInstitutional13F(clean),
    staleTime: 5 * 60_000
  });
  const item = query.data?.item;

  return (
    <section className="rounded border border-[#2d333d] bg-[#171a20] p-5">
      <div className="mb-4 flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <Building2 className="size-5 text-[#8ea4c8]" />
            <h2 className="text-lg font-semibold">Institutionelle 13F-Trends</h2>
          </div>
          <p className="mt-1 text-sm text-[#a0a7b4]">
            {item ? `${item.previous_period ?? "-"} bis ${item.report_period}` : "Noch keine gespeicherten 13F-Trends."}
          </p>
        </div>
        <StatusChip tone={item ? toneForTrend(item.trend) : "warning"}>{item?.trend ?? "missing"}</StatusChip>
      </div>

      {query.isLoading && <div className="text-sm text-[#a0a7b4]">Lädt...</div>}
      {query.isError && <div className="text-sm text-rose-200">13F-Trend konnte nicht geladen werden.</div>}
      {!query.isLoading && !query.isError && !item && (
        <div className="rounded border border-dashed border-[#4b5563] bg-[#111419] p-5 text-sm text-[#a0a7b4]">
          Starte den 13F/SEC-Job auf der Jobs-Seite. Der Worker lädt die offiziellen SEC-Datensätze
          und speichert danach aggregierte Ticker-Trends.
        </div>
      )}
      {item && (
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          <Metric label="Große Institutionen" value={number(item.large_holder_count)} detail={delta(item.large_holder_delta)} trend={item.large_holder_delta} />
          <Metric label="Alle 13F-Halter" value={number(item.holder_count)} detail={delta(item.holder_count_delta)} trend={item.holder_count_delta} />
          <Metric label="Marktwert" value={usd(item.total_value_usd)} detail={pct(item.total_value_delta_pct)} trend={item.total_value_delta_pct} />
          <Metric label="Aktien" value={compact(item.total_shares)} detail={pct(item.total_shares_delta_pct)} trend={item.total_shares_delta_pct} />
        </div>
      )}
    </section>
  );
}

function Metric({
  label,
  value,
  detail,
  trend
}: {
  label: string;
  value: string;
  detail: string;
  trend?: number | null;
}) {
  const positive = typeof trend === "number" && trend > 0;
  const negative = typeof trend === "number" && trend < 0;
  return (
    <div className="rounded border border-[#242a33] bg-[#111419] p-4">
      <div className="mb-2 flex items-center justify-between gap-2">
        <div className="text-xs uppercase text-[#a0a7b4]">{label}</div>
        {positive ? <TrendingUp className="size-4 text-emerald-300" /> : negative ? <TrendingDown className="size-4 text-rose-300" /> : null}
      </div>
      <div className="text-xl font-semibold tabular-nums">{value}</div>
      <div className={negative ? "mt-1 text-xs text-rose-200" : positive ? "mt-1 text-xs text-emerald-200" : "mt-1 text-xs text-[#7f8794]"}>
        {detail}
      </div>
    </div>
  );
}

function toneForTrend(trend: Institutional13FTrendItem["trend"]): Tone {
  if (trend === "positive" || trend === "new") return "good";
  if (trend === "negative") return "bad";
  if (trend === "neutral") return "neutral";
  return "warning";
}

function number(value?: number | null) {
  if (typeof value !== "number") return "-";
  return value.toLocaleString("de-DE");
}

function delta(value?: number | null) {
  if (typeof value !== "number") return "-";
  return `${value >= 0 ? "+" : ""}${value.toLocaleString("de-DE")} vs. Vorquartal`;
}

function pct(value?: number | null) {
  if (typeof value !== "number") return "-";
  return `${value >= 0 ? "+" : ""}${value.toFixed(1)}%`;
}

function usd(value?: number | null) {
  if (typeof value !== "number") return "-";
  if (value >= 1_000_000_000) return `$${(value / 1_000_000_000).toFixed(1)} Mrd.`;
  if (value >= 1_000_000) return `$${(value / 1_000_000).toFixed(1)} Mio.`;
  return `$${value.toLocaleString("de-DE", { maximumFractionDigits: 0 })}`;
}

function compact(value?: number | null) {
  if (typeof value !== "number") return "-";
  if (value >= 1_000_000_000) return `${(value / 1_000_000_000).toFixed(1)} Mrd.`;
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)} Mio.`;
  return value.toLocaleString("de-DE", { maximumFractionDigits: 0 });
}
