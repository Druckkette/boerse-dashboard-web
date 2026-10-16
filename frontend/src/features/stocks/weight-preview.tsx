"use client";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import Link from "next/link";
import { useBetaMode } from "@/components/beta-mode-provider";
import { api } from "@/lib/api/client";

const keys = ["technical", "fundamental", "chart", "moving_average"] as const;
const labels = ["Technik", "Fundamental", "Chart", "Trend"];
export function WeightPreview() {
  const beta = useBetaMode();
  const [open, setOpen] = useState(false);
  const settings = useQuery({ queryKey: ["settings"], queryFn: api.settings, enabled: open && !beta, staleTime: 60_000 });
  const preview = useMutation({ mutationFn: api.weightPreview });
  if (beta) return null;
  const weights = settings.data?.assessment_score_weights?.overall;
  return <details className="dashboard-section" onToggle={event => setOpen(event.currentTarget.open)}><summary className="cursor-pointer font-semibold">Gewichte vergleichen · ohne Strategieänderung</summary>{open && <div className="mt-4 space-y-4"><p className="text-sm text-[#687386]">Alternative Gewichtung derselben gespeicherten Teil-Scores. Ergebnisse werden nicht gespeichert und ändern keine Produktionsrangliste.</p>{settings.error && <p role="alert" className="app-notice">Aktuelle Gewichte nicht verfügbar. Vergleich derzeit gesperrt.</p>}{weights && <form key={JSON.stringify(weights)} className="space-y-3" onSubmit={event => { event.preventDefault(); const form = new FormData(event.currentTarget); preview.mutate(Object.fromEntries(keys.map(key => [key, Number(form.get(key))]))); }}><div className="grid gap-3 sm:grid-cols-4">{keys.map((key, index) => <label key={key} className="text-sm">{labels[index]}<input className="input-dark mt-1" type="number" min={0} max={100} step="any" name={key} defaultValue={weights[key] ?? 0} required /></label>)}</div><button className="app-button" type="submit" disabled={preview.isPending}>{preview.isPending ? "Vergleich läuft …" : "Alternative berechnen"}</button></form>}{preview.error && <p role="alert" className="app-notice">{preview.error.message}</p>}{preview.data && <><p className="app-notice">{preview.data.note} Vergleichbar: {preview.data.count}; ausgeschlossen wegen fehlender oder anderer Berechnungsversion: {preview.data.excluded}.</p><div className="max-h-[460px] overflow-auto"><table className="w-full min-w-[560px] text-left text-sm"><thead><tr>{["Aktie", "Score bisher", "Alternativ", "Rang bisher", "Rang alternativ", "Rangänderung", "Abdeckung"].map(label => <th key={label} className="p-2">{label}</th>)}</tr></thead><tbody>{preview.data.rows.map(row => <tr key={row.ticker} className="border-t"><th className="p-2"><Link className="text-[#0f766e]" href={`/stocks/${encodeURIComponent(row.ticker)}`}>{row.ticker}</Link></th><td className="p-2">{row.current_score}</td><td className="p-2">{row.alternative_score?.toLocaleString("de-DE", { maximumFractionDigits: 1 }) ?? "Fehlt"}</td><td className="p-2">{row.previous_rank}</td><td className="p-2">{row.rank}</td><td className="p-2">{row.rank_change > 0 ? "+" : ""}{row.rank_change}</td><td className="p-2">{Math.round(row.coverage * 100)} %</td></tr>)}</tbody></table></div></>}</div>}</details>;
}
