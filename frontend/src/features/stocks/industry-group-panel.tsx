"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { api } from "@/lib/api/client";

export function IndustryGroupPanel({ ticker }: { ticker: string }) {
  const clean = ticker.toUpperCase();
  const query = useQuery({
    queryKey: ["industry-group-context", clean],
    queryFn: () => api.industryGroupStockContext(clean),
    staleTime: 60_000
  });

  if (query.isLoading) {
    return <section className="rounded-[14px] border border-[#e3e8ef] bg-white p-4 text-sm text-[#687386]">Industry Group wird geladen…</section>;
  }
  if (query.isError || !query.data) {
    return <section className="rounded-[14px] border border-[#e3e8ef] bg-white p-4 text-sm text-[#687386]">Für diese Aktie ist noch kein Industry-Group-RS verfügbar.</section>;
  }

  const { group, stock, top_stocks: topStocks } = query.data;

  return (
    <section className="rounded-[14px] border border-[#e3e8ef] bg-white p-4 shadow-[0_5px_18px_rgba(15,23,42,0.05)]">
      <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
        <div>
          <div className="text-[11px] font-semibold uppercase tracking-[0.1em] text-[#687386]">Industry Group</div>
          <h2 className="mt-1 text-xl font-semibold text-[#172033]">{group.name}</h2>
          <div className="mt-1 text-sm text-[#687386]">{group.sector} → {group.industry_family}</div>
        </div>
        <Link
          href={`/industry-groups/${encodeURIComponent(group.code)}`}
          className="inline-flex items-center gap-2 self-start rounded-[9px] border border-[#cfd8e3] px-3 py-2 text-sm font-semibold text-[#0f766e] transition hover:border-[#0f766e]"
        >
          Industry Group öffnen <ArrowRight size={15} />
        </Link>
      </div>

      <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
        <Metric label="Group RS" value={group.rs_score != null ? Math.round(group.rs_score).toString() : "–"} />
        <Metric
          label="Group Rank"
          value={group.is_ranked && group.rank ? `#${group.rank} / ${group.ranked_group_count}` : "Kleine Vergleichsgruppe"}
        />
        <Metric label={`${clean} in Gruppe`} value={stock.group_rank ? `#${stock.group_rank} / ${stock.group_members}` : "–"} />
        <Metric label="5D Rank" value={formatMomentum(group.rank_change_5d)} />
        <Metric label="20D Rank" value={formatMomentum(group.rank_change_20d)} />
      </div>

      <div className="mt-4 grid gap-3 sm:grid-cols-4">
        <ReturnTile label="1M" value={group.return_1m} />
        <ReturnTile label="3M" value={group.return_3m} />
        <ReturnTile label="6M" value={group.return_6m} />
        <ReturnTile label="12M" value={group.return_12m} />
      </div>

      <div className="mt-5">
        <div className="mb-2 text-sm font-semibold text-[#172033]">Top 3 der Gruppe</div>
        <div className="grid gap-2 lg:grid-cols-3">
          {topStocks.map((item) => (
            <Link
              href={`/stocks/${encodeURIComponent(item.ticker)}`}
              key={item.ticker}
              className={[
                "rounded-[10px] border p-3 transition hover:border-[#0f766e]",
                item.ticker === clean ? "border-[#0f766e] bg-[#e8f4f2]" : "border-[#e3e8ef] bg-[#f9fbfc]"
              ].join(" ")}
            >
              <div className="flex items-center justify-between gap-2">
                <div className="font-semibold text-[#172033]">#{item.group_rank} {item.ticker}</div>
                {item.ticker === clean && <span className="text-[10px] font-semibold uppercase tracking-wide text-[#0f766e]">Aktuelle Aktie</span>}
              </div>
              <div className="mt-1 truncate text-xs text-[#687386]" title={item.name}>{item.name}</div>
              <div className="mt-2 flex gap-3 text-xs text-[#475569]">
                <span>Score {item.overall_score ?? "–"}</span>
                <span>RS {item.stock_rs ?? "–"}</span>
              </div>
            </Link>
          ))}
        </div>
      </div>
    </section>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return <div className="rounded-[10px] border border-[#e3e8ef] bg-[#f9fbfc] p-3"><div className="text-xs text-[#687386]">{label}</div><div className="mt-1 text-lg font-semibold text-[#172033]">{value}</div></div>;
}

function ReturnTile({ label, value }: { label: string; value?: number | null }) {
  const text = formatPct(value);
  const tone = typeof value === "number" ? (value >= 0 ? "text-emerald-700" : "text-rose-700") : "text-[#687386]";
  return <div className="rounded-[10px] border border-[#e3e8ef] px-3 py-2"><div className="text-xs text-[#687386]">{label}</div><div className={`mt-1 font-semibold tabular-nums ${tone}`}>{text}</div></div>;
}

function formatPct(value?: number | null) {
  if (typeof value !== "number") return "–";
  return `${value >= 0 ? "+" : ""}${value.toFixed(1)}%`;
}

function formatMomentum(value?: number | null) {
  if (typeof value !== "number") return "–";
  if (value > 0) return `↑ ${value}`;
  if (value < 0) return `↓ ${Math.abs(value)}`;
  return "→ 0";
}
