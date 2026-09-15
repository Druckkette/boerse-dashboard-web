"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api/client";

const groups: Record<string, string> = { statements: "EPS / Umsatz / ROE", beta: "Beta", sec13f: "13F", filings: "Neue SEC-Berichte", assessment: "Folgebewertungen" };
const states: Record<string, string> = { queued: "eingeplant", running: "läuft", current: "geprüft, nächster Check geplant", waiting_source: "Quelle noch unvollständig", error: "Fehler, erneuter Versuch geplant" };

export function ReportWorkStatus({ enabled = true }: { enabled?: boolean }) {
  const query = useQuery({ queryKey: ["report-work"], queryFn: api.reportWork, enabled, refetchInterval: enabled ? 15_000 : false });
  return <section className="border-y border-[#e3e8ef] py-4 text-sm text-[#475569]" aria-label="Berichtspflege" aria-live="polite">
    <h2 className="font-semibold text-[#172033]">Berichtspflege im Hintergrund</h2>
    {query.error ? <p role="status" className="mt-2 text-amber-800">Status nicht verfügbar. Datenbankmigration und Jobs prüfen.</p> : !query.data ? <p>Status wird geladen.</p> : <>
      <p className="mt-1">{query.data.due_count.toLocaleString("de-DE")} fällige Aufgaben · {query.data.active.length ? query.data.active.map((item) => `${item.ticker}: ${groups[item.group] ?? item.group}`).join(", ") : "Kein Paket aktiv"}</p>
      {query.data.oldest_due_at && <p className="mt-1 text-xs">Älteste fällige Aufgabe: {new Date(query.data.oldest_due_at).toLocaleString("de-DE")}</p>}
      <details className="mt-3"><summary className="cursor-pointer font-medium">Datenbereiche und Wartezustände</summary>
        <ul className="mt-2 grid gap-2 sm:grid-cols-2">{query.data.groups.map((item) => <li key={`${item.group}:${item.status}`} className="border-l-2 border-teal-600 pl-3">
          <strong>{groups[item.group] ?? item.group}: {item.count.toLocaleString("de-DE")}</strong><br />{states[item.status] ?? item.status}
        </li>)}</ul>
      </details>
    </>}
  </section>;
}
