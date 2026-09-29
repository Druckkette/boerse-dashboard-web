"use client";

import { useQuery } from "@tanstack/react-query";
import {
  ArrowRight, ArrowUpRight, BriefcaseBusiness, CheckCircle2, ChevronDown,
  CircleAlert, Clock3, ExternalLink, Layers3, LineChart, ListChecks, TrendingUp
} from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { StatusChip } from "@/components/ui/status-chip";
import { api } from "@/lib/api/client";
import { formatPercent } from "@/lib/format";
import type { HomeDashboard as HomeData, Tone } from "@/lib/types/api";

const number = (value: number | null | undefined, digits = 0) =>
  value == null ? "–" : value.toLocaleString("de-DE", { maximumFractionDigits: digits, minimumFractionDigits: digits });
const shortDate = (value?: string | null) => value
  ? new Date(`${value}T12:00:00`).toLocaleDateString("de-DE", { day: "2-digit", month: "2-digit" }) : "–";
const longDate = (value: Date) => new Intl.DateTimeFormat("de-DE", {
  timeZone: "Europe/Berlin", weekday: "long", day: "2-digit", month: "long", year: "numeric"
}).format(value);
const signedPercent = (value: number | null | undefined, digits = 2) => value == null
  ? "–" : `${value >= 0 ? "+" : ""}${number(value, digits)} %`;

