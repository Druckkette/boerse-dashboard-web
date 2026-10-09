"use client";

import { useState } from "react";
import Link from "next/link";
import { CalendarDays, ListFilter } from "lucide-react";
import { StatusChip } from "@/components/ui/status-chip";
import type { HomeDashboard, HomeEarningsCalendar, HomePortfolioAlert } from "@/lib/types/api";
import { Empty, Panel, shortDate } from "./home-ui";

const categoryLabels = { action: "Handlungsbedarf", observe: "Beobachten", data: "Daten prüfen" } as const;
export function PortfolioAlerts({ alerts, failed = false }: { alerts: HomePortfolioAlert[]; failed?: boolean }) {
  return <div className="mt-5 space-y-4 border-t border-[#e3e8ef] pt-4">
    {failed && <p role="status" className="text-xs text-[#b7791f]">Der Verkaufsmonitor konnte nicht geladen werden. Bewertungen dort prüfen.</p>}
    {!alerts.length && <Empty text="Keine gespeicherten Depotwarnungen. Eine vollständige Bewertung findest du im Verkaufsmonitor." />}
    {(["action", "observe", "data"] as const).map(category => {
      const rows = alerts.filter(row => row.category === category);
      if (!rows.length) return null;
      return <section key={category} aria-label={categoryLabels[category]}>
        <h3 className="mb-2 text-xs font-semibold text-[#475569]">{categoryLabels[category]} <span className="font-normal text-[#687386]">· {rows.length}</span></h3>
        <div className="divide-y divide-[#e8edf2]">{rows.map(row => <Link key={row.id} href={row.href} className="block rounded-lg py-3 focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#0f766e]">
          <div className="flex flex-wrap items-center justify-between gap-2"><span className="min-w-0 text-sm"><b className="text-[#172033]">{row.ticker}</b>{row.name && row.name !== row.ticker && <span className="ml-2 text-xs text-[#687386]">{row.name}</span>}</span><span className="flex items-center gap-2"><StatusChip tone={row.tone}>{row.label}</StatusChip>{row.recommendation_pct != null && <b className="text-xs text-[#c2413b]">Tranche {row.recommendation_pct} %</b>}</span></div>
          <p className="mt-1.5 text-xs leading-5 text-[#475569]">{row.detail}</p>
          {row.category === "data" && row.signal && <p className="text-xs leading-5 text-[#687386]">Gespeichertes Signal: {row.signal}</p>}
          {row.freshness && <p className="mt-1 text-[11px] leading-5 text-[#687386]">Bewertung {shortDate(row.last_seen_date)} · Monitor {monitorTime(row.generated_at)}{row.freshness !== "current" && " · Aktualität prüfen"}</p>}
        </Link>)}</div>
      </section>;
    })}
  </div>;
}
function monitorTime(value?: string | null) {
  if (!value || Number.isNaN(Date.parse(value))) return "Zeitpunkt fehlt";
  return new Intl.DateTimeFormat("de-DE", { timeZone: "Europe/Berlin", day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }).format(new Date(value)) + " Uhr";
}
export function earningsTime(value: string) {
  const normalized = value.trim().toLowerCase();
  if (["bmo", "before market open", "before_market_open"].includes(normalized)) return "Vorbörslich (US)";
  if (["amc", "after market close", "after_market_close"].includes(normalized)) return "Nachbörslich (US)";
  if (["dmh", "during market hours"].includes(normalized)) return "Während des US-Handels";
  return normalized ? `${value} · Zeitzone unbestätigt` : "Veröffentlichungszeit unbekannt";
}
export function HomeEarnings({ calendar }: { calendar?: HomeEarningsCalendar }) {
  const [days, setDays] = useState(14);
  const [watchlist, setWatchlist] = useState(false);
  const rows = (calendar?.rows || []).filter(row => row.days_until >= 0 && row.days_until < days && (row.scopes.includes("portfolio") || watchlist && row.scopes.includes("watchlist"))).sort((a, b) => a.date.localeCompare(b.date) || a.ticker.localeCompare(b.ticker));
  // Week boundaries use the Berlin calendar date supplied by the backend.
  const today = new Date(`${calendar?.today || "2000-01-01"}T12:00:00Z`);
  const daysToSunday = (7 - today.getUTCDay()) % 7;
  const groups = [
    { label: "Heute / morgen", rows: rows.filter(row => row.days_until <= 1) },
    { label: "Diese Woche", rows: rows.filter(row => row.days_until > 1 && row.days_until <= daysToSunday) },
    { label: "Nächste Woche", rows: rows.filter(row => row.days_until > Math.max(1, daysToSunday) && row.days_until <= daysToSunday + 7) },
    { label: "Später", rows: rows.filter(row => row.days_until > Math.max(1, daysToSunday + 7)) },
  ];
  return <Panel icon={CalendarDays} title="Anstehende Earnings" detail={`Nächste ${days} Kalendertage · ${watchlist ? "Depot & Watchlist" : "Depot"}`}>
    <div className="mb-4 flex flex-wrap items-center justify-between gap-3 text-xs">
      <label className="flex items-center gap-2 text-[#475569]">Zeitraum<select aria-label="Earnings-Zeitraum" value={days} onChange={event => setDays(Number(event.target.value))} className="rounded-lg border border-[#e3e8ef] bg-white px-2 py-1.5"><option value={14}>14 Tage</option><option value={30}>30 Tage</option></select></label>
      <label className="flex items-center gap-2 text-[#475569]"><input type="checkbox" checked={watchlist} onChange={event => setWatchlist(event.target.checked)} />Watchlist einbeziehen</label>
    </div>
    {!!calendar?.missing_portfolio_count && <p className="mb-3 text-[11px] leading-5 text-[#687386]">Für {calendar.missing_portfolio_count} Depotwerte ist kein Termin in den nächsten 30 Tagen gespeichert.</p>}
    {calendar?.status === "error" ? <Empty text="Earnings konnten nicht geladen werden. Termine bitte in der Aktienanalyse prüfen." /> : !rows.length ? <Empty text="Keine gespeicherten Earnings in diesem Zeitraum. Fehlende Termine bedeuten keine Entwarnung." /> : groups.filter(group => group.rows.length).map(group => <section key={group.label} className="mb-4 last:mb-0" aria-label={group.label}>
      <h3 className="mb-2 text-xs font-semibold text-[#475569]">{group.label}</h3>
      <div className="divide-y divide-[#e8edf2]">{group.rows.map(row => <Link key={`${row.ticker}:${row.date}`} href={row.href} className="block py-3 focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#0f766e]">
        <div className="flex flex-wrap items-start justify-between gap-2"><div><b className="text-sm text-[#172033]">{row.ticker}</b><p className="text-xs text-[#687386]">{row.name}</p></div><div className="text-right text-xs text-[#475569]"><b>{new Intl.DateTimeFormat("de-DE", { weekday: "short", day: "2-digit", month: "2-digit", year: "numeric", timeZone: "UTC" }).format(new Date(`${row.date}T12:00:00Z`))}</b><p>{row.days_until === 0 ? "Heute" : row.days_until === 1 ? "Morgen" : `In ${row.days_until} Tagen`}</p></div></div>
        <p className="mt-1.5 text-xs text-[#475569]">{earningsTime(row.time)}</p>
        <p className="mt-1 text-[11px] text-[#687386]">{row.scopes.includes("portfolio") ? "Depot" : "Watchlist"} · Quelle {row.source || "unbekannt"} · Kalenderangabe{row.fetched_at && ` · Stand ${shortDate(row.fetched_at.slice(0, 10))}`}</p>
        {row.date_conflict && <p className="mt-1 text-xs text-[#b7791f]">Abweichende Anbietertermine · Datum prüfen</p>}
      </Link>)}</div>
    </section>)}
  </Panel>;
}
export function HomeChanges({ changes, failed = false }: { changes: HomeDashboard["changes"]; failed?: boolean }) {
  const [scope, setScope] = useState("all");
  const [expanded, setExpanded] = useState(false);
  const rows = changes.filter(row => scope === "all" || row.scopes.includes(scope as "portfolio" | "watchlist" | "top_stocks"));
  const labels = { portfolio: "Depot", watchlist: "Watchlist", top_stocks: "Marktchancen" };
  return <Panel icon={ListFilter} title="Was hat sich verändert?" detail="Relevante Score- und RS-Bewegungen sowie neue und entfallene Signale seit dem vorherigen Handelstag.">
    <div className="mb-4 flex flex-wrap gap-2" aria-label="Veränderungen filtern">{[["all", "Alle"], ["portfolio", "Depot"], ["watchlist", "Watchlist"], ["top_stocks", "Marktchancen"]].map(([value, label]) => <button type="button" key={value} aria-pressed={scope === value} onClick={() => { setScope(value); setExpanded(false); }} className={`rounded-full px-3 py-1.5 text-xs font-semibold ${scope === value ? "bg-[#e8f4f2] text-[#0f766e]" : "bg-[#f1f4f7] text-[#687386]"}`}>{label}</button>)}</div>
    {!rows.length ? <Empty text={failed ? "Vergleichsstände konnten nicht geladen werden." : "Keine relevanten Änderungen in gespeicherten Vergleichen. Fehlende Vergleichsstände erzeugen keine Signale."} /> : <div className="divide-y divide-[#e8edf2]">{(expanded ? rows : rows.slice(0, 5)).map(row => <Link href={row.href} key={row.ticker} className="block py-3 focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#0f766e]">
      <div className="flex flex-wrap items-center justify-between gap-2"><span className="text-sm text-[#172033]"><b>{row.ticker}</b><span className="ml-2 text-xs text-[#687386]">{row.name}</span></span><StatusChip tone={row.tone || "neutral"}>{row.summary}</StatusChip></div>
      <p className="mt-1.5 text-xs leading-5 text-[#475569]">{row.details.join(" · ")}</p>
      <p className="mt-1 text-[11px] text-[#687386]">{row.scopes.map(value => labels[value]).join(" · ")} · {shortDate(row.previous_as_of)} → {shortDate(row.as_of)}</p>
    </Link>)}</div>}
    {rows.length > 5 && <button type="button" aria-expanded={expanded} onClick={() => setExpanded(!expanded)} className="mt-3 text-xs font-semibold text-[#0f766e]">{expanded ? "Weniger anzeigen" : `Alle ${rows.length} Veränderungen anzeigen`}</button>}
  </Panel>;
}
