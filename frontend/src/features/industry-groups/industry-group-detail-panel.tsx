"use client";

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { api } from "@/lib/api/client";
import type { IndustryGroupStockRow } from "@/lib/types/api";

type MemberSort = "group_rank" | "overall_score" | "stock_rs" | "return_1m" | "return_3m" | "return_6m" | "return_12m";

export function IndustryGroupDetailPanel({ groupCode }: { groupCode: string }) {
  const [sort, setSort] = useState<MemberSort>("group_rank");
  const query = useQuery({
    queryKey: ["industry-group-detail", groupCode],
    queryFn: () => api.industryGroupDetail(groupCode),
    staleTime: 60_000
  });
  const data = query.data;
  const members = useMemo(() => {
    const rows = [...(data?.members ?? [])];
    rows.sort((left, right) => compareMembers(left, right, sort));
    return rows;
  }, [data?.members, sort]);

  if (query.isLoading) return <div className="rounded-[14px] border border-[#e3e8ef] bg-white p-4 text-sm text-[#687386]">Industry Group wird geladen…</div>;
  if (query.isError || !data) return <div className="rounded-[14px] border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800">Industry Group konnte nicht geladen werden.</div>;

  const group = data.group;
  return (
    <div className="space-y-4">
      <section className="rounded-[14px] border border-[#e3e8ef] bg-white p-4 shadow-[0_5px_18px_rgba(15,23,42,0.05)]">
        <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
          <div>
            <div className="text-[11px] font-semibold uppercase tracking-[0.1em] text-[#687386]">{group.code}</div>
            <h1 className="mt-1 text-2xl font-semibold text-[#172033]">{group.name}</h1>
            <p className="mt-1 text-sm text-[#687386]">{group.sector} → {group.industry_family} · {group.member_count} Aktien</p>
          </div>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            <Metric label="RS" value={group.rs_score != null ? Math.round(group.rs_score).toString() : "–"} />
            <Metric label="Rank" value={group.is_ranked && group.rank ? `#${group.rank}/${group.ranked_group_count}` : "Kleine Gruppe"} />
            <Metric label="Δ 5D" value={momentum(group.rank_change_5d)} />
            <Metric label="Δ 20D" value={momentum(group.rank_change_20d)} />
          </div>
        </div>
        <div className="mt-4 grid gap-3 sm:grid-cols-4">
          <ReturnTile label="1M" value={group.return_1m} excess={group.excess_return_1m} />
          <ReturnTile label="3M" value={group.return_3m} excess={group.excess_return_3m} />
          <ReturnTile label="6M" value={group.return_6m} excess={group.excess_return_6m} />
          <ReturnTile label="12M" value={group.return_12m} excess={group.excess_return_12m} />
        </div>
      </section>

      <section className="rounded-[14px] border border-[#e3e8ef] bg-white p-4 shadow-[0_5px_18px_rgba(15,23,42,0.05)]">
        <div className="mb-3 flex items-center justify-between gap-3">
          <div>
            <h2 className="font-semibold text-[#172033]">Performance vs. {group.benchmark_ticker}</h2>
            <p className="text-xs text-[#687386]">Gleichgewichteter Gruppenindex, Startwert 100.</p>
          </div>
        </div>
        <PerformanceChart points={data.performance_series} />
      </section>

      <section className="rounded-[14px] border border-[#e3e8ef] bg-white p-4 shadow-[0_5px_18px_rgba(15,23,42,0.05)]">
        <h2 className="font-semibold text-[#172033]">Top 3 Aktien der Gruppe</h2>
        <div className="mt-3 grid gap-3 lg:grid-cols-3">
          {data.top_stocks.map((item) => <TopStock key={item.ticker} item={item} />)}
        </div>
      </section>

      <section className="overflow-hidden rounded-[14px] border border-[#e3e8ef] bg-white shadow-[0_5px_18px_rgba(15,23,42,0.05)]">
        <div className="flex flex-wrap items-end justify-between gap-3 p-4">
          <div>
            <h2 className="font-semibold text-[#172033]">Aktien der Gruppe</h2>
            <p className="text-xs text-[#687386]">Rangfolge verwendet das bestehende zentrale Aktienranking.</p>
          </div>
          <label className="grid gap-1 text-xs text-[#687386]">Sortierung
            <select className="h-10 rounded-[9px] border border-[#d8e1ea] bg-white px-3 text-sm text-[#172033]" value={sort} onChange={(event) => setSort(event.target.value as MemberSort)}>
              <option value="group_rank">Gruppenrang</option>
              <option value="overall_score">Gesamtscore</option>
              <option value="stock_rs">Stock RS</option>
              <option value="return_1m">1M</option>
              <option value="return_3m">3M</option>
              <option value="return_6m">6M</option>
              <option value="return_12m">12M</option>
            </select>
          </label>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[1120px] text-left text-sm">
            <thead className="border-y border-[#e3e8ef] bg-[#f6f8fb] text-xs text-[#687386]"><tr>
              {["Rank", "Aktie", "Score", "Stock RS", "1D", "1M", "3M", "6M", "12M", "Kurs", "Issuer"].map((label) => <th key={label} className="px-3 py-3 font-medium">{label}</th>)}
            </tr></thead>
            <tbody>
              {members.map((item) => <tr key={item.ticker} className="border-b border-[#eef2f6] last:border-0 hover:bg-[#f9fbfc]">
                <td className="px-3 py-3 font-semibold">#{item.group_rank}</td>
                <td className="px-3 py-3"><Link href={`/stocks/${encodeURIComponent(item.ticker)}`} className="font-semibold text-[#0f766e] hover:underline">{item.ticker}</Link><div className="max-w-56 truncate text-xs text-[#687386]">{item.name}</div></td>
                <td className="px-3 py-3">{item.overall_score ?? "–"}</td>
                <td className="px-3 py-3">{item.stock_rs ?? "–"}</td>
                <td className={pctClass(item.return_1d)}>{pct(item.return_1d)}</td>
                <td className={pctClass(item.return_1m)}>{pct(item.return_1m)}</td>
                <td className={pctClass(item.return_3m)}>{pct(item.return_3m)}</td>
                <td className={pctClass(item.return_6m)}>{pct(item.return_6m)}</td>
                <td className={pctClass(item.return_12m)}>{pct(item.return_12m)}</td>
                <td className="px-3 py-3 tabular-nums">{typeof item.latest_close === "number" ? item.latest_close.toFixed(2) : "–"}</td>
                <td className="px-3 py-3 text-xs text-[#687386]">{item.issuer_representative ? "RS-Repräsentant" : `über ${item.representative_ticker ?? "–"}`}</td>
              </tr>)}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return <div className="min-w-28 rounded-[10px] border border-[#e3e8ef] bg-[#f9fbfc] p-3"><div className="text-xs text-[#687386]">{label}</div><div className="mt-1 font-semibold text-[#172033]">{value}</div></div>;
}

function ReturnTile({ label, value, excess }: { label: string; value?: number | null; excess?: number | null }) {
  return <div className="rounded-[10px] border border-[#e3e8ef] p-3"><div className="text-xs text-[#687386]">{label}</div><div className={`mt-1 text-lg font-semibold ${typeof value === "number" && value >= 0 ? "text-emerald-700" : "text-rose-700"}`}>{pct(value)}</div><div className="mt-1 text-xs text-[#687386]">vs. Benchmark {pct(excess)}</div></div>;
}

function TopStock({ item }: { item: IndustryGroupStockRow }) {
  return <Link href={`/stocks/${encodeURIComponent(item.ticker)}`} className="rounded-[10px] border border-[#e3e8ef] bg-[#f9fbfc] p-3 transition hover:border-[#0f766e]"><div className="font-semibold text-[#172033]">#{item.group_rank} {item.ticker}</div><div className="mt-1 truncate text-xs text-[#687386]">{item.name}</div><div className="mt-2 text-xs text-[#475569]">Score {item.overall_score ?? "–"} · RS {item.stock_rs ?? "–"}</div></Link>;
}

function compareMembers(left: IndustryGroupStockRow, right: IndustryGroupStockRow, sort: MemberSort) {
  if (sort === "group_rank") return left.group_rank - right.group_rank;
  const a = left[sort] as number | null | undefined;
  const b = right[sort] as number | null | undefined;
  return (b ?? Number.NEGATIVE_INFINITY) - (a ?? Number.NEGATIVE_INFINITY);
}

function pct(value?: number | null) {
  if (typeof value !== "number") return "–";
  return `${value >= 0 ? "+" : ""}${value.toFixed(1)}%`;
}

function pctClass(value?: number | null) {
  return `px-3 py-3 tabular-nums ${typeof value === "number" ? (value >= 0 ? "text-emerald-700" : "text-rose-700") : "text-[#687386]"}`;
}

function momentum(value?: number | null) {
  if (typeof value !== "number") return "–";
  if (value > 0) return `↑ ${value}`;
  if (value < 0) return `↓ ${Math.abs(value)}`;
  return "→ 0";
}

function PerformanceChart({ points }: { points: { date: string; group_index: number; benchmark_index: number }[] }) {
  if (points.length < 2) return <div className="py-8 text-sm text-[#687386]">Performance-Historie wird mit dem nächsten RS-Lauf aufgebaut.</div>;
  const width = 1000;
  const height = 260;
  const values = points.flatMap((point) => [point.group_index, point.benchmark_index]);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = Math.max(1, max - min);
  const pathFor = (key: "group_index" | "benchmark_index") => points.map((point, index) => {
    const x = (index / Math.max(1, points.length - 1)) * width;
    const y = height - ((point[key] - min) / range) * (height - 20) - 10;
    return `${index === 0 ? "M" : "L"} ${x.toFixed(1)} ${y.toFixed(1)}`;
  }).join(" ");
  return <div className="overflow-x-auto"><svg viewBox={`0 0 ${width} ${height}`} className="h-64 min-w-[760px] w-full" role="img" aria-label="Industry Group Performance gegenüber Benchmark"><path d={pathFor("group_index")} fill="none" stroke="#0f766e" strokeWidth="3" /><path d={pathFor("benchmark_index")} fill="none" stroke="#94a3b8" strokeWidth="2" /><text x="12" y="20" fontSize="13" fill="#0f766e">Industry Group</text><text x="132" y="20" fontSize="13" fill="#64748b">Benchmark</text></svg></div>;
}