export function HomeDashboard() {
  const query = useQuery({ queryKey: ["home-dashboard"], queryFn: api.home, staleTime: 60_000, refetchInterval: 60_000 });
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 60_000);
    return () => window.clearInterval(timer);
  }, []);
  if (query.isLoading) return <HomeLoading />;
  if (query.error) return <div className="dashboard-section" role="alert">Die Startseite konnte gerade nicht geladen werden. Bitte später erneut versuchen.</div>;
  if (!query.data) return null;
  const data = query.data;
  const qualityTone: Tone = data.data_quality?.decision_status === "blocked" ? "bad" : data.data_quality?.decision_status === "limited" ? "warning" : "good";
  const portfolioTone: Tone = data.portfolio.daily_price_change_status !== "available" ? "neutral" : (data.portfolio.daily_price_change_pct ?? 0) >= 0 ? "good" : "bad";

  return (
    <div className="space-y-4">
      <header className="flex flex-col gap-3 border-b border-[#e3e8ef] pb-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-sm font-semibold text-[#0f766e]">{greeting(now)}</p>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight text-[#172033]">Dein Börsen-Cockpit</h1>
          <p className="mt-1 flex flex-wrap items-center gap-x-1.5 gap-y-1 text-sm text-[#687386]">
            <span>{longDate(now)}</span><span className="text-[#c4ccd6]">·</span><MarketSessionStatus data={data} />
          </p>
        </div>
        <Link href="/settings#data-quality" className="inline-flex items-center gap-2 self-start rounded-full border border-[#e3e8ef] bg-white px-3 py-1.5 text-xs font-semibold text-[#687386] transition hover:border-[#b7d9d3] hover:text-[#0f766e] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#0f766e]">
          <span className={`size-2 rounded-full ${qualityTone === "good" ? "bg-[#138a57]" : qualityTone === "bad" ? "bg-[#c2413b]" : "bg-[#b7791f]"}`} />
          {data.data_quality?.summary || "Datenqualität prüfen"}<ExternalLink size={13} />
        </Link>
      </header>

      <div className="grid grid-cols-2 gap-2.5 xl:grid-cols-4">
        <SummaryCard href="/market" icon={LineChart} label="Markt" value={data.market.phase_label || "Nicht verfügbar"} detail={marketCardDetail(data)} tone={marketTone(data.market.phase)} />
        <SummaryCard href="/stocks#top-daily" icon={TrendingUp} label="Top Aktien" value={data.opportunities.length ? `${data.opportunities.length} Kandidaten` : "–"} detail={data.opportunities.length ? "Tagesauswahl öffnen" : "Tagesauswahl fehlt"} tone={data.opportunities.length ? "good" : "neutral"} />
        <SummaryCard href="/portfolio#positionen" icon={BriefcaseBusiness} label="Depot" value={`${data.portfolio.positions_count} Positionen`} detail={portfolioDayDetail(data.portfolio)} tone={portfolioTone} />
        <SummaryCard href="/sell-monitor" icon={ListChecks} label="Prüfen" value={`${data.review_positions_count} Positionen`} detail="Zu den Titeln mit Handlungsbedarf" tone={data.review_positions_count ? "warning" : "good"} />
      </div>

      <div className="grid items-start gap-4 xl:grid-cols-[1.14fr_0.86fr]">
        <Panel id="heute-wichtig" icon={CircleAlert} title="Heute wichtig" detail="Portfolio, Datenqualität, Earnings und relevante Veränderungen in dieser Reihenfolge."><PriorityList data={data} /></Panel>
        <Panel icon={LineChart} title="Markt heute" detail={marketPanelDetail(data)}><MarketToday data={data} /></Panel>
      </div>

      <Panel icon={TrendingUp} title="Top Aktien" detail="Starke Aktien mit hoher Qualität und aktueller Dynamik – zur Recherche, nicht als Kaufempfehlung."><Opportunities data={data} /></Panel>
      <div className="grid items-start gap-4 xl:grid-cols-2">
        <Panel icon={ArrowUpRight} title="Seit dem letzten Handelstag" detail={changesPanelDetail(data)}><Changes data={data} /></Panel>
        <Panel icon={BriefcaseBusiness} title="Mein Depot" detail="Auffällige Positionen aus dem gespeicherten Verkaufsmonitor."><Portfolio data={data} /></Panel>
      </div>
      <div className="grid items-start gap-4 xl:grid-cols-2">
        <Panel icon={Layers3} title="Stärkste Industry Groups" detail={data.industry_groups_as_of ? `Rangliste vom ${shortDate(data.industry_groups_as_of)} · Veränderung über 20 gespeicherte Stände.` : "Noch keine Rangliste verfügbar."}><Groups data={data} /></Panel>
        <Panel icon={CheckCircle2} title="Meine Watchlist" detail="Gespeicherte Ticker mit ihrem zuletzt verfügbaren Assessment."><Watchlist data={data} /></Panel>
      </div>
      {data.errors.length ? <p className="text-xs text-[#8a94a6]">Einzelne Bereiche sind derzeit nicht verfügbar: {data.errors.join(", ")}.</p> : null}
    </div>
  );
}

function SummaryCard({ href, icon: Icon, label, value, detail, tone }: { href: string; icon: typeof LineChart; label: string; value: string; detail: string; tone: Tone }) {
  const accent = tone === "good" ? "#138a57" : tone === "bad" ? "#c2413b" : tone === "warning" ? "#b7791f" : "#2563eb";
  return <Link href={href} className="group rounded-[12px] border border-[#e3e8ef] border-t-[3px] bg-white p-3.5 shadow-[0_4px_14px_rgba(15,23,42,0.04)] transition hover:-translate-y-0.5 hover:border-[#b7d9d3] hover:shadow-[0_10px_24px_rgba(15,23,42,0.08)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#0f766e]" style={{ borderTopColor: accent }}>
    <div className="flex items-center justify-between"><span className="text-[10px] font-semibold uppercase tracking-[0.1em] text-[#687386]">{label}</span><Icon size={15} style={{ color: accent }} /></div>
    <div className="mt-2 truncate text-lg font-semibold text-[#172033]">{value}</div>
    <div className="mt-1 flex items-center justify-between gap-2 text-xs leading-5 text-[#687386]"><span className="line-clamp-2">{detail}</span><ArrowRight size={13} className="shrink-0 opacity-0 transition group-hover:opacity-100" /></div>
  </Link>;
}

