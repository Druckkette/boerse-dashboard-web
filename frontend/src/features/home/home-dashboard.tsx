"use client";

import { useQuery } from "@tanstack/react-query";
import { BriefcaseBusiness, ChevronDown, CircleAlert, Clock3, Layers3, LineChart, TrendingUp } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { KpiCard } from "@/components/ui/kpi-card";
import { StatusChip } from "@/components/ui/status-chip";
import { api } from "@/lib/api/client";
import type { HomeDashboard as HomeData, Tone } from "@/lib/types/api";
import { IndexCard } from "./home-index-card";
import { HomeSystemStatus, HomeWatchlist } from "./home-personal";
import { Empty, marketTone, number, Panel, shortDate, signedPercent, TextLink } from "./home-ui";

export function HomeDashboard() {
  const query = useQuery({ queryKey: ["home-dashboard"], queryFn: api.home, staleTime: 30_000, refetchInterval: 60_000 });
  const [now, setNow] = useState(() => new Date());
  const [systemOpen, setSystemOpen] = useState(false);
  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 60_000);
    return () => window.clearInterval(timer);
  }, []);
  if (query.isLoading) return <HomeLoading />;
  if (query.error) return <div className="dashboard-section" role="alert">Die Startseite konnte nicht geladen werden. <button type="button" className="font-semibold text-[#0f766e]" onClick={() => query.refetch()}>Erneut versuchen</button></div>;
  if (!query.data) return null;
  const data = query.data;
  return <div className="space-y-5">
    <h1 className="sr-only">Startseite</h1>
    <div className="flex flex-wrap items-center justify-between gap-3 text-xs text-[#687386]">
      <p className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <span>{new Intl.DateTimeFormat("de-DE", { timeZone: "Europe/Berlin", weekday: "long", day: "2-digit", month: "long" }).format(now)}</span>
        <span className="inline-flex items-center gap-1.5"><Clock3 size={13} />{data.market.session?.phase === "open" ? "US-Handel läuft" : data.market.session?.phase === "closed" ? "US-Handel geschlossen" : "Handelsstatus fehlt"}</span>
        <span>Letzter Handelstag {shortDate(data.market.session?.last_completed_as_of)}</span>
      </p>
      <a href="#systemstatus" onClick={() => setSystemOpen(true)} className="rounded-full focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#0f766e]">Daten & Meldungen</a>
    </div>

    <MarketOverview data={data} />
    <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
      <Panel id="aufgaben" icon={CircleAlert} title="Aufgaben & Veränderungen" detail="Verkaufssignale, Datenprobleme und Earnings zuerst. Jede Aktie erscheint einmal." action={<span className="rounded-full bg-[#edf3f6] px-2.5 py-1 text-xs font-semibold text-[#475569]">{data.priorities_total} Hinweise</span>}>
        <AttentionList data={data} />
      </Panel>
      <PortfolioOverview data={data} />
    </div>
    <Panel icon={TrendingUp} title="Recherche" detail="Die Tagesauswahl und führende Branchen als Einstieg in die Aktienanalyse.">
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)]">
        <div><div className="mb-3 flex items-center justify-between"><h3 className="text-xs font-semibold uppercase tracking-wider text-[#687386]">Top Aktien</h3><TextLink href="/stocks#top-daily">Tagesauswahl</TextLink></div><Opportunities data={data} /></div>
        <div className="lg:border-l lg:border-[#e3e8ef] lg:pl-6"><div className="mb-3 flex items-center justify-between gap-2"><h3 className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-[#687386]"><Layers3 size={14} />Führende Branchen</h3><TextLink href="/industry-groups">Rangliste</TextLink></div><Groups data={data} /></div>
      </div>
    </Panel>
    <HomeWatchlist data={data} />
    <HomeSystemStatus open={systemOpen} onOpenChange={setSystemOpen} />
    {!!data.errors.length && <p role="status" className="text-xs leading-5 text-[#687386]">Einige Bereiche konnten nicht vollständig geladen werden: {data.errors.map((key) => ({ market: "Markt", workspace: "Watchlist", data_quality: "Datenqualität", opportunities: "Tagesauswahl", portfolio: "Depot", sell: "Verkaufsmonitor", watchlist_assessments: "Watchlist-Bewertungen", industry_groups: "Branchen", earnings: "Earnings", changes: "Veränderungen" }[key] || "weitere Daten")).join(", ")}.</p>}
  </div>;
}

