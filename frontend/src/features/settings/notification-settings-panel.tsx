"use client";

import { useState, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api/client";
import { formatDateTime } from "@/lib/format";
import { StatusChip } from "@/components/ui/status-chip";
import type { NotificationMaKey, NotificationMode, NotificationPreferences, NotificationPriority, NotificationRepeat, NotificationSession } from "@/lib/types/api";
import { defaultNotificationPreferences, notificationDeliveryLabels, notificationMaLabels, updateNotificationMa } from "./notification-preferences";

const inputClass = "mt-1 min-h-11 w-full rounded-lg border border-[#d8e1ea] bg-white px-3 py-2 text-sm text-[#172033] focus:outline-[#0f766e]";
const groupClass = "grid gap-3 sm:grid-cols-2 xl:grid-cols-3";
const summaryCategories: Array<[NotificationPreferences["summary"]["categories"][number], string]> = [
  ["ma", "Durchschnittslinien"], ["score", "Gesamtscore"], ["verdict", "Aktienurteil"], ["stop", "Stopps"], ["atr", "ATR-Alarme"],
];

export function NotificationSettingsPanel({ value, onChange }: { value: NotificationPreferences; onChange: (next: NotificationPreferences) => void }) {
  function patch<K extends keyof NotificationPreferences>(key: K, next: Partial<NotificationPreferences[K]>) {
    onChange({ ...value, [key]: { ...(value[key] as object), ...next } });
  }
  return <section className="dashboard-section space-y-5" aria-label="Benachrichtigungen einstellen">
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div><h2 className="text-base font-semibold">Welche Nachrichten möchtest du erhalten?</h2>
        <p className="mt-1 max-w-3xl text-sm leading-6 text-[#687386]">Wähle je Anlass Aus, Tagesübersicht oder Sofort. Änderungen werden erst mit „Änderungen speichern“ übernommen. Die Zeitzone für Versandzeiten stellst du unter Ruhezeiten ein.</p></div>
      <button type="button" className="app-button" onClick={() => onChange(defaultNotificationPreferences())}>Empfohlene Werte übernehmen</button>
    </div>
    {!value.summary.enabled && <p className="app-notice">Die Tagesübersicht ist ausgeschaltet. Anlässe mit „Tagesübersicht“ bleiben dann im Protokoll sichtbar und werden nicht per Pushover gesendet.</p>}

    <div className="space-y-3">
      <h3 className="font-semibold">Durchschnittslinien</h3>
      <p className="text-sm text-[#687386]">Bruch, Rückeroberung und weitere Kursverluste lassen sich für jede Linie getrennt einstellen. Bei „Sofort“ werden Schlusskurssignale nach Bestätigung auch direkt nach Börsenschluss zugestellt. Eigene Versandfenster und Ruhezeiten gelten weiterhin.</p>
      {(Object.keys(notificationMaLabels) as NotificationMaKey[]).map(key => {
        const ma = value.ma[key], label = notificationMaLabels[key];
        const update = (next: Partial<typeof ma>) => onChange(updateNotificationMa(value, key, next));
        return <fieldset key={key} className="min-w-0 rounded-xl border border-[#e3e8ef] bg-[#f9fbfd] p-4">
          <legend className="px-1 text-sm font-semibold">{label}</legend>
          <div className={groupClass}>
            <Mode label={`${label} · Bruch`} value={ma.break_mode} onChange={break_mode => update({ break_mode })} />
            <Mode label={`${label} · Rückeroberung`} value={ma.recovery_mode} onChange={recovery_mode => update({ recovery_mode })} />
            <Mode label={`${label} · Weitere Verschlechterung`} value={ma.worsening_mode} onChange={worsening_mode => update({ worsening_mode })} />
          </div>
          <details className="mt-3">
            <summary className="cursor-pointer py-1 text-sm font-semibold text-[#0f766e]">Schwellen und Bestätigung für {label}</summary>
            <div className={`${groupClass} mt-3`}>
              <Select label={`${label} · Bestätigung`} value={ma.confirmation} onChange={confirmation => update({ confirmation })} options={[["intraday", "Für einige Minuten bestätigt"], ["close", "Erst zum Handelsschluss"]]} />
              <NumberControl label={`${label} · Bestätigung (Minuten)`} value={ma.confirmation_minutes} min={1} max={1440} disabled={ma.confirmation === "close"} onChange={confirmation_minutes => update({ confirmation_minutes })} />
              <Select label={`${label} · Abstand messen in`} value={ma.distance_unit} onChange={distance_unit => update({ distance_unit })} options={[["atr", "ATR"], ["pct", "Prozent"]]} />
              <NumberControl label={`${label} · Mindestabstand (${ma.distance_unit === "atr" ? "ATR" : "%"})`} value={ma.min_distance} min={0.01} max={20} step={0.01} onChange={min_distance => update({ min_distance })} />
              <NumberControl label={`${label} · Weitere Verschlechterung ab (ATR)`} value={ma.worsening_atr} min={0.01} max={20} step={0.1} onChange={worsening_atr => update({ worsening_atr })} />
              <NumberControl label={`${label} · Sofortmeldungen je Tag`} value={ma.max_per_day} min={0} max={100} onChange={max_per_day => update({ max_per_day })} hint="Je Aktie und Linie; 0 bedeutet unbegrenzt." />
              <Session label={`${label} · Handelszeiten`} value={ma.session} onChange={session => update({ session })} />
              <Priority label={`${label} · Priorität`} value={ma.priority} onChange={priority => update({ priority })} />
            </div>
          </details>
        </fieldset>;
      })}
    </div>

    <Group title="Stopp erreicht" description="Der erste Stoppalarm kann sofort kommen. Lege fest, wann derselbe Stopp erneut warnen darf.">
      <Mode label="Stopp · Versand" value={value.stop.mode} onChange={mode => patch("stop", { mode })} />
      <Repeat label="Stopp · Erneut warnen" value={value.stop.repeat} onChange={repeat => patch("stop", { repeat })} />
      <NumberControl label="Stopp · Wiederholen nach (Minuten)" value={value.stop.repeat_minutes} min={1} max={1440} disabled={value.stop.repeat !== "interval"} onChange={repeat_minutes => patch("stop", { repeat_minutes })} />
      <NumberControl label="Stopp · Erholung über dem Stopp (%)" value={value.stop.recovery_pct} min={0.01} max={20} step={0.1} disabled={value.stop.repeat !== "recovery"} onChange={recovery_pct => patch("stop", { recovery_pct })} />
      <NumberControl label="Stopp · Erholung bestätigt (Minuten)" value={value.stop.recovery_minutes} min={1} max={1440} disabled={value.stop.repeat !== "recovery"} onChange={recovery_minutes => patch("stop", { recovery_minutes })} />
      <Session label="Stopp · Handelszeiten" value={value.stop.session} onChange={session => patch("stop", { session })} />
      <Priority label="Stopp · Priorität" value={value.stop.priority} onChange={priority => patch("stop", { priority })} />
    </Group>

    <Group title="ATR-Alarme" description="Die ATR-Schwelle und der Referenzkurs stehen im Positionsmonitor. Eine zusätzliche Eskalation kann einen deutlich größeren Verlust melden.">
      <Mode label="ATR · Versand" value={value.atr.mode} onChange={mode => patch("atr", { mode })} />
      <Repeat label="ATR · Erneut warnen" value={value.atr.repeat} onChange={repeat => patch("atr", { repeat })} />
      <NumberControl label="ATR · Wiederholen nach (Minuten)" value={value.atr.repeat_minutes} min={1} max={1440} disabled={value.atr.repeat !== "interval"} onChange={repeat_minutes => patch("atr", { repeat_minutes })} />
      <NumberControl label="ATR · Erholt bei Verlust unter (ATR)" value={value.atr.recovery_atr} min={0} max={10} step={0.1} disabled={value.atr.repeat !== "recovery"} onChange={recovery_atr => patch("atr", { recovery_atr })} />
      <NumberControl label="ATR · Erholung bestätigt (Minuten)" value={value.atr.recovery_minutes} min={1} max={1440} disabled={value.atr.repeat !== "recovery"} onChange={recovery_minutes => patch("atr", { recovery_minutes })} />
      <Toggle label="Zusätzliche ATR-Eskalation aktiv" checked={value.atr.escalation_enabled} onChange={escalation_enabled => patch("atr", { escalation_enabled })} />
      <NumberControl label="ATR · Eskalation ab (ATR)" value={value.atr.escalation_atr} min={0.5} max={20} step={0.1} disabled={!value.atr.escalation_enabled} onChange={escalation_atr => patch("atr", { escalation_atr })} />
      <Session label="ATR · Handelszeiten" value={value.atr.session} onChange={session => patch("atr", { session })} />
      <Priority label="ATR · Priorität" value={value.atr.priority} onChange={priority => patch("atr", { priority })} />
    </Group>

    <Group title="Gesamtscore und Aktienurteil" description="Kleine Schwankungen müssen keine Einzelmeldung auslösen. Verbesserungen und Verschlechterungen lassen sich getrennt zulassen.">
      <Mode label="Gesamtscore · Versand" value={value.assessment.score_mode} onChange={score_mode => patch("assessment", { score_mode })} />
      <Mode label="Aktienurteil · Versand" value={value.assessment.verdict_mode} onChange={verdict_mode => patch("assessment", { verdict_mode })} />
      <NumberControl label="Scoreänderung ab (Punkte)" value={value.assessment.score_min_change} min={1} max={100} onChange={score_min_change => patch("assessment", { score_min_change })} />
      <Toggle label="Verbesserungen melden" checked={value.assessment.notify_improvements} onChange={notify_improvements => patch("assessment", { notify_improvements })} />
      <Toggle label="Verschlechterungen melden" checked={value.assessment.notify_deteriorations} onChange={notify_deteriorations => patch("assessment", { notify_deteriorations })} />
      <Session label="Bewertung · Handelszeiten" value={value.assessment.session} onChange={session => patch("assessment", { session })} />
      <Priority label="Bewertung · Priorität" value={value.assessment.priority} onChange={priority => patch("assessment", { priority })} />
    </Group>

    <Group title="Nachrichten bündeln" description="Mehrere Anlässe derselben Aktie werden gesammelt. Ein Tageslimit bremst besonders unruhige Handelstage.">
      <Toggle label="Nachrichten je Aktie bündeln" checked={value.grouping.enabled} onChange={enabled => patch("grouping", { enabled })} />
      <NumberControl label="Sammelzeit (Minuten)" value={value.grouping.window_minutes} min={1} max={1440} disabled={!value.grouping.enabled} onChange={window_minutes => patch("grouping", { window_minutes })} />
      <NumberControl label="Sofortmeldungen je Aktie und Tag" value={value.grouping.max_immediate_per_ticker_day} min={0} max={100} onChange={max_immediate_per_ticker_day => patch("grouping", { max_immediate_per_ticker_day })} hint="0 bedeutet unbegrenzt." />
      <Toggle label="Stopps umgehen Sammelzeit und Tageslimit" checked={value.grouping.stop_bypass} onChange={stop_bypass => patch("grouping", { stop_bypass })} />
      <Toggle label="ATR-Eskalationen umgehen Sammelzeit und Tageslimit" checked={value.grouping.atr_escalation_bypass} onChange={atr_escalation_bypass => patch("grouping", { atr_escalation_bypass })} />
    </Group>

    <Group title="Tagesübersicht" description="Eine kompakte Nachricht fasst die ausgewählten Anlässe zusammen. Weitere Details bleiben im Dashboard.">
      <Toggle label="Tagesübersicht aktiv" checked={value.summary.enabled} onChange={enabled => patch("summary", { enabled })} />
      <TimeControl label="Tagesübersicht um" value={value.summary.time} onChange={time => patch("summary", { time })} />
      <NumberControl label="Aktien in der Tagesübersicht" value={value.summary.max_tickers} min={1} max={50} onChange={max_tickers => patch("summary", { max_tickers })} />
      <Toggle label="Bereits sofort gemeldete Anlässe aufnehmen" checked={value.summary.include_sent} onChange={include_sent => patch("summary", { include_sent })} />
      <Toggle label="Nur Änderungen aufnehmen" checked={value.summary.only_changes} onChange={only_changes => patch("summary", { only_changes })} />
      <Priority label="Tagesübersicht · Priorität" value={value.summary.priority} onChange={priority => patch("summary", { priority })} />
      <fieldset className="min-w-0 sm:col-span-2 xl:col-span-3"><legend className="mb-2 text-sm font-medium">Anlässe in der Tagesübersicht</legend><div className="flex flex-wrap gap-3">
        {summaryCategories.map(([key, label]) => <Toggle key={key} label={label} checked={value.summary.categories.includes(key)} onChange={checked => patch("summary", { categories: checked ? [...value.summary.categories, key] : value.summary.categories.filter(item => item !== key) })} />)}
      </div></fieldset>
    </Group>

    <Group title="Ruhezeiten und Handelszeiten" description="Regulärer Börsenhandel berücksichtigt die Börse der Aktie, Feiertage und die Zeitumstellung. Alle Handelszeiten schließen die Vor- und Nachbörse ein. Eigene Zeiten gelten für Anlässe mit der Auswahl „Eigene Zeiten“.">
      <Select label="Zeitzone für Versandzeiten" value={value.timezone} onChange={timezone => onChange({ ...value, timezone })} options={[["Europe/Berlin", "Deutschland"], ["America/New_York", "US-Ostküste"], ["UTC", "UTC"], ...(!["Europe/Berlin", "America/New_York", "UTC"].includes(value.timezone) ? [[value.timezone, value.timezone] as [string, string]] : [])]} />
      <Toggle label="Ruhezeit aktiv" checked={value.quiet.enabled} onChange={enabled => patch("quiet", { enabled })} />
      <TimeControl label="Ruhezeit von" value={value.quiet.start} onChange={start => patch("quiet", { start })} />
      <TimeControl label="Ruhezeit bis" value={value.quiet.end} onChange={end => patch("quiet", { end })} />
      <Toggle label="Stopps dürfen die Ruhezeit unterbrechen" checked={value.quiet.stop_bypass} onChange={stop_bypass => patch("quiet", { stop_bypass })} />
      <Toggle label="ATR-Eskalationen dürfen die Ruhezeit unterbrechen" checked={value.quiet.atr_escalation_bypass} onChange={atr_escalation_bypass => patch("quiet", { atr_escalation_bypass })} />
      <TimeControl label="Eigene Handelszeit von" value={value.custom_session.start} onChange={start => patch("custom_session", { start })} />
      <TimeControl label="Eigene Handelszeit bis" value={value.custom_session.end} onChange={end => patch("custom_session", { end })} />
      <p className="text-xs leading-5 text-[#687386] sm:col-span-2 xl:col-span-3">Ein neuer Überwachungstag beginnt um 07:30 Uhr deutscher Zeit. Zurückgehaltene Anlässe und der Grund erscheinen im Protokoll.</p>
    </Group>
  </section>;
}

export function NotificationDeliveryPanel({ settingsDirty }: { settingsDirty: boolean }) {
  const queryClient = useQueryClient();
  const log = useQuery({ queryKey: ["pushover-delivery-log"], queryFn: api.pushoverDeliveryLog, staleTime: 30_000 });
  const [visible, setVisible] = useState(10);
  const [status, setStatus] = useState("all");
  const [ticker, setTicker] = useState("");
  const [rearmKind, setRearmKind] = useState<"stop" | "atr">("stop");
  const rearm = useMutation({
    mutationFn: (symbol: string) => rearmKind === "stop" ? api.rearmStopNotification(symbol) : api.rearmAtrNotification(symbol),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["pushover-delivery-log"] }),
  });
  const entries = (log.data?.entries ?? []).filter(item => status === "all" || item.status === status).slice(0, 100);
  const validTicker = /^[A-Z0-9^][A-Z0-9.^=_-]{0,31}$/.test(ticker.trim());
  return <section className="dashboard-section space-y-4" aria-label="Benachrichtigungsprotokoll">
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div><h2 className="text-base font-semibold">Benachrichtigungsprotokoll</h2><p className="mt-1 text-sm text-[#687386]">Zuletzt geprüfte Anlässe mit Versandstatus und Begründung. Die Anzeige ist auf die letzten 100 passenden Einträge begrenzt.</p></div>
      <button type="button" className="app-button" disabled={log.isFetching} onClick={() => { void log.refetch(); }}>{log.isFetching ? "Lädt…" : "Protokoll aktualisieren"}</button>
    </div>
    <Select label="Protokoll filtern" value={status} onChange={next => { setStatus(next); setVisible(10); }} options={[["all", "Alle Zustände"], ...Object.entries(notificationDeliveryLabels)]} />
    {log.isLoading ? <p role="status" className="text-sm">Protokoll wird geladen…</p> : log.isError ? <p role="alert" className="text-sm text-[#c2413b]">Das Protokoll ist gerade nicht erreichbar. Bitte erneut laden.</p> : entries.length === 0 ? <p className="text-sm text-[#687386]">Keine passenden Einträge vorhanden.</p> : <ol className="space-y-2">
      {entries.slice(0, visible).map((item, index) => <li key={`${item.alert_id ?? item.timestamp}-${index}`} className="rounded-lg border border-[#e3e8ef] bg-[#f9fbfd] p-3">
        <div className="flex flex-wrap items-center justify-between gap-2"><b className="min-w-0 break-words text-sm">{item.title || (item.ticker ? `${item.ticker} · ${kindLabel(item.kind)}` : kindLabel(item.kind))}</b><StatusChip tone={item.status === "sent" ? "good" : item.status === "failed" ? "bad" : "neutral"}>{notificationDeliveryLabels[item.status]}</StatusChip></div>
        <p className="mt-1 text-xs text-[#687386]">{formatDateTime(item.timestamp)}{item.ticker && item.title ? ` · ${item.ticker}` : ""}</p>
        <p className="mt-2 break-words text-sm leading-5">{item.detail || item.reference_label || "Keine weitere Begründung hinterlegt."}</p>
        {item.message && <details className="mt-2"><summary className="cursor-pointer text-xs font-semibold text-[#0f766e]">Nachricht ansehen</summary><p className="mt-2 whitespace-pre-wrap break-words text-xs leading-5 text-[#687386]">{item.message}</p></details>}
      </li>)}
    </ol>}
    {entries.length > visible && <button type="button" className="app-button" onClick={() => setVisible(Math.min(100, visible + 20))}>Weitere Einträge anzeigen</button>}
    <details className="border-t border-[#e3e8ef] pt-4">
      <summary className="cursor-pointer text-sm font-semibold text-[#0f766e]">Stopp- oder ATR-Warnung manuell erneut scharfstellen</summary>
      <p className="mt-2 text-sm leading-6 text-[#687386]">Für eine Aktie, deren Warnung bereits gemeldet wurde. Beim nächsten gültigen Signal darf wieder eine Nachricht entstehen. Diese Aktion sendet selbst keine Nachricht.</p>
      <div className="mt-3 flex flex-wrap items-end gap-3"><Select label="Warnung erneut scharfstellen" value={rearmKind} disabled={rearm.isPending} onChange={next => { setRearmKind(next); rearm.reset(); }} options={[["stop", "Stoppwarnung"], ["atr", "ATR-Warnung"]]} /><label className="block min-w-0 text-sm font-medium">Ticker für erneute Warnung<input className={inputClass} type="text" autoCapitalize="characters" autoComplete="off" maxLength={32} disabled={rearm.isPending} value={ticker} onChange={event => { setTicker(event.target.value.toUpperCase().trim()); rearm.reset(); }} placeholder="z. B. MRNA" /></label>
        <button type="button" className="app-button min-h-11" disabled={!validTicker || settingsDirty || rearm.isPending} onClick={() => rearm.mutate(ticker.trim())}>{rearm.isPending ? "Wird scharfgestellt…" : `${rearmKind === "stop" ? "Stoppwarnung" : "ATR-Warnung"} erneut scharfstellen`}</button></div>
      {settingsDirty && <p className="mt-2 text-xs text-[#687386]">Bitte die offenen Einstellungsänderungen zuerst speichern oder verwerfen.</p>}
      {rearm.isSuccess && <p role="status" className="mt-2 text-sm text-[#0f766e]">{rearm.data.count > 0 ? `Warnung für ${rearm.data.ticker} erneut scharfgestellt.` : `Kein gespeicherter ${rearmKind === "stop" ? "Stoppalarm" : "ATR-Alarm"} für ${rearm.data.ticker} vorhanden.`}</p>}
      {rearm.isError && <p role="alert" className="mt-2 text-sm text-[#c2413b]">{rearm.error instanceof Error ? rearm.error.message : "Die Warnung konnte nicht erneut scharfgestellt werden."}</p>}
    </details>
  </section>;
}