function Panel({ id, icon: Icon, title, detail, children }: { id?: string; icon: typeof CircleAlert; title: string; detail: string; children: React.ReactNode }) {
  return <section id={id} className="dashboard-section scroll-mt-24"><div className="mb-3 flex items-start gap-2.5"><span className="grid size-8 shrink-0 place-items-center rounded-[9px] bg-[#e8f4f2] text-[#0f766e]"><Icon size={16} /></span><div><h2 className="text-sm font-semibold text-[#172033]">{title}</h2><p className="mt-0.5 text-xs leading-5 text-[#687386]">{detail}</p></div></div>{children}</section>;
}

function MarketSessionStatus({ data }: { data: HomeData }) {
  const session = data.market.session;
  if (session?.phase === "open") return <><Clock3 size={14} className="text-[#0f766e]" /><span>US-Handel läuft · letzter Schlusskurs {shortDate(session.last_completed_as_of)}</span></>;
  if (session?.last_completed_as_of) return <span>Letzter abgeschlossener US-Handelstag: {shortDate(session.last_completed_as_of)}</span>;
  return <span>Marktdaten noch nicht verfügbar</span>;
}

function PriorityList({ data }: { data: HomeData }) {
  const [expanded, setExpanded] = useState(false);
  if (!data.priorities.length) return <Empty text="Heute gibt es keine dringenden Punkte." />;
  const visible = expanded ? data.priorities : data.priorities.slice(0, 5);
  const more = data.priorities_total - visible.length;
  return <div className="divide-y divide-[#e8edf2]">{visible.map((item, index) => <Link key={`${item.ticker}-${item.label}-${index}`} href={item.href} className="grid gap-1.5 py-3 first:pt-0 transition hover:bg-[#f8fbfb] sm:grid-cols-[130px_1fr_auto] sm:items-center sm:gap-3 sm:px-2 focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#0f766e]"><div><div className="font-semibold text-[#172033]">{item.ticker}</div><div className="mt-0.5 text-[11px] font-medium text-[#0f766e]">{item.category}</div></div><div><StatusChip tone={item.tone}>{item.label}</StatusChip><p className="mt-1 text-sm leading-5 text-[#687386]">{item.detail}</p></div><ArrowUpRight className="hidden size-4 text-[#8b95a5] sm:block" /></Link>)}{more > 0 ? <button className="mt-2 inline-flex items-center gap-1 text-sm font-semibold text-[#0f766e]" type="button" onClick={() => setExpanded(true)}>Weitere {more} Hinweise anzeigen <ChevronDown size={14} /></button> : null}</div>;
}

function MarketToday({ data }: { data: HomeData }) {
  const sp = data.market.indices.find((index) => index.ticker === "^GSPC");
  const nasdaq = data.market.indices.find((index) => index.ticker === "^IXIC");
  const breadth = data.market.breadth;
  const vix = data.market.volatility;
  return <><div className="grid grid-cols-2 gap-2"><MarketMetric label="Marktphase" value={data.market.phase_label || "–"} /><IndexMetric index={sp} /><IndexMetric index={nasdaq} /><MarketMetric label="Marktbreite" value={breadth?.pct_above_50sma == null ? "–" : `${number(breadth.pct_above_50sma, 1)} %`} detail={breadth?.as_of ? `über 50 SMA · ${shortDate(breadth.as_of)}` : "über 50 SMA"} /><MarketMetric label="VIX" value={vix?.close == null ? "–" : number(vix.close, 1)} detail={vix?.as_of ? `Schlusskurs ${shortDate(vix.as_of)}` : undefined} /><MarketMetric label="Warnzeichen" value={data.market.warning_count == null ? "–" : String(data.market.warning_count)} detail="im aktuellen Marktstatus" /></div><Link className="mt-3 inline-flex items-center gap-1 text-sm font-semibold text-[#0f766e]" href="/market">Marktanalyse öffnen <ArrowRight size={14} /></Link></>;
}

