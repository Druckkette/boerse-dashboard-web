"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BellRing, BookmarkPlus, ChevronDown, Clock3, Plus, ShieldCheck, Trash2 } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { StatusChip } from "@/components/ui/status-chip";
import { api } from "@/lib/api/client";
import { formatDateTime } from "@/lib/format";
import type { HomeDashboard, WorkspaceState } from "@/lib/types/api";
import { Empty, Panel, TextLink } from "./home-ui";

export function HomeWatchlist({ data }: { data: HomeDashboard }) {
  const queryClient = useQueryClient();
  const workspace = useQuery({ queryKey: ["workspace"], queryFn: api.workspace, staleTime: 30_000 });
  const [input, setInput] = useState("");
  const [expanded, setExpanded] = useState(false);
  const saved = async (state: WorkspaceState) => {
    queryClient.setQueryData(["workspace"], state);
    await queryClient.invalidateQueries({ queryKey: ["home-dashboard"] });
  };
  async function persist(action: (ticker: string) => Promise<WorkspaceState>, ticker: string) {
    const state = await action(ticker);
    if (state.source !== "database") throw new Error("Watchlist nicht gespeichert");
    return state;
  }
  const add = useMutation({ mutationFn: (ticker: string) => persist(api.addWorkspaceTicker, ticker), onSuccess: async (state) => { setInput(""); await saved(state); } });
  const remove = useMutation({ mutationFn: (ticker: string) => persist(api.removeWorkspaceTicker, ticker), onSuccess: saved });
  const tickers = workspace.data?.source === "database" ? workspace.data.watchlist : data.watchlist.map((row) => row.ticker);
  const pending = add.isPending || remove.isPending;
  const canEdit = workspace.data?.source === "database";
  const shown = expanded ? tickers : tickers.slice(0, 8);
  const recent = (workspace.data?.recent_tickers ?? []).filter((ticker) => !tickers.includes(ticker)).slice(0, 8);
  function addTicker() {
    const clean = input.trim().toUpperCase().replace(/[^A-Z0-9.-]/g, "").slice(0, 32);
    if (clean && !pending && canEdit) add.mutate(clean);
  }
  return <Panel id="watchlist" icon={BookmarkPlus} title="Meine Watchlist" detail="Beobachtete Aktien verwalten und zuletzt geöffnete Analysen wiederfinden." action={<span className="text-xs text-[#687386]">{tickers.length} Aktien</span>}>
    <form className="mb-4 flex max-w-md gap-2" onSubmit={(event) => { event.preventDefault(); addTicker(); }}>
      <label htmlFor="watchlist-ticker" className="sr-only">Ticker zur Watchlist hinzufügen</label>
      <input id="watchlist-ticker" className="h-10 min-w-0 flex-1 rounded-lg border border-[#d8e1ea] bg-white px-3 text-sm uppercase outline-none focus:border-[#0f766e]" placeholder="Ticker hinzufügen, z. B. AAPL" maxLength={32} value={input} onChange={(event) => setInput(event.target.value)} />
      <button type="submit" disabled={pending || !input.trim() || !canEdit} className="inline-flex items-center gap-1.5 rounded-lg bg-[#0f766e] px-3 text-xs font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50"><Plus size={14} />Hinzufügen</button>
    </form>
    {(add.isError || remove.isError) && <p role="alert" className="mb-3 text-sm text-[#c2413b]">Die Watchlist konnte nicht gespeichert werden. Bitte erneut versuchen.</p>}
    {(workspace.isError || workspace.data?.source === "default") && <p role="alert" className="mb-3 text-xs text-[#b7791f]">Die Watchlist-Verwaltung ist derzeit nicht verfügbar. Der letzte gespeicherte Überblick bleibt sichtbar.</p>}
    {!tickers.length ? <Empty text="Noch keine Watchlist gespeichert. Füge eine Aktie über ihren Ticker hinzu." /> : <div className="grid gap-x-5 gap-y-2 md:grid-cols-2 xl:grid-cols-4">{shown.map((ticker) => {
      const row = data.watchlist.find((item) => item.ticker === ticker);
      return <div key={ticker} className="flex items-center gap-1 rounded-lg border border-[#e3e8ef] bg-[#fbfcfd]">
        <Link href={`/stocks/${encodeURIComponent(ticker)}`} className="min-w-0 flex-1 px-3 py-2.5"><b className="text-sm text-[#172033]">{ticker}</b><p className="mt-1 truncate text-[11px] text-[#687386]">{row?.data_status === "available" ? `Score ${row.overall_score} · ${row.top_warning || "Keine Warnung"}` : row?.data_status === "error" ? "Bewertung derzeit nicht verfügbar" : row ? "Noch nicht bewertet" : "Bewertung öffnen"}</p></Link>
        <button aria-label={`${ticker} aus Watchlist entfernen`} disabled={pending || !canEdit} className="mr-1 rounded-md p-2 text-[#94a3b8] hover:bg-[#fbeeee] hover:text-[#c2413b] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#0f766e] disabled:opacity-40" type="button" onClick={() => remove.mutate(ticker)}><Trash2 size={14} /></button>
      </div>;
    })}</div>}
    {tickers.length > 8 && <button type="button" className="mt-3 text-xs font-semibold text-[#0f766e]" aria-expanded={expanded} onClick={() => setExpanded(!expanded)}>{expanded ? "Weniger anzeigen" : `Alle ${tickers.length} Aktien anzeigen`}</button>}
    {!!recent.length && <div className="mt-5 flex flex-wrap items-center gap-2 border-t border-[#e3e8ef] pt-4"><span className="mr-1 inline-flex items-center gap-1.5 text-xs text-[#687386]"><Clock3 size={13} />Zuletzt geöffnet</span>{recent.map((ticker) => <Link key={ticker} href={`/stocks/${encodeURIComponent(ticker)}`} className="rounded-md bg-[#edf2f6] px-2.5 py-1 text-xs font-medium text-[#475569] hover:text-[#0f766e]">{ticker}</Link>)}</div>}
  </Panel>;
}

