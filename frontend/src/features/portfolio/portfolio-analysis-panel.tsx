"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api/client";
import { useViewState } from "@/lib/view-state";
import { SavedViews } from "@/components/ui/saved-views";
import { QueryState } from "@/components/ui/query-state";
import type { PortfolioAnalysis } from "@/lib/types/analysis";

const defaults = { tab: "attribution", sessions: 21, sector: "all", sectorShock: -10, fxShock: -5 };
const percent = (value: number | null | undefined) => value == null ? "Nicht verfügbar" : `${value.toLocaleString("de-DE", { maximumFractionDigits: 1 })} %`;
const money = (value: number | null | undefined, currency: string) => value == null ? "Nicht verfügbar" : value.toLocaleString("de-DE", { style: "currency", currency, maximumFractionDigits: 2 });

export function PortfolioAnalysisPanel() {
  const [open, setOpen] = useState(false);
  const [view, setView] = useViewState("portfolio", defaults);
  const params = new URLSearchParams({ sessions: String(view.sessions), sector_shock: String(view.sectorShock), fx_shock: String(view.fxShock), shocked_sector: view.sector });
  const query = useQuery({ queryKey: ["portfolio-analysis", params.toString()], queryFn: () => api.portfolioAnalysis(params.toString()), enabled: open, staleTime: 60_000 });
  const data = query.data;
  return <details className="dashboard-section" open={open} onToggle={event => setOpen(event.currentTarget.open)}>
    <summary className="cursor-pointer text-base font-semibold">Depotanalyse <span className="ml-2 text-xs font-normal text-[#687386]">Ergebnisbeiträge · Konzentration · Earnings · Szenarien</span></summary>
    {open && <div className="mt-4 space-y-4">
      <SavedViews scope="portfolio" />
      <nav className="flex flex-wrap gap-2" aria-label="Depotanalyse Bereiche">{[["attribution", "Ergebnis erklären"], ["risk", "Konzentration & Risiko"], ["earnings", "Earnings-Exposition"], ["scenarios", "Szenarien"]].map(([key, label]) => <button key={key} type="button" className={`app-button ${view.tab === key ? "app-button-primary" : ""}`} aria-pressed={view.tab === key} onClick={() => setView({ tab: key })}>{label}</button>)}</nav>
      <QueryState error={query.error} loading={query.isLoading} hasData={Boolean(data)} onRetry={() => query.refetch()} />
      {data && <>
        <p className="text-xs text-[#687386]">Stand {data.as_of} · Basiswährung {data.currency} · gespeicherte Daten</p>
        {view.tab === "attribution" && <Attribution data={data} sessions={view.sessions} onPeriod={sessions => setView({ sessions })} />}
        {view.tab === "risk" && <Risk data={data} />}
        {view.tab === "earnings" && <Earnings data={data} />}
        {view.tab === "scenarios" && <Scenarios data={data} view={view} onApply={setView} />}
        <ul className="space-y-1 text-xs text-[#687386]">{data.notes.map(note => <li key={note}>{note}</li>)}</ul>
      </>}
    </div>}
  </details>;
}

