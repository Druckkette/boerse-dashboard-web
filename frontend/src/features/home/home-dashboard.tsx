"use client";

import { useQuery } from "@tanstack/react-query";
import {
  ArrowRight, ArrowUpRight, BriefcaseBusiness, CheckCircle2, CircleAlert,
  ExternalLink, Layers3, LineChart, ListChecks, TrendingUp
} from "lucide-react";
import Link from "next/link";
import { StatusChip } from "@/components/ui/status-chip";
import { api } from "@/lib/api/client";
import { formatPercent } from "@/lib/format";
import type { HomeDashboard as HomeData, Tone } from "@/lib/types/api";

const number = (value: number | null | undefined, digits = 0) =>
  value == null ? "–" : value.toLocaleString("de-DE", { maximumFractionDigits: digits, minimumFractionDigits: digits });
const today = () => new Date().toLocaleDateString("de-DE", { weekday: "long", day: "2-digit", month: "long", year: "numeric" });
const shortDate = (value?: string | null) => value ? new Date(`${value}T12:00:00`).toLocaleDateString("de-DE", { day: "2-digit", month: "2-digit" }) : "–";

export function HomeDashboard() {
  const query = useQuery({ queryKey: ["home-dashboard"], queryFn: api.home, staleTime: 60_000, refetchInterval: 60_000 });
  if (query.isLoading) return <HomeLoading />;
  if (query.error) return <div className="dashboard-section" role="alert">Die Startseite konnte gerade nicht geladen werden. Bitte später erneut versuchen.</div>;
  if (!query.data) return null;
  const data = query.data;
  const market = data.market.overview;
  const qualityTone: Tone = data.data_quality?.decision_status === "blocked" ? "bad" : data.data_quality?.decision_status === "limited" ? "warning" : "good";

  return (
    <div className="space-y-4">
      <header className="flex flex-col gap-3 border-b border-[#e3e8ef] pb-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-sm font-semibold text-[#0f766e]">Guten Morgen</p>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight text-[#172033]">Dein Börsen-Cockpit</h1>
          <p className="mt-1 text-sm text-[#687386]">{today()} <span className="mx-1.5 text-[#c4ccd6]">·</span> Datenstand: {data.as_of || "noch nicht verfügbar"}</p>
        </div>
        <Link href="/settings#data-quality" className="inline-flex items-center gap-2 self-start rounded-full border border-[#e3e8ef] bg-white px-3 py-1.5 text-xs font-semibold text-[#687386] transition hover:border-[#b7d9d3] hover:text-[#0f766e]">
          <span className={`size-2 rounded-full ${qualityTone === "good" ? "bg-[#138a57]" : qualityTone === "bad" ? "bg-[#c2413b]" : "bg-[#b7791f]"}`} />
          {data.data_quality?.summary || "Datenqualität prüfen"}<ExternalLink size={13} />
        </Link>
      </header>

      <div className="grid grid-cols-2 gap-2.5 xl:grid-cols-4">
        <SummaryCard href="/market" icon={LineChart} label="Markt" value={market?.phase_label || "Nicht verfügbar"} detail={market ? `${market.warning_count} Warnzeichen · Stand ${shortDate(data.as_of)}` : "Marktdaten fehlen"} tone={marketTone(market?.phase)} />
        <SummaryCard href="/stocks#top-daily" icon={TrendingUp} label="Top Aktien" value={data.opportunities.length ? `${data.opportunities.length} Kandidaten` : "–"} detail={data.opportunities.length ? "Tagesauswahl öffnen" : "Tagesauswahl fehlt"} tone={data.opportunities.length ? "good" : "neutral"} />
        <SummaryCard href="/portfolio#positionen" icon={BriefcaseBusiness} label="Depot" value={`${data.portfolio.positions_count} Positionen`} detail={portfolioDayDetail(data.portfolio)} tone={data.portfolio.daily_performance_pct == null ? "neutral" : data.portfolio.daily_performance_pct >= 0 ? "good" : "bad"} />
        <SummaryCard href="/sell-monitor" icon={ListChecks} label="Prüfen" value={`${data.priorities.length} Punkte`} detail="Zu den Titeln mit Handlungsbedarf" tone={data.priorities.length ? "warning" : "good"} />
      </div>

      <div className="grid items-start gap-4 xl:grid-cols-[1.14fr_0.86fr]">
        <Panel id="heute-wichtig" icon={CircleAlert} title="Heute wichtig" detail="Priorisiert nach Portfolio, Datenqualität, Earnings und relevanten Veränderungen."><PriorityList data={data} /></Panel>
        <Panel icon={LineChart} title="Markt heute" detail="Letzter abgeschlossener US-Handelstag."><MarketToday data={data} /></Panel>
      </div>

      <Panel icon={TrendingUp} title="Top Aktien" detail="Starke Aktien mit hoher Qualität und aktueller Dynamik – zur Recherche, nicht als Kaufempfehlung."><Opportunities data={data} /></Panel>
      <div className="grid items-start gap-4 xl:grid-cols-2">
        <Panel icon={ArrowUpRight} title="Seit dem letzten Handelstag" detail="Jede Änderung weist ihre Datenquelle aus."><Changes data={data} /></Panel>
        <Panel icon={BriefcaseBusiness} title="Mein Depot" detail="Auffällige Positionen aus dem gespeicherten Verkaufsmonitor."><Portfolio data={data} /></Panel>
      </div>
      <div className="grid items-start gap-4 xl:grid-cols-2">
        <Panel icon={Layers3} title="Stärkste Industry Groups" detail="Nur vorhandene Industry-Group-RS-Snapshots."><Groups data={data} /></Panel>
        <Panel icon={CheckCircle2} title="Meine Watchlist" detail="Der letzte gespeicherte Assessment-Snapshot je beobachteter Aktie."><Watchlist data={data} /></Panel>
      </div>
      {data.errors.length ? <p className="text-xs text-[#8a94a6]">Einzelne Bereiche sind derzeit nicht verfügbar: {data.errors.join(", ")}.</p> : null}
    </div>
  );
}

function SummaryCard({ href, icon: Icon, label, value, detail, tone }: { href: string; icon: typeof LineChart; label: string; value: string; detail: string; tone: Tone }) {
  const accent = tone === "good" ? "#138a57" : tone === "bad" ? "#c2413b" : tone === "warning" ? "#b7791f" : "#2563eb";
  return <Link href={href} className="group rounded-[12px] border border-[#e3e8ef] border-t-[3px] bg-white p-3.5 shadow-[0_4px_14px_rgba(15,23,42,0.04)] transition hover:-translate-y-0.5 hover:border-[#b7d9d3] hover:shadow-[0_10px_24px_rgba(15,23,42,0.08)]" style={{ borderTopColor: accent }}>
    <div className="flex items-center justify-between"><span className="text-[10px] font-semibold uppercase tracking-[0.1em] text-[#687386]">{label}</span><Icon size={15} style={{ color: accent }} /></div>
    <div className="mt-2 truncate text-lg font-semibold text-[#172033]">{value}</div>
    <div className="mt-1 flex items-center justify-between gap-2 text-xs leading-5 text-[#687386]"><span className="line-clamp-1">{detail}</span><ArrowRight size={13} className="shrink-0 opacity-0 transition group-hover:opacity-100" /></div>
  </Link>;
}

function Panel({ id, icon: Icon, title, detail, children }: { id?: string; icon: typeof CircleAlert; title: string; detail: string; children: React.ReactNode }) {
  return <section id={id} className="dashboard-section scroll-mt-24"><div className="mb-3 flex items-start gap-2.5"><span className="grid size-8 shrink-0 place-items-center rounded-[9px] bg-[#e8f4f2] text-[#0f766e]"><Icon size={16} /></span><div><h2 className="text-sm font-semibold text-[#172033]">{title}</h2><p className="mt-0.5 text-xs leading-5 text-[#687386]">{detail}</p></div></div>{children}</section>;
}

function PriorityList({ data }: { data: HomeData }) {
  if (!data.priorities.length) return <Empty text="Heute gibt es keine dringenden Punkte." />;
  return <div className="divide-y divide-[#e8edf2]">{data.priorities.map((item, index) => <Link key={`${item.ticker}-${item.label}-${index}`} href={item.href} className="grid gap-1.5 py-3 first:pt-0 last:pb-0 transition hover:bg-[#f8fbfb] sm:grid-cols-[108px_1fr_auto] sm:items-center sm:gap-3 sm:px-2"><div><div className="font-semibold text-[#172033]">{item.ticker}</div><div className="mt-0.5 text-[11px] font-medium text-[#0f766e]">{item.category}</div></div><div><StatusChip tone={item.tone}>{item.label}</StatusChip><p className="mt-1 text-sm leading-5 text-[#687386]">{item.detail || "Details im Zielbereich prüfen."}</p></div><ArrowUpRight className="hidden size-4 text-[#8b95a5] sm:block" /></Link>)}</div>;
}

function MarketToday({ data }: { data: HomeData }) {
  const sp = data.market.overview?.trend_ampel;
  const nasdaq = data.market.nasdaq?.trend_ampel;
  const breadth = data.market.breadth;
  const vix = data.market.volatility;
  return <><div className="grid grid-cols-2 gap-2"><MarketMetric label="Marktphase" value={data.market.overview?.phase_label || "–"} /><MarketMetric label="S&P 500" value={sp?.close == null ? "–" : number(sp.close, 2)} detail={sp?.as_of ? `Schlusskurs ${shortDate(sp.as_of)}` : undefined} /><MarketMetric label="Nasdaq" value={nasdaq?.close == null ? "–" : number(nasdaq.close, 2)} detail={nasdaq?.as_of ? `Schlusskurs ${shortDate(nasdaq.as_of)}` : undefined} /><MarketMetric label="Marktbreite" value={breadth?.pct_above_50sma == null ? "–" : `${number(breadth.pct_above_50sma, 1)} %`} detail="über 50 SMA" /><MarketMetric label="VIX" value={vix?.vix_close == null ? "–" : number(vix.vix_close, 1)} detail={vix?.date ? `Schlusskurs ${shortDate(vix.date)}` : undefined} /><MarketMetric label="Warnzeichen" value={data.market.overview ? String(data.market.overview.warning_count) : "–"} detail="im Markt-Snapshot" /></div><Link className="mt-3 inline-flex items-center gap-1 text-sm font-semibold text-[#0f766e]" href="/market">Marktanalyse öffnen <ArrowRight size={14} /></Link></>;
}

function Opportunities({ data }: { data: HomeData }) {
  if (!data.opportunities.length) return <Empty text="Die Tagesauswahl wird nach dem nächsten Aktienranking verfügbar." />;
  return <div className="grid gap-2 md:grid-cols-3">{data.opportunities.map((row) => <Link key={row.ticker} href={`/stocks/${row.ticker}`} className="rounded-[10px] border border-[#e3e8ef] bg-[#fbfcfe] p-3 transition hover:border-[#b7d9d3] hover:bg-[#f7fbfa]"><div className="flex justify-between gap-2"><div><div className="text-xs font-semibold text-[#0f766e]">#{row.rank}</div><div className="mt-1 font-semibold text-[#172033]">{row.ticker}</div><div className="text-xs text-[#687386]">{row.name}</div></div><div className="text-right"><div className="text-xl font-semibold text-[#0f766e]">{number(row.daily_opportunity_score, 1)}</div><div className="text-[11px] text-[#687386]">Daily Score</div></div></div><div className="mt-3 text-xs text-[#687386]">Qualität {number(row.quality_score)} · RS {number(row.rs_rating)}</div><div className="mt-2 line-clamp-2 text-xs leading-5 text-[#475569]">{row.reasons.slice(0, 2).join(" · ") || "Keine Begründung gespeichert"}</div></Link>)}</div>;
}

function Changes({ data }: { data: HomeData }) {
  if (!data.changes.length) return <Empty text="Keine neuen Veränderungen im gespeicherten Vergleich." />;
  return <div className="space-y-1.5">{data.changes.map((row, index) => <Link key={`${row.ticker}-${index}`} href={row.href} className="flex items-center gap-3 rounded-[9px] bg-[#f7f9fb] px-3 py-2.5 transition hover:bg-[#eef7f5]"><span className="min-w-12 font-semibold text-[#172033]">{row.ticker}</span><span className="min-w-0 flex-1 text-sm text-[#687386]">{row.detail}</span><span className="hidden rounded-full bg-white px-2 py-0.5 text-[11px] font-semibold text-[#0f766e] sm:inline">{row.source}</span></Link>)}</div>;
}

function Portfolio({ data }: { data: HomeData }) {
  const alerts = data.sell_rows.filter((row) => row.status !== "Halten" || row.data_quality_status !== "trusted").slice(0, 5);
  const rows = alerts.length ? alerts : data.portfolio.positions.slice(0, 5);
  return <><div className="grid grid-cols-2 gap-2"><MarketMetric label="Positionen" value={String(data.portfolio.positions_count)} /><MarketMetric label="Stop-Abdeckung" value={data.portfolio.stop_coverage_total ? `${number((data.portfolio.stop_coverage_count || 0) / data.portfolio.stop_coverage_total * 100)} %` : "–"} /></div><div className="mt-3 space-y-1.5">{rows.map((row) => <Link key={row.ticker} href={`/sell-monitor/${row.ticker}`} className="flex items-center justify-between gap-3 rounded-[9px] bg-[#f7f9fb] px-3 py-2.5 transition hover:bg-[#fff8e6]"><span className="min-w-0"><b className="text-[#172033]">{row.ticker}</b>{"primary_signal" in row && row.primary_signal ? <span className="ml-2 text-xs text-[#687386]">{row.primary_signal}</span> : "pnl_pct" in row ? <span className="ml-2 text-xs text-[#687386]">{formatPercent(row.pnl_pct)}</span> : null}</span>{"status" in row ? <StatusChip tone={row.status === "Verkaufen" || row.data_quality_status === "blocked" ? "bad" : "warning"}>{row.data_quality_status === "blocked" ? "Daten prüfen" : row.status}</StatusChip> : null}</Link>)}</div><Link className="mt-3 inline-flex items-center gap-1 text-sm font-semibold text-[#0f766e]" href="/portfolio#positionen">Alle Positionen öffnen <ArrowRight size={14} /></Link></>;
}

function Groups({ data }: { data: HomeData }) { return data.industry_groups.length ? <div className="space-y-1.5">{data.industry_groups.map((row) => <Link key={row.code} href={`/industry-groups/${row.code}`} className="flex items-center justify-between gap-2 rounded-[9px] bg-[#f7f9fb] px-3 py-2 transition hover:bg-[#eef7f5]"><span><b className="text-[#172033]">#{row.rank || "–"} {row.name}</b><span className="ml-2 text-xs text-[#687386]">RS {number(row.rs_score, 0)}</span></span><span className="text-xs font-semibold text-[#138a57]">{row.rank_change_20d == null ? "" : `${row.rank_change_20d > 0 ? "↑" : "↓"} ${Math.abs(row.rank_change_20d)}`}</span></Link>)}</div> : <Empty text="Noch keine Industry-Group-Rangliste verfügbar." />; }
function Watchlist({ data }: { data: HomeData }) { return data.watchlist.length ? <div className="space-y-1.5">{data.watchlist.map((row) => <Link key={row.ticker} href={`/stocks/${row.ticker}`} className="flex items-center justify-between gap-2 rounded-[9px] bg-[#f7f9fb] px-3 py-2 transition hover:bg-[#eef7f5]"><span><b className="text-[#172033]">{row.ticker}</b><span className="ml-2 text-xs text-[#687386]">Score {row.overall_score}</span></span><StatusChip tone={row.warnings_count ? "warning" : "good"}>{row.top_warning || "Snapshot vorhanden"}</StatusChip></Link>)}</div> : <Empty text="Noch keine Watchlist oder keine gespeicherten Assessment-Snapshots." />; }
function MarketMetric({ label, value, detail }: { label: string; value: string; detail?: string }) { return <div className="rounded-[9px] bg-[#f7f9fb] px-3 py-2.5"><div className="text-xs text-[#687386]">{label}</div><div className="mt-0.5 font-semibold tabular-nums text-[#172033]">{value}</div>{detail ? <div className="mt-0.5 text-[11px] text-[#8a94a6]">{detail}</div> : null}</div>; }
function Empty({ text }: { text: string }) { return <div className="rounded-[9px] border border-dashed border-[#d8e1ea] bg-[#fafcfd] px-3 py-3 text-sm text-[#687386]">{text}</div>; }
function HomeLoading() { return <div className="space-y-4" aria-busy="true"><div className="h-20 animate-pulse rounded-[12px] bg-[#e9eef3]" /><div className="grid grid-cols-2 gap-2.5 xl:grid-cols-4">{[1, 2, 3, 4].map((item) => <div className="h-24 animate-pulse rounded-[12px] bg-[#e9eef3]" key={item} />)}</div><div className="grid gap-4 xl:grid-cols-2">{[1, 2].map((item) => <div className="h-52 animate-pulse rounded-[14px] bg-[#e9eef3]" key={item} />)}</div></div>; }
function portfolioDayDetail(portfolio: HomeData["portfolio"]) { if (portfolio.daily_performance_pct == null) return "Vortagsvergleich nicht verfügbar"; const dateLabel = shortDate(portfolio.daily_performance_as_of); return `${portfolio.daily_performance_pct >= 0 ? "+" : ""}${number(portfolio.daily_performance_pct, 2)} % ggü. Vortag · ${dateLabel}`; }
function marketTone(phase?: string): Tone { return phase === "aufwaertstrend" || phase === "gruen" ? "good" : phase === "rot" ? "bad" : phase ? "warning" : "neutral"; }