export function MarketOverview({ data }: { data: Pick<HomeData, "market"> }) {
  return <Panel icon={LineChart} title="Marktlage" detail={`${data.market.logic === "ibd" ? "IBD" : "Buchlogik"} · Phasen aus abgeschlossenen Tageskerzen`} action={<StatusChip tone={marketTone(data.market.phase)}>{data.market.phase_label || "Marktstand fehlt"}</StatusChip>}>
    <div className="grid gap-3 md:grid-cols-3">{data.market.indices.map((index) => <IndexCard key={index.ticker} index={index} />)}</div>
    <div className="mt-4 flex flex-wrap items-center justify-between gap-x-6 gap-y-2 border-t border-[#e3e8ef] pt-3 text-xs text-[#687386]">
      <p className="flex flex-wrap gap-x-5 gap-y-1"><span>Marktbreite: <b className="font-medium text-[#475569]">{number(data.market.breadth?.pct_above_50sma, 1)} %</b> über 50-SMA{data.market.breadth?.as_of && <> · {shortDate(data.market.breadth.as_of)}</>}</span><span>VIX: <b className="font-medium text-[#475569]">{number(data.market.volatility?.close, 1)}</b>{data.market.volatility?.as_of && <> · {shortDate(data.market.volatility.as_of)}</>}</span></p>
      <TextLink href="/market">Marktanalyse öffnen</TextLink>
    </div>
    {data.market.status !== "available" && <p className="mt-3 text-xs text-[#b7791f]">{data.market.summary || "Nicht alle Index-Ampeln sind aktuell verfügbar."}</p>}
  </Panel>;
}

function AttentionList({ data }: { data: HomeData }) {
  const [expanded, setExpanded] = useState(false);
  if (!data.priorities.length) return <Empty text={data.errors.includes("sell") ? "Der Verkaufsmonitor konnte nicht geladen werden. Bitte dort den aktuellen Stand prüfen." : "Keine gespeicherten Prüfpunkte oder relevanten Veränderungen."} />;
  const visible = expanded ? data.priorities : data.priorities.slice(0, 5);
  return <><div className="divide-y divide-[#e8edf2]">{visible.map((item) => <Link key={item.ticker} href={item.href} className="group grid gap-2 py-3 first:pt-0 sm:grid-cols-[110px_minmax(0,1fr)] sm:gap-4 focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#0f766e]">
    <div><b className="text-sm text-[#172033] group-hover:text-[#0f766e]">{item.ticker}</b><p className="mt-1 text-[11px] leading-4 text-[#687386]">{item.category}</p></div>
    <div><StatusChip tone={item.tone}>{item.label}</StatusChip><p className="mt-1.5 text-sm leading-5 text-[#687386]">{item.detail}</p></div>
  </Link>)}</div>
    {data.priorities.length > 5 && <button className="mt-3 inline-flex items-center gap-1 text-xs font-semibold text-[#0f766e]" type="button" aria-expanded={expanded} onClick={() => setExpanded(!expanded)}>{expanded ? "Weniger anzeigen" : `Weitere ${data.priorities.length - 5} Hinweise`}<ChevronDown size={14} className={expanded ? "rotate-180" : ""} /></button>}
    {expanded && data.priorities_total > data.priorities.length && <p className="mt-2 text-xs text-[#687386]">{data.priorities.length} von {data.priorities_total} Hinweisen angezeigt. <TextLink href="/sell-monitor">Verkaufsmonitor öffnen</TextLink></p>}
  </>;
}

