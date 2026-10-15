"use client";
import { useBetaMode } from "@/components/beta-mode-provider";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { StatusChip } from "@/components/ui/status-chip";
import { api } from "@/lib/api/client";
import type { TopDailyStockItem } from "@/lib/types/api";
import { dailyChangeDisplay, dailyExplanations, dailyWarningDisplay } from "./top-daily-display";

const number = (value: number | null | undefined, digits = 0) => value == null ? "–" : value.toLocaleString("de-DE", { maximumFractionDigits: digits, minimumFractionDigits: digits });

function rankChange(row: TopDailyStockItem) {
  if (row.previous_rank == null) return "kein Vortagsrang";
  if (row.previous_rank === row.rank) return `gestern #${row.previous_rank} · unverändert`;
  const delta = row.previous_rank - row.rank;
  return `gestern #${row.previous_rank} · ${delta > 0 ? "+" : ""}${delta}`;
}

export function TopDailyStocksPanel() {
  const beta = useBetaMode();
  const query = useQuery({ queryKey: ["top-daily-stocks"], queryFn: api.topDailyStocks, staleTime: 60_000, refetchInterval: beta ? false : 60_000 });
  const data = query.data;
  return (
    <section id="top-daily" className="rounded-2xl border border-[#dce5ed] bg-white p-5 shadow-sm" aria-label="Top 3 Aktien des Tages">
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
      <p className="mb-4 text-xs leading-5 text-[#687386]">Der Tages-Score kombiniert die aktuelle Qualität mit der Dynamik. Alle Scores reichen von 0 bis 100.</p>
      <div className="grid items-stretch gap-4 xl:grid-cols-3">{data?.rows.map(row => <DailyStockCard key={row.ticker} row={row} />)}</div>
    </section>
  );
}

function DailyStockCard({ row }: { row: TopDailyStockItem }) {
  const explanations = dailyExplanations(row);
  const warnings = row.warnings.map(dailyWarningDisplay);
  return <article aria-label={`${row.ticker} · Rang ${row.rank}`} className="flex min-w-0 flex-col rounded-xl border border-[#e3e8ef] bg-[#fbfcfe] text-[#172033]">
    <div className="p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0"><span className="text-xs font-semibold text-teal-700">#{row.rank} · {rankChange(row)}</span><h3 className="mt-2 text-xl font-bold">{row.ticker}</h3></div>
        <div className="shrink-0 text-right"><p className="text-3xl font-bold tabular-nums text-teal-800">{number(row.daily_opportunity_score, 1)}</p><p className="text-xs text-[#687386]">Tages-Score</p></div>
      </div>
      <p className="mt-1 text-xs leading-5 text-[#687386]">{row.name}</p>
      <p className="mt-2 text-sm font-semibold tabular-nums">{row.last_close == null ? "Kurs fehlt" : `$${number(row.last_close, 2)}`}<span className="ml-2 text-xs font-normal text-[#687386]">Letzter Schlusskurs</span></p>
      <dl className="mt-4 grid grid-cols-3 gap-2 rounded-lg border border-[#e8edf2] bg-white p-3">
        <Metric label="Qualität" value={number(row.quality_score)} />
        <Metric label="Dynamik" value={number(row.daily_dynamics_score, 1)} />
        <Metric label="RS-Rating" value={number(row.rs_rating)} />
      </dl>
      <details className="mt-3 text-xs">
        <summary className="cursor-pointer rounded font-semibold text-[#475569] focus-visible:outline-2 focus-visible:outline-teal-700">Weitere Kennzahlen</summary>
        <dl className="mt-3 grid grid-cols-2 gap-3">
          <Metric label="Technisch" value={number(row.technical_score)} />
          <Metric label="Fundamental" value={number(row.fundamental_score)} />
          <Metric label="Trend" value={number(row.moving_average_score)} />
          <Metric label="Chart" value={number(row.chart_behavior_score)} />
        </dl>
      </details>
    </div>
    <div className="border-t border-[#e3e8ef] p-4">
      <h4 className="text-sm font-semibold">Seit dem vorherigen Handelstag</h4>
      {explanations.changes.length || explanations.signals.length ? <>
        {!!explanations.changes.length && <dl className="mt-2 divide-y divide-[#e8edf2]">{explanations.changes.map(text => {
          const change = dailyChangeDisplay(text);
          return <div key={text} className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1 py-2 text-xs leading-5"><dt className="text-[#475569]">{change.label}</dt>{change.value && <dd className="font-semibold tabular-nums text-teal-800">{change.value}</dd>}</div>;
        })}</dl>}
        {!!explanations.signals.length && <div className="mt-3"><h5 className="text-xs font-medium text-[#687386]">Neu erfüllte Kriterien</h5><ul className="mt-2 space-y-2 text-xs leading-5 text-[#475569]">{explanations.signals.map(signal => <li key={signal} className="flex gap-2"><span aria-hidden="true" className="text-teal-700">✓</span><span>{signal}</span></li>)}</ul></div>}
      </> : <p className="mt-2 text-xs leading-5 text-[#687386]">Keine neue Verbesserung im gespeicherten Vergleich.</p>}
      {!!explanations.reasons.length && <div className="mt-4"><h5 className="text-xs font-medium text-[#687386]">Weitere Stärken</h5><ul className="mt-2 list-disc space-y-1 pl-4 text-xs leading-5 text-[#475569]">{explanations.reasons.map(reason => <li key={reason}>{reason}</li>)}</ul></div>}
    </div>
    {!!warnings.length && <div className="space-y-3 border-t border-[#e3e8ef] px-4 py-3">{warnings.map((warning, index) => <div key={index} className={warning.informational ? "text-xs leading-5 text-[#475569]" : "rounded-lg bg-amber-50 p-3 text-xs leading-5 text-amber-900"}>
      <p className="mb-1 font-semibold">{warning.informational ? "Relative Stärke einordnen" : "Vor dem Kauf prüfen"}</p>
      <p>{warning.title}</p>{warning.detail && <p className="mt-1 text-[#687386]">{warning.detail}</p>}
    </div>)}</div>}
    <div className="mt-auto p-4"><Link className="inline-flex w-full justify-center rounded-lg bg-teal-700 px-3 py-2.5 text-sm font-semibold text-white! hover:bg-teal-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-700" href={`/stocks/${encodeURIComponent(row.ticker)}`}>Aktie genauer prüfen</Link></div>
  </article>;
}

function Metric({ label, value }: { label: string; value: string }) {
  return <div><dt className="text-xs text-[#687386]">{label}</dt><dd className="mt-1 text-base font-semibold tabular-nums">{value}</dd></div>;
}