function kindLabel(kind?: string) {
  return ({ stop: "Stopp erreicht", atr: "ATR-Alarm", atr_escalation: "ATR-Eskalation", ma_break: "Linie unterschritten", ma_recovery: "Linie zurückerobert", ma_worsening: "Weitere Verschlechterung", score: "Gesamtscore", verdict: "Aktienurteil", digest: "Tagesübersicht", summary: "Tagesübersicht" } as Record<string, string>)[kind ?? ""] ?? "Benachrichtigung";
}
function Group({ title, description, children }: { title: string; description: string; children: ReactNode }) {
  return <details open={title === "Stopp erreicht" || title === "ATR-Alarme"} className="min-w-0 border-t border-[#e3e8ef] pt-4"><summary className="cursor-pointer py-1 text-sm font-semibold">{title}</summary><p className="mb-3 mt-2 text-sm leading-6 text-[#687386]">{description}</p><div className={groupClass}>{children}</div></details>;
}
function Select<T extends string>({ label, value, options, disabled, onChange }: { label: string; value: T; options: Array<[T, string]>; disabled?: boolean; onChange: (value: T) => void }) {
  return <label className="block min-w-0 text-sm font-medium">{label}<select aria-label={label} className={inputClass} value={value} disabled={disabled} onChange={event => onChange(event.target.value as T)}>{options.map(([key, text]) => <option key={key} value={key}>{text}</option>)}</select></label>;
}
function Mode(props: { label: string; value: NotificationMode; onChange: (value: NotificationMode) => void }) {
  return <Select {...props} options={[["off", "Aus"], ["digest", "Tagesübersicht"], ["immediate", "Sofort"]]} />;
}
function Session(props: { label: string; value: NotificationSession; onChange: (value: NotificationSession) => void }) {
  return <Select {...props} options={[["regular", "Regulärer Börsenhandel"], ["all", "Alle Handelszeiten"], ["custom", "Eigene Zeiten"]]} />;
}
function Repeat(props: { label: string; value: NotificationRepeat; onChange: (value: NotificationRepeat) => void }) {
  return <Select {...props} options={[["daily", "Höchstens einmal je Überwachungstag"], ["manual", "Erst nach manuellem Scharfstellen"], ["recovery", "Nach bestätigter Erholung"], ["interval", "Nach einer Wartezeit"]]} />;
}
function Priority({ label, value, onChange }: { label: string; value: NotificationPriority; onChange: (value: NotificationPriority) => void }) {
  return <Select label={label} value={String(value)} onChange={next => onChange(Number(next) as NotificationPriority)} options={[["-1", "Leise"], ["0", "Normal"], ["1", "Hoch"]]} />;
}
function Toggle({ label, checked, onChange }: { label: string; checked: boolean; onChange: (checked: boolean) => void }) {
  return <label className="flex min-h-11 min-w-0 items-center justify-between gap-3 rounded-lg border border-[#e3e8ef] bg-[#f9fbfd] px-3 py-2 text-sm"><span>{label}</span><input className="size-4 shrink-0 accent-[#0f766e]" type="checkbox" checked={checked} onChange={event => onChange(event.target.checked)} /></label>;
}
function NumberControl({ label, value, min, max, step = 1, disabled = false, hint, onChange }: { label: string; value: number; min: number; max: number; step?: number; disabled?: boolean; hint?: string; onChange: (value: number) => void }) {
  return <label className="block min-w-0 text-sm font-medium">{label}<input aria-label={label} type="number" className={`${inputClass} disabled:opacity-50`} value={value} min={min} max={max} step={step} disabled={disabled} onChange={event => { const next = event.target.valueAsNumber; if (Number.isFinite(next)) onChange(Math.max(min, Math.min(max, step === 1 ? Math.round(next) : next))); }} />{hint && <span className="mt-1 block text-xs font-normal text-[#687386]">{hint}</span>}</label>;
}
function TimeControl({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
  return <label className="block min-w-0 text-sm font-medium">{label}<input aria-label={label} type="time" className={inputClass} value={value} onChange={event => { if (event.target.value) onChange(event.target.value); }} /></label>;
}