function Attribution({ data, sessions, onPeriod }: { data: PortfolioAnalysis; sessions: number; onPeriod: (value: number) => void }) {
  const a = data.attribution;
  const max = Math.max(1, ...a.rows.map(row => Math.abs(row.result ?? 0)));
  return <div className="space-y-4">
    <div className="flex flex-wrap items-center justify-between gap-2"><h3 className="font-semibold">{a.model === "executions" ? "Beitrag aus Ausführungen" : "Simulation des heutigen Bestands"}</h3><label className="text-sm">Zeitraum <select className="input-dark ml-2 !w-auto" aria-label="Attributionszeitraum" value={sessions} onChange={event => onPeriod(Number(event.target.value))}>{[[1, "1 Sitzung"], [21, "21 Sitzungen"], [63, "63 Sitzungen"], [126, "126 Sitzungen"]].map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label></div>
    <p className="app-notice">{a.note} Zeitraum: {a.start} bis {a.end}. Bewertbar: {a.covered_count}/{a.total_count} Instrumente.</p>
    <div className="grid gap-3 sm:grid-cols-3"><Metric label="Gesamtbeitrag" value={money(a.result, data.currency)} /><Metric label="Cash: Wechselkurseffekt" value={money(a.cash_fx, data.currency)} /><Metric label="Externe Cashbewegungen" value={money(a.external_cash_flow, data.currency)} /></div>
    <div className="space-y-2">{a.rows.filter(row => row.result !== null).sort((x, y) => Math.abs(y.result!) - Math.abs(x.result!)).map(row => <div key={row.ticker} className="grid grid-cols-[80px_1fr_110px] items-center gap-3 text-sm"><Link className="font-semibold text-[#0f766e]" href={`/stocks/${encodeURIComponent(row.ticker)}`}>{row.ticker}</Link><div className="h-2 rounded bg-slate-100"><div className={`h-2 rounded ${row.result! < 0 ? "bg-[#c2413b]" : "bg-[#138a57]"}`} style={{ width: `${Math.abs(row.result!) / max * 100}%` }} /></div><span className="text-right tabular-nums">{money(row.result, data.currency)}</span></div>)}</div>
    <details><summary className="cursor-pointer text-sm font-semibold">Beiträge nachvollziehen</summary><p className="my-2 text-xs text-[#687386]">{a.decomposition} Kosten enthalten Gebühren und Steuern.</p><div className="overflow-x-auto"><table className="w-full min-w-[680px] text-left text-sm"><thead><tr>{["Aktie", "Anfang", "Ende", "Kurseffekt", "FX Anfangsbestand", "Kosten", "Handel & Wechselwirkung", "Ergebnis"].map(label => <th key={label} className="p-2">{label}</th>)}</tr></thead><tbody>{a.rows.map(row => <tr key={row.ticker} className="border-t border-[#e3e8ef]"><th className="p-2">{row.ticker}</th>{[row.opening_value, row.ending_value, row.price_effect, row.fx_effect, row.costs, row.trading_and_interaction, row.result].map((value, i) => <td key={i} className="p-2 tabular-nums">{money(value, data.currency)}</td>)}</tr>)}</tbody></table></div></details>
  </div>;
}

function Risk({ data }: { data: PortfolioAnalysis }) {
  const [all, setAll] = useState(false);
  const correlations = [...data.correlations].sort((a, b) => (b.value ?? -2) - (a.value ?? -2));
  return <div className="space-y-5">
    <div className="grid gap-5 lg:grid-cols-2"><Allocation title="Sektorgewichte" rows={data.sectors} /><Allocation title="Branchengewichte" rows={data.industry_groups} /></div>
    <p className="text-sm">Cashquote: <strong>{percent(data.cash_ratio_pct)}</strong> · Größte fünf Positionen: {percent(data.top_positions.reduce((sum, row) => sum + row.weight_pct, 0))}</p>
    <details><summary className="cursor-pointer font-semibold">Abstand zum gesetzten Stopp</summary><div className="mt-2 grid gap-2 sm:grid-cols-2">{data.stops.map(row => <div key={row.ticker} className="rounded border p-3 text-sm"><Link href={`/sell-monitor/${encodeURIComponent(row.ticker)}`} className="font-semibold text-[#0f766e]">{row.ticker}</Link> · {row.stop == null ? "Stopp fehlt" : `${money(row.stop, row.currency)} · Abstand ${percent(row.distance_pct)}`}<p className="mt-1 text-xs text-[#687386]">Modelliertes Stopprisiko: {percent(row.modeled_loss_pct)} des Depots</p></div>)}</div></details>
    <div><h3 className="font-semibold">Gemeinsame Kursbewegungen</h3><p className="mt-1 text-xs text-[#687386]">{data.correlation_note}</p><div className="mt-3 grid gap-2 sm:grid-cols-2">{(all ? correlations : correlations.slice(0, 8)).map(row => <div key={`${row.left}-${row.right}`} className="rounded border p-3 text-sm">{row.left} / {row.right}: <strong>{row.value == null ? "Zu wenig Daten" : row.value.toLocaleString("de-DE", { maximumFractionDigits: 2 })}</strong><span className="ml-2 text-xs text-[#687386]">{row.observations} Beobachtungen</span></div>)}</div>{correlations.length > 8 && <button type="button" className="app-button mt-3" onClick={() => setAll(!all)}>{all ? "Weniger" : `Alle ${correlations.length} Paare`}</button>}{!correlations.length && <p className="mt-2 text-sm text-[#687386]">Mindestens zwei Positionen erforderlich.</p>}</div>
  </div>;
}

function Earnings({ data }: { data: PortfolioAnalysis }) {
  return <div className="space-y-4"><h3 className="font-semibold">Gewicht bekannter Berichtstermine</h3><div className="grid gap-3 sm:grid-cols-3">{data.earnings.windows.map(row => <Metric key={row.days} label={`Nächste ${row.days} Tage`} value={percent(row.weight_pct)} />)}</div><p className="app-notice">Für {percent(data.earnings.missing_weight_pct)} des Depots ist kein Termin im nächsten 30-Tage-Fenster gespeichert. Fehlende Termine sind keine Entwarnung.</p><div className="divide-y">{data.earnings.rows.map(row => <Link key={row.ticker} href={`/stocks/${encodeURIComponent(row.ticker)}`} className="flex flex-wrap justify-between gap-2 py-3 text-sm"><span><strong>{row.ticker}</strong> · {percent(row.weight_pct)} Depotgewicht</span><span>{row.date} · {row.time === "bmo" ? "Vor US-Handelsbeginn" : row.time === "amc" ? "Nach US-Handelsschluss" : "Uhrzeit unbekannt"} · {row.source}{row.date_conflict ? " · Anbietertermine widersprechen sich" : ""}</span></Link>)}</div></div>;
}

function Scenarios({ data, view, onApply }: { data: PortfolioAnalysis; view: typeof defaults; onApply: (value: Partial<typeof defaults>) => void }) {
  return <form className="space-y-4" onSubmit={event => { event.preventDefault(); const form = new FormData(event.currentTarget); onApply({ sector: String(form.get("sector")), sectorShock: Number(form.get("shock")), fxShock: Number(form.get("fx")) }); }}>
    <h3 className="font-semibold">Annahmen selbst vorgeben</h3><div className="grid gap-3 sm:grid-cols-3"><label className="text-sm">Betroffener Sektor<select name="sector" className="input-dark mt-1" defaultValue={view.sector}><option value="all">Alle Aktien</option>{data.sectors.map(row => <option key={row.name}>{row.name}</option>)}</select></label><label className="text-sm">Sektorbewegung in %<input name="shock" className="input-dark mt-1" type="number" min={-100} max={100} step="any" defaultValue={view.sectorShock} required /></label><label className="text-sm">Fremdwährungen gegen Basis in %<input name="fx" className="input-dark mt-1" type="number" min={-100} max={100} step="any" defaultValue={view.fxShock} required /></label></div><button className="app-button" type="submit">Szenarien berechnen</button><div className="grid gap-3 sm:grid-cols-2"><Metric label={`Sektorszenario · ${percent(data.scenarios.sector_shock_pct)}`} value={money(data.scenarios.sector_impact, data.currency)} /><Metric label={`Währungsszenario · ${percent(data.scenarios.fx_shock_pct)}`} value={money(data.scenarios.fx_impact, data.currency)} /></div><p className="app-notice">{data.scenarios.note}</p>
  </form>;
}

function Allocation({ title, rows }: { title: string; rows: { name: string; weight_pct: number }[] }) {
  return <div><h3 className="mb-3 font-semibold">{title}</h3><div className="space-y-3">{rows.map(row => <div key={row.name}><div className="mb-1 flex justify-between gap-2 text-sm"><span>{row.name}</span><strong>{percent(row.weight_pct)}</strong></div><div className="h-2 rounded bg-slate-100"><div className="h-2 rounded bg-[#0f766e]" style={{ width: `${Math.min(100, Math.max(0, row.weight_pct))}%` }} /></div></div>)}</div></div>;
}
function Metric({ label, value }: { label: string; value: string }) { return <div className="rounded-lg border border-[#e3e8ef] bg-white p-3"><p className="text-xs text-[#687386]">{label}</p><p className="mt-2 text-xl font-semibold tabular-nums">{value}</p></div>; }
