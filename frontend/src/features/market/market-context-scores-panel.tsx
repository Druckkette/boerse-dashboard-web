"use client";

import { useQuery } from "@tanstack/react-query";
import { ChevronDown } from "lucide-react";
import { StatusChip } from "@/components/ui/status-chip";
import { api } from "@/lib/api/client";
import type { MarketContextScore, MarketContextScores, MarketScoreCriterion, Tone } from "@/lib/types/api";
import { useMarketRefetchInterval } from "./query-timing";

export function MarketContextScoresPanel({ ticker, asOf }: { ticker: string; asOf: string }) {
  const refetchInterval = useMarketRefetchInterval();
  const query = useQuery({
    queryKey: ["market-context-scores", ticker, asOf],
    queryFn: () => api.marketContextScores(ticker, asOf),
    enabled: Boolean(asOf),
    staleTime: 60_000,
    refetchInterval
  });
  if (!query.data || query.data.ticker !== ticker || query.data.as_of !== asOf) {
    return <section id="context-scores" className="scroll-mt-36 rounded-2xl border border-[#e3e8ef] bg-white p-5 text-sm text-[#687386]">
      {query.isError ? "Kontext-Kennzahlen nicht verfügbar. Die bestätigte Trendampel wird oben angezeigt." : query.data ? `Für die bestätigte Sitzung ${asOf} liegt noch kein passender Kontext-Datenstand vor.` : "Kontext-Kennzahlen werden geladen …"}
    </section>;
  }
  return <ContextScoresView data={query.data} updateFailed={query.isError} />;
}

export function ContextScoresView({ data, updateFailed = false }: { data: MarketContextScores; updateFailed?: boolean }) {
  return <section id="context-scores" aria-label="Informationsscores zur Marktphase" className="scroll-mt-36 rounded-[22px] border border-[#dfe5ec] bg-white p-4 shadow-[0_12px_34px_rgba(15,23,42,0.065)] sm:p-5">
    <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
      <div>
        <h2 className="text-base font-semibold text-[#0f172a]">Kontext zur Trendampel</h2>
        <p className="mt-1 max-w-4xl text-sm leading-6 text-[#687386]">Die Trendampel bestimmt die Marktphase. Diese fünf Kennzahlen ergänzen sie mit gewichteten Informationen.</p>
      </div>
      <span className="text-xs text-[#687386]">{data.ticker} · Stand {data.as_of}</span>
    </div>
    <div className="grid min-w-0 items-start gap-3 sm:grid-cols-2 xl:grid-cols-5">
      {data.scores.map(score => <ContextScoreCard key={score.key} item={score} />)}
    </div>
    <p className="mt-4 text-xs leading-5 text-[#687386]">Unter 40: schwach · 40 bis unter 65: gemischt · ab 65: konstruktiv. Höhere Werte beschreiben günstigere Bedingungen. Die Gewichte sind ein erklärbarer Startentwurf.</p>
    {updateFailed ? <p className="mt-2 text-xs text-[#687386]">Aktualisierung nicht verfügbar; angezeigt wird der letzte erfolgreich geladene Datenstand.</p> : null}
    {data.notes.length > 0 ? <details className="mt-3 rounded-lg border border-[#e3e8ef] px-3 py-2 text-xs text-[#687386]">
      <summary className="cursor-pointer font-medium">Hinweise zum Datenstand ({data.notes.length})</summary>
      <ul className="mt-2 list-disc space-y-1 pl-4">{data.notes.map(note => <li key={note}>{note}</li>)}</ul>
    </details> : null}
  </section>;
}

