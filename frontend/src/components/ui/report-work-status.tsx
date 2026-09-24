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
const reasonLabels: Record<string, string> = {
  waiting_sec_data: "SEC-Daten noch nicht verfügbar",
  waiting_yahoo_data: "Yahoo-Daten fehlen vorübergehend",
  waiting_fmp_fallback: "optionaler FMP-Ersatz wird später erneut geprüft",
  unsupported_taxonomy: "kein sicher zuordenbarer SEC-Finanzwert",
  missing_history: "ältere Prüfung ohne genaue Ursache; erneute Klassifizierung nötig",
  actual_missing_history: "vergleichbare veröffentlichte Perioden fehlen tatsächlich",
  insufficient_operating_history: "Unternehmen besitzt noch keine ausreichende veröffentlichte Historie",
  foreign_filer_reporting_structure: "ausländischer Emittent ohne vergleichbare US-Quartalsstruktur; Jahresdaten werden weiter genutzt",
  not_applicable_for_instrument_type: "Fundamentalkriterium für diesen Wertpapiertyp nicht anwendbar",
  non_operating_security: "keine operative Unternehmensaktie",
  spac_no_operating_history: "SPAC – operative Fundamentaldaten noch nicht sinnvoll verfügbar",
  predecessor_cik_gap: "historische Daten des Vorgänger-CIK noch nicht vollständig ausgewertet",
  predecessor_cik_history_merged: "Historie aus Vorgänger- und Nachfolger-CIK verbunden",
  unknown_data_gap: "Ursache der Datenlücke wird untersucht",
  rate_limited: "Datenquelle hat das Abruflimit erreicht; Wiederholung geplant",
  provider_rate_limited: "Datenquelle ist begrenzt; Abruf nach Cooldown geplant",
  provider_error: "Datenquelle vorübergehend nicht erreichbar",
};

function formatDate(value: string | null): string {
  return value ? new Date(value).toLocaleString("de-DE", { dateStyle: "medium", timeStyle: "short" }) : "–";
}

