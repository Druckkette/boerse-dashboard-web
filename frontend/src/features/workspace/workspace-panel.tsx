"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  BellRing,
  BookmarkPlus,
  Clock3,
  ExternalLink,
  ShieldCheck,
  Trash2,
  TrendingUp
} from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";
import { StatusChip } from "@/components/ui/status-chip";
import { api } from "@/lib/api/client";
import { formatDateTime, formatPercent, qualityLabel } from "@/lib/format";
import type { Tone, WorkspaceState } from "@/lib/types/api";

const workspaceKey = ["workspace"];
const emptyWorkspace: WorkspaceState = {
  source: "default",
  updated_at: null,
  watchlist: [],
  todos: "",
  recent_tickers: []
};

export function WorkspacePanel() {
  const queryClient = useQueryClient();
  const [tickerInput, setTickerInput] = useState("");
  const workspaceQuery = useQuery({ queryKey: workspaceKey, queryFn: api.workspace, staleTime: 30_000 });
  const portfolioQuery = useQuery({ queryKey: ["portfolio-snapshot"], queryFn: api.portfolioSnapshot, staleTime: 60_000 });
  const marketQuery = useQuery({ queryKey: ["today-market"], queryFn: () => api.marketOverview("^GSPC"), staleTime: 60_000 });
  const diagnosticsQuery = useQuery({ queryKey: ["today-data-quality"], queryFn: api.dataDiagnostics, staleTime: 60_000 });
  const sellQuery = useQuery({ queryKey: ["sell-ranking"], queryFn: api.sellRanking, staleTime: 60_000 });
  const buyStrengthQuery = useQuery({ queryKey: ["portfolio-buy-strength", 3], queryFn: () => api.portfolioBuyStrength({ weeks: 3 }), staleTime: 60_000 });
  const notificationsQuery = useQuery({ queryKey: ["pushover-delivery-log"], queryFn: api.pushoverDeliveryLog, staleTime: 30_000 });
  const workspace = workspaceQuery.data ?? emptyWorkspace;

  const addMutation = useMutation({
    mutationFn: (ticker: string) => api.addWorkspaceTicker(ticker),
    onSuccess: (state) => queryClient.setQueryData(workspaceKey, state),
    onSettled: () => queryClient.invalidateQueries({ queryKey: workspaceKey })
  });
  const removeMutation = useMutation({
    mutationFn: (ticker: string) => api.removeWorkspaceTicker(ticker),
    onSuccess: (state) => queryClient.setQueryData(workspaceKey, state),
    onSettled: () => queryClient.invalidateQueries({ queryKey: workspaceKey })
  });

  const priorities = useMemo(
    () => (sellQuery.data?.rows ?? [])
      .filter((row) => row.status !== "Halten" || row.data_quality_status !== "trusted")
      .slice(0, 6),
    [sellQuery.data?.rows]
  );
  const quality = diagnosticsQuery.data;
  const market = marketQuery.data;
  const portfolio = portfolioQuery.data;

  function addTicker() {
    const clean = normalizeTicker(tickerInput);
    if (!clean) return;
    addMutation.mutate(clean);
    setTickerInput("");
  }

  return (
    <div className="space-y-4">
      <section className="grid gap-2.5 sm:grid-cols-2 xl:grid-cols-4">
        <TodayMetric
          label="Marktphase"
          value={market?.phase_label ?? "Wird geladen"}
          detail={market ? `${market.warning_count} Warnzeichen · Stand ${market.as_of} ${market.as_of_time}` : "Marktdaten werden geprüft"}
          tone={marketTone(market?.phase)}
        />
        <TodayMetric
          label="Datenbasis"
          value={quality ? qualityLabel(quality.decision_status) : "Wird geprüft"}
          detail={quality?.summary ?? "Aktualität und Plausibilität werden geprüft"}
          tone={quality?.health_tone ?? "neutral"}
        />
        <TodayMetric
          label="Handlungsbedarf"
          value={String(priorities.length)}
          detail="Positionen mit Signal oder Datenproblem"
          tone={priorities.length ? "warning" : "good"}
        />
        <TodayMetric
          label="Stop-Abdeckung"
          value={portfolio ? `${Math.round(portfolio.stop_coverage_pct)}%` : "–"}
          detail={portfolio ? `${portfolio.stop_coverage_count} von ${portfolio.stop_coverage_total} Positionen` : "Portfolio wird geladen"}
          tone={!portfolio ? "neutral" : portfolio.stop_coverage_pct >= 95 ? "good" : portfolio.stop_coverage_pct >= 70 ? "warning" : "bad"}
        />
      </section>

      <div className="grid items-start gap-4 xl:grid-cols-[1.15fr_0.85fr]">
        <section className="dashboard-section">
          <SectionTitle icon={AlertTriangle} title="Heute prüfen" detail="Nur neue Signale und eingeschränkte Entscheidungen." />
          {priorities.length ? (
            <div className="divide-y divide-[#e8edf2]">
              {priorities.map((row) => {
                const blocked = row.data_quality_status === "blocked";
                return (
                  <Link
                    key={row.ticker}
                    className="grid gap-2 py-3 transition first:pt-0 last:pb-0 hover:bg-[#f8fafc] sm:grid-cols-[100px_130px_1fr_auto] sm:items-center sm:px-2"
                    href={`/sell-monitor/${encodeURIComponent(row.ticker)}`}
                  >
                    <span className="font-semibold text-[#172033]">{row.ticker}</span>
                    <StatusChip tone={blocked ? "bad" : row.status === "Verkaufen" ? "bad" : "warning"}>
                      {blocked ? "Daten prüfen" : row.status}
                    </StatusChip>
                    <span className="min-w-0 truncate text-sm text-[#687386]" title={blocked ? row.data_quality_detail : row.primary_signal}>
                      {blocked ? row.data_quality_detail : row.primary_signal || row.reason}
                    </span>
                    <ExternalLink className="hidden size-4 text-[#8b95a5] sm:block" />
                  </Link>
                );
              })}
            </div>
          ) : (
            <EmptyState text="Keine Position benötigt aktuell eine Prüfung." />
          )}
        </section>

        <section className="dashboard-section">
          <SectionTitle icon={Clock3} title="Datenaktualität" detail="Zeigt den letzten erfolgreichen Stand der wichtigsten Datenbereiche." />
          <div className="space-y-2">
            {(quality?.freshness ?? []).map((item) => (
              <div key={item.name} className="flex items-center justify-between gap-3 rounded-[9px] bg-[#f7f9fb] px-3 py-2">
                <div className="min-w-0">
                  <div className="text-sm font-medium text-[#172033]">{freshnessLabel(item.name)}</div>
                  <div className="truncate text-xs text-[#687386]">{item.as_of ? `Stand ${item.as_of}` : "Noch keine Daten"}</div>
                </div>
                <StatusChip tone={item.status === "fresh" ? "good" : item.status === "stale" ? "warning" : "bad"}>
                  {item.status === "fresh" ? "Aktuell" : item.status === "stale" ? "Veraltet" : "Fehlt"}
                </StatusChip>
              </div>
            ))}
          </div>
          <Link className="mt-3 inline-flex items-center gap-2 text-sm font-semibold text-[#0f766e]" href="/settings#data-quality">
            Datenqualität öffnen <ExternalLink size={14} />
          </Link>
        </section>
      </div>

      <div className="grid items-start gap-4 xl:grid-cols-3">
        <section className="dashboard-section">
          <SectionTitle icon={TrendingUp} title="Frische Käufe" detail="Standardfenster: drei Wochen ab Kauf." />
          <CompactLinks
            empty="Keine frischen Käufe im aktuellen Fenster."
            rows={(buyStrengthQuery.data?.items ?? []).slice(0, 5).map((item) => ({
              href: `/portfolio/buy-strength/${encodeURIComponent(item.ticker)}`,
              title: item.ticker,
              value: item.status_label,
              detail: `${item.age_days} Tage · ${formatPercent(item.pnl_pct)}`,
              tone: item.status === "stark" ? "good" : item.status === "risk" ? "bad" : "warning"
            }))}
          />
        </section>

        <section className="dashboard-section">
          <SectionTitle icon={BellRing} title="Letzte ATR-Alarme" detail="Nachweis von Versand, Fehlern und übersprungenen Meldungen." />
          <CompactLinks
            empty="Noch keine Pushover-Zustellung protokolliert."
            rows={(notificationsQuery.data?.entries ?? []).slice(0, 5).map((item) => ({
              href: item.ticker ? `/sell-monitor/${encodeURIComponent(item.ticker)}` : "/settings",
              title: item.ticker || "System",
              value: item.status === "sent" ? "Gesendet" : item.status === "failed" ? "Fehlgeschlagen" : "Übersprungen",
              detail: formatDateTime(item.timestamp),
              tone: item.status === "sent" ? "good" : item.status === "failed" ? "bad" : "neutral"
            }))}
          />
        </section>

        <section className="dashboard-section">
          <SectionTitle icon={ShieldCheck} title="Kapitalmaßnahmen" detail="Automatisch erkannte Kandidaten, die Kursreihen verzerren können." />
          <CompactLinks
            empty="Keine auffälligen Split- oder Dividendenkandidaten."
            rows={(quality?.corporate_events ?? []).slice(0, 5).map((item) => ({
              href: `/stocks/${encodeURIComponent(item.ticker)}`,
              title: item.ticker,
              value: item.label,
              detail: item.event_date || item.detail,
              tone: item.severity === "critical" ? "bad" : item.severity === "warning" ? "warning" : "neutral"
            }))}
          />
        </section>
      </div>

      <section className="dashboard-section">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <SectionTitle icon={BookmarkPlus} title="Watchlist und Verlauf" detail="Beobachtete und zuletzt geöffnete Aktien schnell wiederfinden." />
          <div className="flex w-full gap-2 lg:max-w-sm">
            <input
              className="h-9 min-w-0 flex-1 rounded-[9px] border border-[#d8e1ea] px-3 text-sm uppercase outline-none focus:border-[#0f766e]"
              placeholder="Ticker"
              value={tickerInput}
              onChange={(event) => setTickerInput(event.target.value)}
              onKeyDown={(event) => { if (event.key === "Enter") addTicker(); }}
            />
            <button className="rounded-[9px] bg-[#0f766e] px-3 text-sm font-semibold text-white" type="button" onClick={addTicker}>
              Hinzufügen
            </button>
          </div>
        </div>
        <div className="mt-3 flex flex-wrap gap-2">
          {[...workspace.watchlist, ...workspace.recent_tickers.filter((ticker) => !workspace.watchlist.includes(ticker))].slice(0, 24).map((ticker) => (
            <span key={ticker} className="inline-flex overflow-hidden rounded-[9px] border border-[#dfe6ed] bg-[#f8fafc]">
              <Link className="px-3 py-1.5 text-sm font-semibold text-[#172033] hover:text-[#0f766e]" href={`/stocks/${encodeURIComponent(ticker)}`}>{ticker}</Link>
              {workspace.watchlist.includes(ticker) ? (
                <button aria-label={`${ticker} entfernen`} className="border-l border-[#dfe6ed] px-2 text-[#8b95a5] hover:text-[#c2413b]" type="button" onClick={() => removeMutation.mutate(ticker)}>
                  <Trash2 size={13} />
                </button>
              ) : null}
            </span>
          ))}
          {!workspace.watchlist.length && !workspace.recent_tickers.length ? <EmptyState text="Noch keine Watchlist oder zuletzt geöffneten Aktien." /> : null}
        </div>
      </section>
    </div>
  );
}

