"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { StatusChip } from "@/components/ui/status-chip";
import { api } from "@/lib/api/client";
import type { TopDailyStockItem } from "@/lib/types/api";

const number = (value: number | null | undefined, digits = 0) => value == null ? "–" : value.toLocaleString("de-DE", { maximumFractionDigits: digits, minimumFractionDigits: digits });

function rankChange(row: TopDailyStockItem) {
  if (row.previous_rank == null) return "kein Vortagsrang";
  if (row.previous_rank === row.rank) return `gestern #${row.previous_rank} · unverändert`;
  const delta = row.previous_rank - row.rank;
  return `gestern #${row.previous_rank} · ${delta > 0 ? "+" : ""}${delta}`;
}

export function TopDailyStocksPanel() {
  const query = useQuery({ queryKey: ["top-daily-stocks"], queryFn: api.topDailyStocks, staleTime: 60_000, refetchInterval: 60_000 });
  const data = query.data;
  return (
    <section className="rounded-2xl border border-[#dce5ed] bg-white p-5 shadow-sm" aria-label="Top 3 Aktien des Tages">
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-teal-700">Research-Shortlist</p>
          <h2 className="mt-1 text-xl font-bold text-[#172033]">Top 3 Aktien des Tages</h2>
          <p className="mt-1 text-sm text-[#687386]">Hohe Qualität und aktuelle Dynamik · keine Kaufempfehlung.</p>
        </div>
        <StatusChip tone={data?.status === "current" ? "good" : "warning"}>{data?.as_of ? `Stand ${data.as_of}${data.status === "stale" ? " · veraltet" : ""}` : "Noch nicht berechnet"}</StatusChip>
      </div>
      {query.isLoading && <p role="status" className="text-sm text-[#687386]">Tagesauswahl lädt…</p>}
      {query.error && <p role="alert" className="text-sm text-red-700">Tagesauswahl derzeit nicht verfügbar.</p>}
      {data && !data.rows.length && <p className="rounded-xl bg-[#f6f8fb] p-4 text-sm text-[#687386]">{data.status === "not_ready" ? "Die erste Bewertung steht noch aus. Nach dem nächsten Aktienranking erscheint hier die Shortlist." : "Heute erfüllen weniger als drei oder keine Aktien alle Daten- und Qualitätsfilter."}</p>}
      <div className="grid gap-4 xl:grid-cols-3">{data?.rows.map((row) => <article key={row.ticker} className="flex flex-col rounded-xl border border-[#e3e8ef] bg-[#fbfcfe] p-4 text-[#172033]">
        <div className="flex items-start justify-between gap-2"><div><span className="text-xs font-semibold text-teal-700">#{row.rank} · {rankChange(row)}</span><h3 className="mt-1 text-lg font-bold">{row.ticker}</h3><p className="text-xs text-[#687386]">{row.name}</p></div><div className="text-right"><p className="text-2xl font-bold text-teal-800">{number(row.daily_opportunity_score, 1)}</p><p className="text-xs text-[#687386]">Daily Score</p></div></div>
        <div className="mt-4 grid grid-cols-2 gap-x-4 gap-y-2 rounded-lg bg-white p-3 text-xs sm:grid-cols-3 xl:grid-cols-2">
          <Metric label="Kurs" value={row.last_close == null ? "–" : `$${number(row.last_close, 2)}`} />
          <Metric label="Qualität" value={number(row.quality_score)} />
          <Metric label="Dynamik" value={number(row.daily_dynamics_score, 1)} />
          <Metric label="RS" value={`${number(row.rs_rating)}${row.rs_rating_delta == null ? "" : ` (${row.rs_rating_delta > 0 ? "+" : ""}${number(row.rs_rating_delta)})`}`} />
          <Metric label="Technisch" value={number(row.technical_score)} />
          <Metric label="Fundamental" value={number(row.fundamental_score)} />
          <Metric label="Trend" value={number(row.moving_average_score)} />
          <Metric label="Chart" value={number(row.chart_behavior_score)} />
        </div>
        <div className="mt-4"><h4 className="text-xs font-semibold uppercase tracking-wide text-[#687386]">Warum interessant</h4><ul className="mt-2 space-y-1 text-sm">{row.reasons.map((reason) => <li key={reason}>• {reason}</li>)}</ul></div>
        <div className="mt-4"><h4 className="text-xs font-semibold uppercase tracking-wide text-[#687386]">Heute verbessert</h4><p className="mt-1 text-sm text-[#475569]">{row.positive_changes.length ? row.positive_changes.join(" · ") : "Keine neue Verbesserung im gespeicherten Vergleich"}</p></div>
        {!!row.warnings.length && <div className="mt-4 rounded-lg bg-amber-50 p-2 text-xs text-amber-900">{row.warnings.join(" · ")}</div>}
        <Link className="mt-5 inline-flex justify-center rounded-lg bg-teal-700 px-3 py-2 text-sm font-semibold text-white hover:bg-teal-800" href={`/stocks/${encodeURIComponent(row.ticker)}`}>Aktie genauer prüfen</Link>
      </article>)}</div>
    </section>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return <div><span className="text-[#687386]">{label}</span><div className="font-semibold tabular-nums">{value}</div></div>;
}