function ContextScoreCard({ item }: { item: MarketContextScore }) {
  return <article aria-label={`${item.title} Informationsscore`} className="min-w-0 rounded-xl border border-[#e3e8ef] bg-[#fbfcfe] p-3.5">
    <h3 className="text-sm font-semibold text-[#172033]">{item.title}</h3>
    <p className="mt-1 min-h-8 text-[11px] leading-4 text-[#687386]">{item.scope}</p>
    <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
      <div className="text-2xl font-semibold tabular-nums text-[#172033]">{number(item.score, 2)}<span className="ml-1 text-xs font-normal text-[#687386]">/ 100</span></div>
      <StatusChip tone={item.tone}>{item.status}</StatusChip>
    </div>
    <ScoreBar score={item.score} tone={item.tone} label={`${item.title} Score`} />
    {item.data_status !== "complete" ? <p className="mt-2 text-[11px] leading-4 text-[#687386]">{item.score === null ? "Gesamtwert nicht bewertbar" : "Teilweise bewertbar"} · Bewertete Beiträge {number(item.coverage_pct)} %</p> : null}
    <div className="mt-4 space-y-2.5">
      {item.subscores.filter(sub => sub.weight > 0).map(sub => <div key={sub.key}>
        <div className="flex items-start justify-between gap-2 text-xs">
          <span className="min-w-0 leading-4 text-[#687386]">{sub.label}<span className="ml-1 text-[10px]">({sub.weight} %)</span></span>
          <span className="shrink-0 font-semibold tabular-nums text-[#172033]">{number(sub.score, 2)}</span>
        </div>
        <ScoreBar score={sub.score} tone={sub.tone} label={`${item.title}: ${sub.label}`} />
        {sub.data_status !== "complete" ? <span className="text-[10px] text-[#687386]">{sub.score === null ? "Nicht bewertbar" : "Teilwerte fehlen"}</span> : null}
      </div>)}
    </div>
    <details className="group mt-4 border-t border-[#e3e8ef] pt-3">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-2 text-xs font-semibold text-[#172033]">Beiträge & Regeln<ChevronDown size={14} className="shrink-0 transition-transform group-open:rotate-180" /></summary>
      <p className="mt-3 text-[11px] leading-5 text-[#687386]">{item.message}</p>
      <p className="mt-2 text-[11px] leading-5 text-[#687386]">Unterscore = gewichteter Mittelwert der bewertbaren Kriterien. Für die Kennzahl zählt jedes Gruppengewicht nur im Umfang seiner verfügbaren Beiträge. Fehlende Beiträge erhalten keinen Malus; bei weniger als 50 % bewertbarer Gewichtung bleibt der Gesamtwert offen.</p>
      {item.subscores.map(sub => <div key={sub.key} className="mt-4 space-y-2">
        <h4 className="text-xs font-semibold text-[#172033]">{sub.label} · {sub.weight ? `${sub.weight} %` : "nur Information"}</h4>
        {sub.criteria.map(c => <CriterionContribution key={c.id} item={c} />)}
      </div>)}
    </details>
  </article>;
}

function CriterionContribution({ item }: { item: MarketScoreCriterion }) {
  const label = item.evaluation === "missing" ? "Nicht bewertbar" : item.evaluation === "info" ? "Nur Information" : item.evaluation === "not_applicable" ? "Aktuell nicht anwendbar" : `${number(item.score)} / 100`;
  return <div className="min-w-0 rounded-lg border border-[#e3e8ef] bg-white p-2.5 text-[11px] leading-5">
    <div className="font-semibold text-[#172033]">{item.id} · {item.label}</div>
    <div className="mt-1 break-words text-[#687386]">{item.value}</div>
    <div className="mt-1 flex flex-wrap gap-x-2 text-[#172033]"><span>Gewicht {number(item.weight, 2)}</span><span>{label}</span></div>
    {item.contribution != null ? <p className="text-[#687386]">Anteil am Unterscore: {number(item.contribution)} Punkte</p> : null}
    <p className="mt-1 text-[#687386]">{item.rule}</p>
    {item.explanation ? <p className="mt-1 text-[#687386]">{item.explanation}</p> : null}
  </div>;
}

function ScoreBar({ score, tone, label }: { score: number | null; tone: Tone; label: string }) {
  const color = tone === "good" ? "#138a57" : tone === "bad" ? "#d14c43" : tone === "warning" ? "#c39137" : "#94a3b8";
  return <div role={score == null ? undefined : "meter"} aria-label={label} aria-valuemin={score == null ? undefined : 0} aria-valuemax={score == null ? undefined : 100} aria-valuenow={score ?? undefined} className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-[#e7ebf0]">
    <div className="h-full rounded-full" style={{ width: `${score ?? 0}%`, backgroundColor: color }} />
  </div>;
}

function number(value: number | null, digits = 0) {
  return value == null ? "—" : new Intl.NumberFormat("de-DE", { maximumFractionDigits: digits }).format(value);
}
