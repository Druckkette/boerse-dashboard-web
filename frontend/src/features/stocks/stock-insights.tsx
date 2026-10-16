"use client";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "@/lib/api/client";
import { useBetaMode } from "@/components/beta-mode-provider";
import { QueryState } from "@/components/ui/query-state";

export function StockInsights({ ticker }: { ticker: string }) {
  const beta = useBetaMode();
  const [historyOpen, setHistoryOpen] = useState(false);
  const [sourceOpen, setSourceOpen] = useState(false);
  const history = useQuery({ queryKey: ["score-history", ticker], queryFn: () => api.stockScoreHistory(ticker), enabled: !beta && historyOpen, staleTime: 60_000 });
  const sources = useQuery({ queryKey: ["stock-provenance", ticker], queryFn: () => api.stockProvenance(ticker), enabled: !beta && sourceOpen, staleTime: 60_000 });
  if (beta) return null;
  const points = history.data?.points ?? [];
  const width = 800;
  const x = (index: number) => 35 + index / Math.max(1, points.length - 1) * (width - 70);
  return <div className="space-y-4">
    <details className="dashboard-section" onToggle={event => setHistoryOpen(event.currentTarget.open)}><summary className="cursor-pointer font-semibold">Scoreverlauf und Ursachen</summary>{historyOpen && <div className="mt-4 space-y-3"><QueryState error={history.error} loading={history.isLoading} hasData={Boolean(history.data)} onRetry={() => history.refetch()} />{history.data && <>
      <p className="app-notice">{historyLabels[history.data.status] || "Noch keine Vergleichsbasis."} {history.data.note}</p>
      {points.length > 1 && <svg viewBox="0 0 800 210" className="w-full" role="img" aria-label="Archivierter Gesamtscore von 0 bis 100"><line x1="35" y1="180" x2="765" y2="180" stroke="#cbd5e1" /><text x="3" y="30" fontSize="12">100</text><text x="13" y="180" fontSize="12">0</text><path d={points.map((point, index) => `${point.connect_to_previous ? "L" : "M"}${x(index)},${180 - point.score * 1.5}`).join(" ")} fill="none" stroke="#0f766e" strokeWidth="2" />{points.map((point, index) => <circle key={point.as_of} cx={x(index)} cy={180 - point.score * 1.5} r="3" fill="#0f766e"><title>{point.as_of}: Score {point.score}, RS {point.rs ?? "fehlt"}</title></circle>)}<text x="35" y="205" fontSize="12">{points[0].as_of}</text><text x="765" y="205" textAnchor="end" fontSize="12">{points.at(-1)?.as_of}</text></svg>}
      {history.data.score_delta != null && <p className="font-semibold">Gesamtscore: {history.data.score_delta > 0 ? "+" : ""}{history.data.score_delta} Punkte</p>}
      <div className="grid gap-3 sm:grid-cols-2">{history.data.component_changes?.map(row => <div key={row.key} className="rounded-lg border p-3 text-sm"><strong>{componentLabels[row.key] || row.key}</strong><p>{row.before.toLocaleString("de-DE", { maximumFractionDigits: 1 })} → {row.after.toLocaleString("de-DE", { maximumFractionDigits: 1 })}</p><p className="text-xs text-[#687386]">Beitrag zur Veränderung: {row.contribution_delta > 0 ? "+" : ""}{row.contribution_delta.toLocaleString("de-DE", { maximumFractionDigits: 2 })} Punkte</p></div>)}</div>
      {history.data.rounding_delta != null && <p className="text-xs text-[#687386]">Rundungsanteil: {history.data.rounding_delta.toLocaleString("de-DE", { maximumFractionDigits: 4 })} Punkte. Die Beiträge einschließlich Rundung ergeben die Gesamtänderung.</p>}
      <ul className="space-y-2 text-sm">{history.data.changes.map(row => <li key={row.id || row.label}><strong>{row.after ? "Neu erfüllt" : "Entfallen"}: {row.label}</strong><p className="text-xs text-[#687386]">{row.detail}</p></li>)}</ul>
      {points.length > 0 && <p className="break-all text-xs text-[#687386]">Letzte gespeicherte Berechnung: {points.at(-1)?.calculation?.version || "Version nicht archiviert"} · {points.at(-1)?.calculation?.configuration_hash || "Konfiguration unbekannt"}</p>}
    </>}</div>}</details>
    <details className="dashboard-section" onToggle={event => setSourceOpen(event.currentTarget.open)}><summary className="cursor-pointer font-semibold">Datenherkunft und Berechnungsgrundlage</summary>{sourceOpen && <div className="mt-4 space-y-3"><QueryState error={sources.error} loading={sources.isLoading} hasData={Boolean(sources.data)} onRetry={() => sources.refetch()} />{sources.data && <>
      {!!sources.data.component_errors.length && <p className="app-notice">Einzelne Quellen konnten nicht gelesen werden: {sources.data.component_errors.join(", ")}.</p>}
      <div className="grid gap-3 lg:grid-cols-2">{sources.data.fields.map(field => <article key={field.key} className="rounded-lg border p-3"><h3 className="font-semibold">{field.label}: {field.value == null ? "Fehlt" : field.value.toLocaleString("de-DE", { maximumFractionDigits: 3 })} {field.value != null ? field.unit : ""}</h3><dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs text-[#687386]"><dt>Quelle</dt><dd>{field.source || "Nicht belegt"}</dd><dt>Berichtsperiode</dt><dd>{field.period || "Nicht gespeichert / nicht anwendbar"}</dd><dt>Beobachtung</dt><dd>{field.observation_date || "Unbekannt"}</dd><dt>Veröffentlicht</dt><dd>{field.publication_date || "Nicht gespeichert"}</dd><dt>Abgerufen</dt><dd>{field.retrieved_at || "Nicht gespeichert"}</dd></dl><p className="mt-2 text-xs leading-5">{field.formula}</p></article>)}</div>
      <p className="app-notice">{sources.data.institutional.note}{sources.data.institutional.status === "missing" ? ` Ursache: ${causes[sources.data.institutional.missing_cause] || "Noch nicht geklärt"}.` : ""}</p>
      <ul className="text-xs text-[#687386]">{sources.data.notes.map(note => <li key={note}>{note}</li>)}</ul>
    </>}</div>}</details>
  </div>;
}
const historyLabels: Record<string, string> = { comparable: "Vergleichbare archivierte Handelstage.", model_changed: "Regeln oder Gewichte wurden geändert; keine reine Marktveränderung.", coverage_changed: "Die Datenabdeckung hat sich geändert; Scoreunterschied nicht unmittelbar vergleichbar.", legacy_without_criteria: "Für ältere Stände fehlen archivierte Einzelkriterien.", session_gap: "Zwischen den gespeicherten Ständen fehlt mindestens ein Handelstag.", missing: "Noch keine ausreichende archivierte Historie." };
const componentLabels: Record<string, string> = { technical: "Technik", fundamental: "Fundamental", chart: "Chart", moving_average: "Trend" };
const causes: Record<string, string> = { identifier_unverified: "Wertpapierkennung nicht verifiziert", not_yet_classified: "Zuordnung oder öffentliche Holdings noch nicht geklärt" };