function TodayMetric({ label, value, detail, tone }: { label: string; value: string; detail: string; tone: Tone }) {
  const color = tone === "good" ? "#138a57" : tone === "bad" ? "#c2413b" : tone === "warning" ? "#b7791f" : "#2563eb";
  return (
    <div className="rounded-[12px] border border-[#e3e8ef] bg-white px-3.5 py-3 shadow-[0_4px_14px_rgba(15,23,42,0.04)]" style={{ borderTopColor: color, borderTopWidth: 3 }}>
      <div className="text-[10px] font-semibold uppercase tracking-[0.08em] text-[#687386]">{label}</div>
      <div className="mt-1 text-xl font-semibold text-[#172033]">{value}</div>
      <div className="mt-1 line-clamp-2 text-xs leading-5 text-[#687386]">{detail}</div>
    </div>
  );
}

function SectionTitle({ icon: Icon, title, detail }: { icon: typeof AlertTriangle; title: string; detail: string }) {
  return (
    <div className="mb-3 flex items-start gap-2.5">
      <span className="grid size-8 shrink-0 place-items-center rounded-[9px] bg-[#e8f4f2] text-[#0f766e]"><Icon size={16} /></span>
      <div><h2 className="text-sm font-semibold text-[#172033]">{title}</h2><p className="mt-0.5 text-xs leading-5 text-[#687386]">{detail}</p></div>
    </div>
  );
}

