"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api/client";

type ReportWork = Awaited<ReturnType<typeof api.reportWork>>;

const groupLabels: Record<string, string> = {
  statements: "Geschäftsberichte (EPS / Umsatz / ROE)", beta: "Beta",
  sec13f: "Institutionelle Beteiligungen (13F)", filings: "Neue SEC-Berichte", assessment: "Folgebewertungen",
};
const missingExplanations: Record<string, string> = {
  statements: "EPS- oder Umsatzhistorie bzw. erwartete Berichtsperiode fehlt noch",
  beta: "Beta fehlt beim Anbieter oder es gibt noch zu wenig gemeinsame Kurstage mit SPY",
  assessment: "Kursverlauf ist noch zu kurz oder nicht bewertbar",
  sec13f: "SEC-Archiv lieferte noch keine verwertbaren Daten",
  filings: "SEC-Index lieferte noch keine verwertbaren Daten",
};

function formatDate(value: string | null): string {
  return value ? new Date(value).toLocaleString("de-DE", { dateStyle: "medium", timeStyle: "short" }) : "–";
}

export function ReportWorkOverview({ data, compact = false }: { data: ReportWork; compact?: boolean }) {
  const byGroup = new Map<string, ReportWork["groups"]>();
  for (const item of data.groups) byGroup.set(item.group, [...(byGroup.get(item.group) ?? []), item]);
  const waiting = data.groups.reduce((sum, item) => sum + (item.status === "waiting_source" ? item.count : 0), 0);
  return <div className={compact ? "text-sm" : "mt-2 text-sm"}>
    <p><strong>{data.due_count.toLocaleString("de-DE")} jetzt fällig</strong>
      {data.due_count > 0 && data.oldest_due_at ? ` · älteste Fälligkeit: ${formatDate(data.oldest_due_at)}` : ""}
      {data.active.length ? ` · in Arbeit: ${data.active.map((item) => `${item.ticker} (${groupLabels[item.group] ?? item.group})`).join(", ")}` : " · aktuell kein Paket aktiv"}
    </p>
    <p className="mt-1 text-xs text-[#687386]">Nächster geplanter Check: {formatDate(data.next_due_at)}. {waiting.toLocaleString("de-DE")} Prüfungen warten auf weitere Quelldaten; sie werden zum geplanten Termin erneut versucht.</p>
    <details className="mt-3"><summary className="cursor-pointer font-medium">Datenbereiche und Wartezustände erklären</summary>
      <p className="mt-2 text-xs text-[#687386]">Jede Zahl zählt Prüfungen in einem Datenbereich. Eine Aktie kann in mehreren Bereichen stehen. „Geprüft“ bedeutet: letzter Check erfolgreich, derzeit keine Arbeit offen. „Wartet auf Daten“ bedeutet: Quelle geprüft, aber noch keine ausreichenden Daten. Nur die separat genannte Zahl „jetzt fällig“ bezeichnet aktuell abzuarbeitende Prüfungen.</p>
      <ul className="mt-3 grid gap-3 sm:grid-cols-2">
        {[...byGroup].map(([group, items]) => {
          const count = (status: string) => items.find((item) => item.status === status)?.count ?? 0;
          const due = items.reduce((sum, item) => sum + item.due_count, 0);
          const next = items.map((item) => item.next_due_at).filter((value): value is string => !!value).sort()[0] ?? null;
          return <li key={group} className="rounded-lg border border-[#e3e8ef] p-3">
            <strong className="text-[#172033]">{groupLabels[group] ?? group}</strong>
            <p className="mt-1">{due.toLocaleString("de-DE")} jetzt fällig · {count("current").toLocaleString("de-DE")} geprüft · {count("queued").toLocaleString("de-DE")} Erstprüfung geplant</p>
            {count("waiting_source") > 0 && <p className="mt-1 text-amber-800">{count("waiting_source").toLocaleString("de-DE")} warten auf Daten: {missingExplanations[group] ?? "Quelldaten noch unvollständig"}.</p>}
            {count("error") > 0 && <p className="mt-1 text-red-700">{count("error").toLocaleString("de-DE")} Abruffehler, Wiederholung geplant.</p>}
            {count("running") > 0 && <p className="mt-1">{count("running").toLocaleString("de-DE")} in Bearbeitung.</p>}
            {next && <p className="mt-1 text-xs text-[#687386]">Nächster Termin: {formatDate(next)}</p>}
          </li>;
        })}
      </ul>
    </details>
  </div>;
}

export function ReportWorkStatus({ enabled = true }: { enabled?: boolean }) {
  const query = useQuery({ queryKey: ["report-work"], queryFn: api.reportWork, enabled, refetchInterval: enabled ? 15_000 : false });
  return <section className="border-y border-[#e3e8ef] py-4 text-[#475569]" aria-label="Berichtspflege" aria-live="polite">
    <h2 className="font-semibold text-[#172033]">Berichtspflege im Hintergrund</h2>
    {query.error ? <p role="status" className="mt-2 text-amber-800">Status nicht verfügbar. Datenbankmigration und Jobs prüfen.</p> : !query.data ? <p>Status wird geladen.</p> : <ReportWorkOverview data={query.data} />}
  </section>;
}