function PortfolioOverview({ data }: { data: HomeData }) {
  const buys = useQuery({ queryKey: ["portfolio-buy-strength", 3], queryFn: () => api.portfolioBuyStrength({ weeks: 3 }), staleTime: 60_000, enabled: data.portfolio.positions_count > 0 });
  const snapshot = useQuery({ queryKey: ["portfolio-snapshot"], queryFn: api.portfolioSnapshot, refetchInterval: 60_000 });
  const dailyChange = snapshot.data?.kpis.find((item) => item.label === "Gewinn/Verlust zum Vortagsschluss");
  const p = data.portfolio;
  return <Panel icon={BriefcaseBusiness} title="Mein Depot" action={<TextLink href="/portfolio#positionen">Portfolio öffnen</TextLink>}>
    <dl className="grid grid-cols-3 gap-3">
      <DepotMetric label="Positionen" value={String(p.positions_count)} />
      <DepotMetric label="Stop-Abdeckung" value={p.stop_coverage_total ? `${number((p.stop_coverage_count || 0) / p.stop_coverage_total * 100)} %` : "–"} />
      <DepotMetric label="Zu prüfen" value={String(data.review_positions_count)} tone={data.review_positions_count ? "warning" : "neutral"} />
    </dl>
    <div className="mt-4">
      {dailyChange ? <KpiCard item={dailyChange} /> : <Empty text={snapshot.isLoading ? "Gewinn/Verlust zum Vortagsschluss wird geladen …" : "Gewinn/Verlust zum Vortagsschluss derzeit nicht verfügbar."} />}
    </div>
    <div className="mt-5 border-t border-[#e3e8ef] pt-4"><div className="mb-3 flex items-center justify-between gap-2"><h3 className="text-xs font-semibold text-[#475569]">Stärke nach Kauf · letzte 3 Wochen</h3><TextLink href="/portfolio/buy-strength">Alle Käufe</TextLink></div>
      {buys.isLoading ? <Empty text="Kaufentwicklung wird geladen …" /> : buys.isError ? <Empty text="Kaufentwicklung derzeit nicht verfügbar." /> : !buys.data?.items.length ? <Empty text="Keine frischen Käufe im aktuellen Fenster." /> : <div className="space-y-2">{buys.data.items.slice(0, 4).map((item) => <Link key={item.ticker} href={`/portfolio/buy-strength/${encodeURIComponent(item.ticker)}`} className="flex flex-wrap items-center justify-between gap-2 rounded-lg bg-[#f7f9fb] px-3 py-2.5 text-xs"><span><b className="text-[#172033]">{item.ticker}</b><span className="ml-2 text-[#687386]">{item.age_days} Tage · {signedPercent(item.pnl_pct, 1)}</span></span><StatusChip tone={item.status === "stark" ? "good" : item.status === "risk" ? "bad" : item.status === "watch" ? "warning" : "neutral"}>{item.status_label}</StatusChip></Link>)}</div>}
    </div>
  </Panel>;
}
function DepotMetric({ label, value, tone }: { label: string; value: string; tone?: Tone }) {
  return <div><dt className="text-[11px] text-[#687386]">{label}</dt><dd className={`mt-1 text-xl font-semibold tabular-nums ${tone === "warning" ? "text-[#b7791f]" : "text-[#172033]"}`}>{value}</dd></div>;
}
export function Opportunities({ data }: { data: Pick<HomeData, "opportunities"> }) {
  if (!data.opportunities.length) return <Empty text="Die Tagesauswahl ist noch nicht verfügbar." />;
  return <div className="divide-y divide-[#e8edf2]">{data.opportunities.map((row) => <Link key={row.ticker} href={`/stocks/${encodeURIComponent(row.ticker)}`} className="group flex gap-3 py-3 first:pt-0">
    <span className="grid size-7 shrink-0 place-items-center rounded-lg bg-[#e8f4f2] text-xs font-semibold text-[#0f766e]">{row.rank}</span>
    <div className="min-w-0 flex-1"><div className="flex items-start justify-between gap-3"><div><b className="text-sm text-[#172033] group-hover:text-[#0f766e]">{row.ticker}</b><span className="ml-2 text-xs text-[#687386]">{row.name}</span></div><span className="shrink-0 text-sm font-semibold tabular-nums text-[#0f766e]">{number(row.daily_opportunity_score, 1)}<span className="ml-1 text-[10px] font-normal text-[#687386]">Score</span></span></div><p className="mt-1 text-xs text-[#687386]">Qualität {number(row.quality_score)} · RS {number(row.rs_rating)}</p><p className="mt-1.5 text-xs leading-5 text-[#475569]">{row.reasons.find((reason) => !/^(Gesamtscore|Technischer Score|RS \d)/.test(reason)) || "Hohe Qualität und relative Stärke im gespeicherten Ranking."}</p></div>
  </Link>)}</div>;
}
export function Groups({ data }: { data: Pick<HomeData, "industry_groups" | "industry_groups_as_of"> }) {
  if (!data.industry_groups.length) return <Empty text="Noch keine Branchen-Rangliste verfügbar." />;
  return <><div className="divide-y divide-[#e8edf2]">{data.industry_groups.map((row) => <Link key={row.code} href={`/industry-groups/${row.code}`} className="flex items-center justify-between gap-3 py-2.5 first:pt-0 text-xs"><span className="min-w-0"><span className="mr-2 text-[#94a3b8]">{row.rank || "–"}</span><b className="font-medium text-[#172033]">{row.name}</b><span className="ml-2 text-[#687386]">RS {number(row.rs_score)}</span></span><span className={`shrink-0 tabular-nums ${row.rank_change_20d == null || row.rank_change_20d === 0 ? "text-[#94a3b8]" : row.rank_change_20d > 0 ? "text-[#138a57]" : "text-[#c2413b]"}`}>{row.rank_change_20d == null ? "–" : row.rank_change_20d === 0 ? "=" : `${row.rank_change_20d > 0 ? "↑" : "↓"} ${Math.abs(row.rank_change_20d)}`}</span></Link>)}</div><p className="mt-3 text-[11px] text-[#94a3b8]">Stand {shortDate(data.industry_groups_as_of)} · Rangänderung über 20 gespeicherte Stände</p></>;
}
function HomeLoading() {
  return <div className="space-y-5" aria-busy="true" aria-label="Startseite wird geladen"><div className="h-52 animate-pulse rounded-2xl bg-[#e9eef3]" /><div className="grid gap-5 xl:grid-cols-[1.4fr_1fr]">{[1, 2].map((item) => <div className="h-72 animate-pulse rounded-2xl bg-[#e9eef3]" key={item} />)}</div></div>;
}