function CompactLinks({ rows, empty }: { rows: Array<{ href: string; title: string; value: string; detail: string; tone: Tone }>; empty: string }) {
  if (!rows.length) return <EmptyState text={empty} />;
  return <div className="space-y-1.5">{rows.map((row, index) => (
    <Link key={`${row.title}-${index}`} className="flex items-center justify-between gap-3 rounded-[9px] bg-[#f7f9fb] px-3 py-2 transition hover:bg-[#eef5f3]" href={row.href}>
      <span className="min-w-0"><span className="font-semibold text-[#172033]">{row.title}</span><span className="ml-2 text-xs text-[#687386]">{row.detail}</span></span>
      <StatusChip tone={row.tone}>{row.value}</StatusChip>
    </Link>
  ))}</div>;
}

function EmptyState({ text }: { text: string }) {
  return <div className="rounded-[9px] border border-dashed border-[#d8e1ea] bg-[#fafcfd] px-3 py-3 text-sm text-[#687386]">{text}</div>;
}

function normalizeTicker(value: string) {
  return value.trim().toUpperCase().replace(/[^A-Z0-9.^=-]/g, "").slice(0, 32);
}

function marketTone(phase?: string): Tone {
  if (phase === "aufwaertstrend" || phase === "gruen") return "good";
  if (phase === "rot") return "bad";
  if (phase === "gelb") return "warning";
  return "neutral";
}

function freshnessLabel(name: string) {
  return ({ prices: "Kurse", market_snapshot: "Marktstatus", trend_benchmark: "Trend-Benchmark", market_breadth: "Marktbreite", relative_strength: "Relative Stärke", fundamentals_tracked: "Fundamentaldaten", institutional_13f: "13F-Daten", sell_ranking: "Verkaufsmonitor" } as Record<string, string>)[name] ?? name;
}