function IndexMetric({ index }: { index?: HomeData["market"]["indices"][number] }) {
  if (!index) return <MarketMetric label="Index" value="–" detail="Daten fehlen" />;
  const statusDetail = index.status === "stale" ? `Stand ${shortDate(index.as_of)} · Aktualisierung ausstehend` : index.status === "partial" ? "Vorheriger Schlusskurs fehlt" : index.status === "missing" ? "Daten fehlen" : `Schlusskurs ${number(index.close, 2)} · ${shortDate(index.as_of)}`;
  return <MarketMetric label={index.label} value={index.change_pct == null ? "–" : signedPercent(index.change_pct)} detail={statusDetail} tone={index.change_pct == null ? "neutral" : index.change_pct >= 0 ? "good" : "bad"} />;
}

function Opportunities({ data }: { data: HomeData }) {
  if (!data.opportunities.length) return <Empty text="Die Tagesauswahl wird nach dem nächsten Aktienranking verfügbar." />;
  return <div className="grid gap-2 md:grid-cols-3">{data.opportunities.map((row) => <Link key={row.ticker} href={`/stocks/${row.ticker}`} className="rounded-[10px] border border-[#e3e8ef] bg-[#fbfcfe] p-3 transition hover:border-[#b7d9d3] hover:bg-[#f7fbfa] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#0f766e]"><div className="flex justify-between gap-2"><div><div className="text-xs font-semibold text-[#0f766e]">#{row.rank}</div><div className="mt-1 font-semibold text-[#172033]">{row.ticker}</div><div className="line-clamp-1 text-xs text-[#687386]">{row.name}</div></div><div className="text-right"><div className="text-xl font-semibold text-[#0f766e]">{number(row.daily_opportunity_score, 1)}</div><div className="text-[11px] text-[#687386]">Daily Score</div></div></div><div className="mt-3 text-xs text-[#687386]">Qualität {number(row.quality_score)} · RS {number(row.rs_rating)}</div><div className="mt-2 line-clamp-2 text-xs leading-5 text-[#475569]">{researchReason(row)}</div></Link>)}</div>;
}

function Changes({ data }: { data: HomeData }) {
  if (!data.changes.length) return <Empty text="Für gespeicherte Vergleiche gibt es keine relevanten Änderungen." />;
  return <div className="space-y-1.5">{data.changes.map((row) => <Link key={row.ticker} href={row.href} className="block rounded-[9px] bg-[#f7f9fb] px-3 py-2.5 transition hover:bg-[#eef7f5] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#0f766e]"><div className="flex flex-wrap items-center gap-2"><b className="text-[#172033]">{row.ticker}</b>{row.scopes.map((scope) => <ScopeChip key={scope} scope={scope} />)}</div><p className="mt-1 text-sm leading-5 text-[#687386]">{row.summary}</p></Link>)}</div>;
}

function Portfolio({ data }: { data: HomeData }) {
  const alerts = data.sell_rows.filter((row) => row.status !== "Halten" || row.data_quality_status !== "trusted");
  const rows = alerts.length ? alerts.slice(0, 5) : data.portfolio.positions.slice(0, 5);
  return <><div className="grid grid-cols-3 gap-2"><MarketMetric label="Positionen" value={String(data.portfolio.positions_count)} /><MarketMetric label="Stop-Abdeckung" value={data.portfolio.stop_coverage_total ? `${number((data.portfolio.stop_coverage_count || 0) / data.portfolio.stop_coverage_total * 100)} %` : "–"} /><MarketMetric label="Prüfen" value={String(data.review_positions_count)} /></div><div className="mt-3 space-y-1.5">{rows.map((row) => <Link key={row.ticker} href={`/sell-monitor/${row.ticker}`} className="flex items-center justify-between gap-3 rounded-[9px] bg-[#f7f9fb] px-3 py-2.5 transition hover:bg-[#fff8e6] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#0f766e]"><span className="min-w-0"><b className="text-[#172033]">{row.ticker}</b>{"primary_signal" in row && row.primary_signal ? <span className="ml-2 text-xs text-[#687386]">{row.primary_signal}</span> : "pnl_pct" in row ? <span className="ml-2 text-xs text-[#687386]">{formatPercent(row.pnl_pct)}</span> : null}</span>{"status" in row ? <StatusChip tone={row.status === "Verkaufen" || row.data_quality_status === "blocked" ? "bad" : "warning"}>{row.data_quality_status === "blocked" ? "Daten prüfen" : row.status}</StatusChip> : null}</Link>)}</div>{data.review_positions_count > rows.length ? <p className="mt-2 text-xs text-[#687386]">{rows.length} von {data.review_positions_count} Positionen mit Handlungsbedarf angezeigt.</p> : null}<Link className="mt-3 inline-flex items-center gap-1 text-sm font-semibold text-[#0f766e]" href="/portfolio#positionen">Alle Positionen öffnen <ArrowRight size={14} /></Link></>;
}

function Groups({ data }: { data: HomeData }) {
  return data.industry_groups.length ? <div className="space-y-1.5">{data.industry_groups.map((row) => <Link key={row.code} href={`/industry-groups/${row.code}`} className="flex items-center justify-between gap-2 rounded-[9px] bg-[#f7f9fb] px-3 py-2 transition hover:bg-[#eef7f5] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#0f766e]"><span className="min-w-0"><b className="text-[#172033]">#{row.rank || "–"} {row.name}</b><span className="ml-2 text-xs text-[#687386]">RS {number(row.rs_score, 0)}</span></span><span className="shrink-0 text-xs font-semibold text-[#138a57]">{rankChange(row.rank_change_20d)}</span></Link>)}</div> : <Empty text="Noch keine Industry-Group-Rangliste verfügbar." />;
}

function Watchlist({ data }: { data: HomeData }) {
  if (!data.watchlist_total) return <Empty text="Noch keine Watchlist gespeichert." />;
  return <><div className="space-y-1.5">{data.watchlist.map((row) => <Link key={row.ticker} href={`/stocks/${row.ticker}`} className="flex items-center justify-between gap-2 rounded-[9px] bg-[#f7f9fb] px-3 py-2 transition hover:bg-[#eef7f5] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#0f766e]"><span className="min-w-0"><b className="text-[#172033]">{row.ticker}</b>{row.data_status === "available" ? <span className="ml-2 text-xs text-[#687386]">Score {row.overall_score}</span> : <span className="ml-2 text-xs text-[#687386]">Assessment fehlt</span>}</span><StatusChip tone={row.data_status === "error" ? "bad" : row.data_status === "missing" || row.warnings_count ? "warning" : "good"}>{row.data_status === "error" ? "Daten prüfen" : row.data_status === "missing" ? "Noch nicht bewertet" : row.top_warning || "Aktuell"}</StatusChip></Link>)}</div>{data.watchlist_total > data.watchlist.length ? <p className="mt-2 text-xs text-[#687386]">{data.watchlist.length} von {data.watchlist_total} Watchlist-Aktien angezeigt.</p> : null}<Link className="mt-3 inline-flex items-center gap-1 text-sm font-semibold text-[#0f766e]" href="/workspace">Watchlist verwalten <ArrowRight size={14} /></Link></>;
}

function MarketMetric({ label, value, detail, tone = "neutral" }: { label: string; value: string; detail?: string; tone?: Tone }) {
  const valueClass = tone === "good" ? "text-[#138a57]" : tone === "bad" ? "text-[#c2413b]" : tone === "warning" ? "text-[#b7791f]" : "text-[#172033]";
  return <div className="rounded-[9px] bg-[#f7f9fb] px-3 py-2.5"><div className="text-xs text-[#687386]">{label}</div><div className={`mt-0.5 font-semibold tabular-nums ${valueClass}`}>{value}</div>{detail ? <div className="mt-0.5 text-[11px] leading-4 text-[#8a94a6]">{detail}</div> : null}</div>;
}

function ScopeChip({ scope }: { scope: HomeData["changes"][number]["scopes"][number] }) {
  return <span className="rounded-full bg-white px-2 py-0.5 text-[11px] font-semibold text-[#0f766e]">{scope === "portfolio" ? "Depot" : scope === "watchlist" ? "Watchlist" : "Top Aktien"}</span>;
}

function Empty({ text }: { text: string }) { return <div className="rounded-[9px] border border-dashed border-[#d8e1ea] bg-[#fafcfd] px-3 py-3 text-sm text-[#687386]">{text}</div>; }
function HomeLoading() { return <div className="space-y-4" aria-busy="true"><div className="h-20 animate-pulse rounded-[12px] bg-[#e9eef3]" /><div className="grid grid-cols-2 gap-2.5 xl:grid-cols-4">{[1, 2, 3, 4].map((item) => <div className="h-24 animate-pulse rounded-[12px] bg-[#e9eef3]" key={item} />)}</div><div className="grid gap-4 xl:grid-cols-2">{[1, 2].map((item) => <div className="h-52 animate-pulse rounded-[14px] bg-[#e9eef3]" key={item} />)}</div></div>; }
function greeting(now: Date) { const hour = Number(new Intl.DateTimeFormat("en-GB", { timeZone: "Europe/Berlin", hour: "2-digit", hourCycle: "h23" }).format(now)); return hour < 12 ? "Guten Morgen" : hour < 18 ? "Guten Tag" : "Guten Abend"; }
function marketCardDetail(data: HomeData) { const asOf = data.market.session?.last_completed_as_of; return data.market.warning_count == null ? "Marktdaten fehlen" : `${data.market.warning_count} Warnzeichen · letzter Schluss ${shortDate(asOf)}`; }
function marketPanelDetail(data: HomeData) { return data.market.session?.phase === "open" ? `US-Handel läuft · Schlusskurse vom ${shortDate(data.market.session.last_completed_as_of)}.` : `Letzter abgeschlossener US-Handelstag: ${shortDate(data.market.session?.last_completed_as_of)}.`; }
function changesPanelDetail(data: HomeData) { const row = data.changes[0]; return row?.as_of && row.previous_as_of ? `Vergleich ${shortDate(row.as_of)} mit ${shortDate(row.previous_as_of)}. Jede Aktie erscheint einmal.` : "Nur Änderungen mit gespeicherter Vergleichsbasis."; }
function researchReason(row: HomeData["opportunities"][number]) { return row.reasons.find((reason) => !/^(Gesamtscore|Technischer Score|RS \d)/.test(reason)) || "Hohe Qualität und relative Stärke im gespeicherten Ranking."; }
function rankChange(value: number | null | undefined) { if (value == null) return "–"; if (value === 0) return "unverändert"; return `${value > 0 ? "↑" : "↓"} ${Math.abs(value)}`; }
function portfolioDayDetail(portfolio: HomeData["portfolio"]) { if (portfolio.daily_price_change_status === "mixed_currency") return "Kursveränderung nicht summiert: mehrere Währungen"; if (portfolio.daily_price_change_status === "partial") return `Kursvergleich nur für ${portfolio.comparable_positions || 0}/${portfolio.positions_count} Positionen verfügbar`; if (portfolio.daily_price_change_pct == null) return "Kursveränderung zum Vortag nicht verfügbar"; return `${signedPercent(portfolio.daily_price_change_pct)} Kursveränderung · ${portfolio.comparable_positions}/${portfolio.positions_count} Positionen · ${shortDate(portfolio.daily_price_change_as_of)}`; }
function marketTone(phase?: string | null): Tone { return phase === "aufwaertstrend" || phase === "gruen" ? "good" : phase === "rot" ? "bad" : phase ? "warning" : "neutral"; }