export function ReportWorkOverview({ data, compact = false }: { data: ReportWork; compact?: boolean }) {
  const byGroup = new Map<string, ReportWork["groups"]>();
  for (const item of data.groups) byGroup.set(item.group, [...(byGroup.get(item.group) ?? []), item]);
  const waiting = data.groups.reduce((sum, item) => sum + (item.status === "waiting_source" ? item.count : 0), 0);
  const waitingDue = data.groups.reduce((sum, item) => sum + (item.status === "waiting_source" ? item.due_count : 0), 0);
  const archiveAgeHours = data.sec_bulk_cache.fetched_at
    ? (new Date(data.generated_at).getTime() - new Date(data.sec_bulk_cache.fetched_at).getTime()) / 3_600_000
    : null;
  return <div className={compact ? "text-sm" : "mt-2 text-sm"}>
    <p><strong>{data.due_count.toLocaleString("de-DE")} jetzt fällig</strong>
      {data.due_count > 0 && data.oldest_due_at ? ` · älteste Fälligkeit: ${formatDate(data.oldest_due_at)}` : ""}
      {data.active.length ? ` · in Arbeit: ${data.active.map((item) => `${item.ticker} (${groupLabels[item.group] ?? item.group})`).join(", ")}` : " · aktuell kein Paket aktiv"}
    </p>
    <p className="mt-1 text-xs text-[#687386]">{waiting.toLocaleString("de-DE")} offene Prüfaufträge; {waitingDue.toLocaleString("de-DE")} davon jetzt zur erneuten Prüfung fällig. Nächster geplanter Termin: {formatDate(data.next_due_at)}.</p>
    <p className="mt-1 text-xs text-[#687386]">Live-Stand: {formatDate(data.generated_at)} · Abrufzahlen zählen seit 00:00 UTC.</p>
    <a className="mt-2 inline-block rounded border border-[#cbd5e1] px-3 py-1.5 font-medium text-[#172033] hover:bg-[#f1f5f9]" href={api.reportMissingCsvUrl()} download="fehlende-berichtsdaten.csv">Fehlende Daten als CSV exportieren</a>
    <details className="mt-3"><summary className="cursor-pointer font-medium">Datenbereiche und Wartezustände erklären</summary>
      <p className="mt-2 text-xs text-[#687386]">Die Zahlen zählen Prüfaufträge, keine verschiedenen Aktien. Eine Aktie kann mehrfach vorkommen. „Geprüft“ heißt: aktuell keine Arbeit offen. Folgebewertungen werden bei Datenänderungen neu angestoßen. Nur „jetzt fällig“ zählt die gerade anstehenden Prüfungen.</p>
      <ul className="mt-3 grid gap-3 sm:grid-cols-2">
        {[...byGroup].map(([group, items]) => {
          const count = (status: string) => items.filter((item) => item.status === status).reduce((sum, item) => sum + item.count, 0);
          const due = items.reduce((sum, item) => sum + item.due_count, 0);
          const checked = items.reduce((sum, item) => sum + item.checked_24h, 0);
          const next = items.map((item) => item.next_due_at).filter((value): value is string => !!value).sort()[0] ?? null;
          return <li key={group} className="rounded-lg border border-[#e3e8ef] p-3">
            <strong className="text-[#172033]">{groupLabels[group] ?? group}</strong>
            <p className="mt-1">{due.toLocaleString("de-DE")} jetzt fällig · {count("current").toLocaleString("de-DE")} {group === "assessment" ? "geprüft, Neubewertung bei Datenänderung" : "geprüft, Kontrolle geplant"} · {count("queued").toLocaleString("de-DE")} Erstprüfung geplant</p>
            <p className="mt-1 text-xs text-[#687386]">{checked.toLocaleString("de-DE")} verschiedene Prüfaufträge in den letzten 24 Stunden bearbeitet.</p>
            {count("waiting_source") > 0 && <p className="mt-1 text-amber-800">{count("waiting_source").toLocaleString("de-DE")} warten auf Daten: {missingExplanations[group] ?? "Quelldaten noch unvollständig"}.</p>}
            {items.filter((item) => item.status === "waiting_source" && item.reason_code && item.count).map((item) => <p key={item.reason_code} className="mt-1 text-xs text-amber-800">{item.count.toLocaleString("de-DE")}: {reasonLabels[item.reason_code] ?? item.reason_code}</p>)}
            {items.filter((item) => item.status === "current" && item.reason_code && item.count).map((item) => <p key={`current-${item.reason_code}`} className="mt-1 text-xs text-[#687386]">{item.count.toLocaleString("de-DE")}: {reasonLabels[item.reason_code] ?? item.reason_code}</p>)}
            {count("error") > 0 && <p className="mt-1 text-red-700">{count("error").toLocaleString("de-DE")} Abruffehler, Wiederholung geplant.</p>}
            {count("running") > 0 && <p className="mt-1">{count("running").toLocaleString("de-DE")} in Bearbeitung.</p>}
            {next && <p className="mt-1 text-xs text-[#687386]">Nächster Termin: {formatDate(next)}</p>}
          </li>;
        })}
      </ul>
      <p className="mt-3 text-xs text-[#687386]">Externe Abrufe seit 00:00 UTC: SEC {data.provider_usage.sec_requests ?? 0}, Yahoo {data.provider_usage.yahoo_requests ?? 0}, FMP {data.provider_usage.fmp_requests ?? 0}. SEC-Archiv: {data.sec_bulk_cache.available ? `letzter erfolgreicher Download ${formatDate(data.sec_bulk_cache.fetched_at ?? null)}` : "noch nicht verfügbar"}. Geplanter Download täglich um 10:30 Uhr Berliner Zeit.</p>
      <p className="mt-1 text-xs text-[#687386]">Durch Instrumententyp übersprungene potenzielle Abrufe: SEC {data.provider_usage.avoided_sec_requests ?? 0}, Yahoo {data.provider_usage.avoided_yahoo_fallbacks ?? 0}, FMP {data.provider_usage.avoided_fmp_fallbacks ?? 0}; übersprungene Ticker {data.provider_usage.instrument_type_skipped ?? 0}.</p>
      {archiveAgeHours !== null && archiveAgeHours > 30 && <p className="mt-1 text-xs text-amber-800">SEC-Archiv älter als 30 Stunden. Der vorhandene Cache bleibt nutzbar; geplanten Download und Worker-Logs prüfen.</p>}
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
