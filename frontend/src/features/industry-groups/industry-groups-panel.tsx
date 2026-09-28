"use client";

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { api } from "@/lib/api/client";
import type { IndustryGroupRankingRow } from "@/lib/types/api";

type SortKey = "rank" | "rs_score" | "return_1m" | "return_3m" | "return_6m" | "return_12m" | "rank_change_5d" | "rank_change_20d" | "member_count";

export function IndustryGroupsPanel() {
  const [sector, setSector] = useState("");
  const [family, setFamily] = useState("");
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState<SortKey>("rank");
  const [includeSmall, setIncludeSmall] = useState(true);

  const query = useQuery({
    queryKey: ["industry-group-rankings", sector, family, includeSmall],
    queryFn: () => {
      const params = new URLSearchParams();
      if (sector) params.set("sector", sector);
      if (family) params.set("industry_family", family);
      params.set("include_small", String(includeSmall));
      return api.industryGroupRankings(params.toString());
    },
    staleTime: 60_000
  });

  const rows = useMemo(() => query.data?.rows ?? [], [query.data?.rows]);
  const sectors = useMemo(() => Array.from(new Set(rows.map((row) => row.sector))).sort(), [rows]);
  const families = useMemo(() => Array.from(new Set(rows.map((row) => row.industry_family))).sort(), [rows]);

  const visible = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return [...rows]
      .filter((row) => !needle || row.name.toLowerCase().includes(needle) || row.code.toLowerCase().includes(needle))
      .sort((left, right) => compareRows(left, right, sort));
  }, [rows, search, sort]);

  return (
    <div className="space-y-4">
      <section className="rounded-[14px] border border-[#e3e8ef] bg-white p-4 shadow-[0_5px_18px_rgba(15,23,42,0.05)]">
        <div className="flex flex-col gap-3 xl:flex-row xl:items-end xl:justify-between">
          <div>
            <h1 className="text-xl font-semibold text-[#172033]">Industry Group Relative Strength</h1>
            <p className="mt-1 text-sm text-[#687386]">
              {query.data ? `Stand ${query.data.as_of} · Benchmark ${query.data.benchmark} · Mindestgröße ${query.data.min_group_members_for_rs}` : "Gruppenranking wird geladen…"}
            </p>
          </div>
          <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-5">
            <select className={control} value={sector} onChange={(event) => { setSector(event.target.value); setFamily(""); }}>
              <option value="">Alle Sektoren</option>
              {sectors.map((item) => <option key={item}>{item}</option>)}
            </select>
            <select className={control} value={family} onChange={(event) => setFamily(event.target.value)}>
              <option value="">Alle Families</option>
              {families.map((item) => <option key={item}>{item}</option>)}
            </select>
            <input className={control} placeholder="Gruppe suchen" value={search} onChange={(event) => setSearch(event.target.value)} />
            <select className={control} value={sort} onChange={(event) => setSort(event.target.value as SortKey)}>
              <option value="rank">Rank</option>
              <option value="rs_score">RS</option>
              <option value="return_1m">1M</option>
              <option value="return_3m">3M</option>
              <option value="return_6m">6M</option>
              <option value="return_12m">12M</option>
              <option value="rank_change_5d">5D Rank Δ</option>
              <option value="rank_change_20d">20D Rank Δ</option>
              <option value="member_count">Mitglieder</option>
            </select>
            <label className="flex items-center gap-2 rounded-[9px] border border-[#d8e1ea] px-3 py-2 text-sm text-[#475569]">
              <input type="checkbox" checked={includeSmall} onChange={(event) => setIncludeSmall(event.target.checked)} />
              Kleine Gruppen
            </label>
          </div>
        </div>
      </section>

      {query.isError && <div className="rounded-[14px] border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800">Industry-Group-RS konnte nicht geladen werden.</div>}
      {query.isLoading && <div className="rounded-[14px] border border-[#e3e8ef] bg-white p-4 text-sm text-[#687386]">Daten werden geladen…</div>}

      {!query.isLoading && !query.isError && (
        <section className="overflow-hidden rounded-[14px] border border-[#e3e8ef] bg-white shadow-[0_5px_18px_rgba(15,23,42,0.05)]">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[1260px] text-left text-sm">
              <thead className="border-b border-[#e3e8ef] bg-[#f6f8fb] text-xs text-[#687386]">
                <tr>
                  {["Rank", "Industry Group", "Sektor", "Mitglieder", "RS", "1M", "3M", "6M", "12M", "Δ5D", "Δ20D", "Top Aktie"].map((label) => (
                    <th key={label} className="px-3 py-3 font-medium">{label}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {visible.map((row) => (
                  <tr key={row.code} className="border-b border-[#eef2f6] last:border-0 hover:bg-[#f9fbfc]">
                    <td className="px-3 py-3 font-semibold tabular-nums" title={rankStatusLabel(row)}>{row.is_ranked && row.rank ? `#${row.rank}` : "–"}</td>
                    <td className="px-3 py-3">
                      <Link className="font-semibold text-[#0f766e] hover:underline" href={`/industry-groups/${encodeURIComponent(row.code)}`}>{row.name}</Link>
                      <div className="mt-0.5 text-xs text-[#687386]">{row.code} · {row.industry_family}</div>
                    </td>
                    <td className="px-3 py-3">{row.sector}</td>
                    <td className="px-3 py-3 tabular-nums">{row.member_count}</td>
                    <td className="px-3 py-3 font-semibold tabular-nums">{row.rs_score != null ? Math.round(row.rs_score) : "–"}</td>
                    <td className={pctClass(row.return_1m)}>{formatPct(row.return_1m)}</td>
                    <td className={pctClass(row.return_3m)}>{formatPct(row.return_3m)}</td>
                    <td className={pctClass(row.return_6m)}>{formatPct(row.return_6m)}</td>
                    <td className={pctClass(row.return_12m)}>{formatPct(row.return_12m)}</td>
                    <td className="px-3 py-3 tabular-nums">{formatMomentum(row.rank_change_5d)}</td>
                    <td className="px-3 py-3 tabular-nums">{formatMomentum(row.rank_change_20d)}</td>
                    <td className="px-3 py-3">
                      {row.top_stock ? <Link className="font-semibold text-[#0f766e] hover:underline" href={`/stocks/${encodeURIComponent(row.top_stock.ticker)}`}>{row.top_stock.ticker}</Link> : "–"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {!visible.length && <p className="p-4 text-sm text-[#687386]">Keine Gruppen für diese Auswahl.</p>}
        </section>
      )}
    </div>
  );
}

const control = "h-10 rounded-[9px] border border-[#d8e1ea] bg-white px-3 text-sm text-[#172033] outline-none focus:border-[#0f766e]";

function compareRows(left: IndustryGroupRankingRow, right: IndustryGroupRankingRow, sort: SortKey) {
  if (sort === "rank") return (left.rank ?? Number.MAX_SAFE_INTEGER) - (right.rank ?? Number.MAX_SAFE_INTEGER);
  const a = left[sort] as number | null | undefined;
  const b = right[sort] as number | null | undefined;
  return (b ?? Number.NEGATIVE_INFINITY) - (a ?? Number.NEGATIVE_INFINITY);
}

function formatPct(value?: number | null) {
  if (typeof value !== "number") return "–";
  return `${value >= 0 ? "+" : ""}${value.toFixed(1)}%`;
}

function pctClass(value?: number | null) {
  return `px-3 py-3 tabular-nums ${typeof value === "number" ? (value >= 0 ? "text-emerald-700" : "text-rose-700") : "text-[#687386]"}`;
}

function formatMomentum(value?: number | null) {
  if (typeof value !== "number") return "–";
  if (value > 0) return `↑${value}`;
  if (value < 0) return `↓${Math.abs(value)}`;
  return "→0";
}

function rankStatusLabel(row: IndustryGroupRankingRow) {
  if (row.rank_status === "small_group") return "Zu wenige Emittenten für ein offizielles Ranking";
  if (row.rank_status === "insufficient_history") return "Nicht genügend vollständige Kurshistorie";
  return `Offizieller Rang ${row.rank ?? "–"} von ${row.ranked_group_count}`;
}