export function HomeSystemStatus({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const quality = useQuery({ queryKey: ["data-diagnostics"], queryFn: api.dataDiagnostics, staleTime: 60_000, enabled: open });
  const notifications = useQuery({ queryKey: ["pushover-delivery-log"], queryFn: api.pushoverDeliveryLog, staleTime: 30_000, enabled: open });
  return <details id="systemstatus" open={open} onToggle={(event) => onOpenChange(event.currentTarget.open)} className="dashboard-section scroll-mt-28 !p-5 md:!p-6">
    <summary className="flex cursor-pointer list-none items-center justify-between gap-3 rounded-md text-sm font-semibold text-[#475569] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#0f766e]">Daten & Meldungen <ChevronDown size={16} className={open ? "rotate-180" : ""} /></summary>
    <p className="mt-2 text-xs text-[#687386]">Datenaktualität, Kapitalmaßnahmen und der Versandstatus deiner ATR-Alarme.</p>
    <div className="mt-5 grid gap-6 lg:grid-cols-3">
      <div><h3 className="mb-3 flex items-center gap-1.5 text-xs font-semibold text-[#475569]"><Clock3 size={14} />Datenaktualität</h3>
        {quality.isLoading ? <Empty text="Datenstatus wird geladen …" /> : quality.isError ? <Empty text="Datenstatus derzeit nicht verfügbar." /> : <div className="space-y-2">{quality.data?.freshness.map((item) => <div key={item.name} className="flex items-center justify-between gap-3 rounded-lg bg-[#f7f9fb] px-3 py-2"><div><p className="text-xs font-medium text-[#475569]">{freshnessLabel(item.name)}</p><p className="mt-0.5 text-[11px] text-[#94a3b8]">{item.as_of || "Stand fehlt"}</p></div><StatusChip tone={item.status === "fresh" ? "good" : item.status === "stale" ? "warning" : "bad"}>{item.status === "fresh" ? "Aktuell" : item.status === "stale" ? "Veraltet" : "Fehlt"}</StatusChip></div>)}</div>}
        <div className="mt-3"><TextLink href="/settings#data-quality">Datenqualität öffnen</TextLink></div>
      </div>
      <div><h3 className="mb-3 flex items-center gap-1.5 text-xs font-semibold text-[#475569]"><ShieldCheck size={14} />Kapitalmaßnahmen</h3>
        {quality.isLoading ? <Empty text="Kapitalmaßnahmen werden geladen …" /> : quality.isError ? <Empty text="Kapitalmaßnahmen derzeit nicht verfügbar." /> : !quality.data?.corporate_events.length ? <Empty text="Keine auffälligen Split- oder Dividendenkandidaten." /> : <div className="space-y-2">{quality.data.corporate_events.slice(0, 5).map((item, i) => <Link key={`${item.ticker}-${i}`} href={`/stocks/${encodeURIComponent(item.ticker)}`} className="block rounded-lg bg-[#f7f9fb] px-3 py-2"><div className="flex flex-wrap items-center justify-between gap-2"><b className="text-xs text-[#172033]">{item.ticker}</b><StatusChip tone={item.severity === "critical" ? "bad" : item.severity === "warning" ? "warning" : "neutral"}>{item.label}</StatusChip></div><p className="mt-1 text-[11px] text-[#687386]">{item.event_date || item.detail}</p></Link>)}</div>}
      </div>
      <div><h3 className="mb-3 flex items-center gap-1.5 text-xs font-semibold text-[#475569]"><BellRing size={14} />Letzte ATR-Meldungen</h3>
        {notifications.isLoading ? <Empty text="Meldungen werden geladen …" /> : notifications.isError ? <Empty text="Zustellstatus derzeit nicht verfügbar." /> : !notifications.data?.entries.length ? <Empty text="Noch keine ATR-Zustellung protokolliert." /> : <div className="space-y-2">{notifications.data.entries.slice(0, 5).map((item, i) => <Link key={`${item.timestamp}-${i}`} href={item.ticker ? `/sell-monitor/${encodeURIComponent(item.ticker)}` : "/settings"} className="block rounded-lg bg-[#f7f9fb] px-3 py-2"><div className="flex items-center justify-between gap-2"><b className="text-xs text-[#172033]">{item.ticker || "System"}</b><StatusChip tone={item.status === "sent" ? "good" : item.status === "failed" ? "bad" : "neutral"}>{item.status === "sent" ? "Gesendet" : item.status === "failed" ? "Fehlgeschlagen" : "Übersprungen"}</StatusChip></div><p className="mt-1 text-[11px] text-[#687386]">{formatDateTime(item.timestamp)}</p></Link>)}</div>}
      </div>
    </div>
  </details>;
}
function freshnessLabel(name: string) {
  return ({ prices: "Kurse", market_snapshot: "Marktstatus", trend_benchmark: "Trend-Benchmark", market_breadth: "Marktbreite", relative_strength: "Relative Stärke", fundamentals_tracked: "Fundamentaldaten", earnings_calendar: "Earnings-Kalender", institutional_13f: "13F-Daten", sell_ranking: "Verkaufsmonitor" } as Record<string, string>)[name] ?? name;
}
