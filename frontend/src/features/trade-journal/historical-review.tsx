"use client";

import { useState } from "react";
import { LineChartCard } from "@/components/ui/line-chart-card";
import type { TradeJournalEntryDetail } from "@/lib/types/api";
import { historicalChartView } from "./historical-chart-data";

type RecordValue = Record<string, unknown>;
const record = (value: unknown): RecordValue => value && typeof value === "object" && !Array.isArray(value) ? value as RecordValue : {};
const records = (value: unknown): RecordValue[] => Array.isArray(value) ? value.map(record) : [];
const numeric = (value: unknown): number | null => typeof value === "number" && Number.isFinite(value) ? value : null;
const number = (value: number) => new Intl.NumberFormat("de-DE", { maximumFractionDigits: 2 }).format(value);
const date = (value: string) => { const parsed = new Date(`${value.slice(0, 10)}T12:00:00`); return Number.isNaN(parsed.valueOf()) ? "Nicht belegt" : new Intl.DateTimeFormat("de-DE", { dateStyle: "medium" }).format(parsed); };
const status = (value: unknown) => ({ available: "Belegt", partial: "Teilweise belegt", missing: "Daten fehlen", insufficient_history: "Historie zu kurz", neutral: "Neutral", limited: "Eingeschränkt" })[String(value) as "available"] || "Nicht belegt";
const categoryLabels: Record<string, string> = { technical: "Technik / relative Stärke", trend: "Trend / Durchschnitte", risk: "Überdehnung / Risiko", fundamental: "Fundamental" };

export function HistoricalSignals({ assessment, sellAssessment }: { assessment: RecordValue; sellAssessment?: RecordValue }) {
  const [showAll, setShowAll] = useState(false);
  const checks = records(assessment.checks);
  const states = Object.entries(record(assessment.chart_signal_states)).map(([label, value]) => ({ label, ...record(value) } as RecordValue));
  const additionalSignals = records(assessment.chart_signals).filter((signal) => signal.category === "negative" && !states.some((state) => state.label === signal.label));
  const negativeStates: RecordValue[] = [...states, ...additionalSignals.map((signal) => ({ ...signal, active: true, available: true }))];
  const failed = checks.filter((check) => check.passed === false);
  const active = negativeStates.filter((signal) => signal.active === true && signal.available === true);
  const missing = negativeStates.filter((signal) => signal.available !== true);
  const evaluation = record(sellAssessment?.evaluation);
  const sellFeatures = ["emergency_features", "defensive_features", "offensive_features"].flatMap((key) => records(evaluation[key]));
  const sellActive = sellFeatures.filter((feature) => feature.active === true);
  return <section className="space-y-4" aria-label="Historische Warnungen und Prüfungen">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div><h3 className="text-lg font-semibold text-[#172033]">Schwächen & Warnzeichen damals</h3><p className="mt-1 text-sm text-[#687386]">{failed.length} Kriterien nicht erfüllt oder nicht belegbar · {active.length} aktive negative Chart-Signale · {missing.length} Chart-Prüfungen ohne Daten</p></div>
      <button type="button" aria-pressed={showAll} onClick={() => setShowAll(!showAll)} className="rounded-lg border border-slate-300 px-3 py-2 text-sm font-semibold text-teal-800">{showAll ? "Nur Auffälligkeiten zeigen" : "Alle Prüfungen zeigen"}</button>
    </div>
    <p className="text-sm text-[#687386]">Auch Kriterien ohne formale Warnstufe und Punkteabzüge werden sichtbar. Eine fehlende Datenbasis bedeutet keine Entwarnung.</p>
    <div className="grid gap-3 lg:grid-cols-2">{Object.entries(categoryLabels).map(([category, label]) => {
      const items = checks.filter((check) => check.category === category && (showAll || check.passed === false));
      return <div key={category} className="rounded-xl border border-slate-200 p-4"><h4 className="mb-3 font-semibold text-[#172033]">{label}</h4>{items.length ? <ul className="space-y-3">{items.map((check, index) => <SignalRow key={index} label={String(check.label)} detail={String(check.detail || "")} badge={check.passed === true ? "Erfüllt" : check.severity === "critical" ? "Kritisches Kriterium" : check.severity === "warning" ? "Warnkriterium" : "Nicht erfüllt / nicht belegbar"} tone={check.passed === true ? "good" : "warning"} />)}</ul> : <p className="text-sm text-slate-500">{checks.some((check) => check.category === category) ? "Keine Auffälligkeit in den gespeicherten Prüfungen." : "Keine damaligen Prüfungen gespeichert."}</p>}</div>;
    })}</div>
    <div className="rounded-xl border border-slate-200 p-4"><h4 className="mb-3 font-semibold text-[#172033]">Negatives Chartverhalten</h4><ul className="grid gap-4 md:grid-cols-2">{negativeStates.filter((signal) => showAll || signal.active === true || signal.available !== true).map((signal, index) => <SignalRow key={index} label={String(signal.label)} detail={String(signal.detail || "")} badge={signal.available !== true ? "Nicht belegbar" : signal.active === true ? "Aktiv" : "Nicht aktiv"} tone={signal.available !== true ? "neutral" : signal.active === true ? "warning" : "good"} />)}</ul>{!negativeStates.length && <p className="text-sm text-slate-500">Keine damaligen Chart-Prüfungen gespeichert.</p>}{negativeStates.length > 0 && !active.length && !missing.length && !showAll && <p className="text-sm text-slate-500">Keine aktive Warnung in den {negativeStates.length} belegten Chart-Prüfungen.</p>}</div>
    {Array.isArray(assessment.warnings) && assessment.warnings.length > 0 && <details className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900"><summary className="cursor-pointer font-semibold">Zusammenfassende Aktienhinweise ({assessment.warnings.length})</summary><ul className="mt-3 list-disc space-y-2 pl-5">{assessment.warnings.map((warning, index) => <li key={index}>{String(warning)}</li>)}</ul></details>}
    {sellFeatures.length > 0 && <details className="rounded-xl border border-slate-200 p-4" open={sellActive.length > 0}><summary className="cursor-pointer font-semibold text-[#172033]">Verkaufsprüfungen dieser Position · {sellActive.length} aktiv / {sellFeatures.length} geprüft</summary><p className="my-3 text-sm text-slate-500">Gespeicherte Verkaufsbewertung bis {date(String(sellAssessment?.as_of))}. Diese Prüfungen berücksichtigen die Haltedauer seit Kauf; einzelne Linien oder Benchmarkphasen können noch fehlen.</p><ul className="grid gap-4 md:grid-cols-2">{sellFeatures.filter((feature) => showAll || feature.active === true).map((feature, index) => <SignalRow key={index} label={String(feature.label)} detail={`${feature.value} · ${feature.detail} · Schwelle: ${feature.threshold}`} badge={feature.active === true ? "Aktiv" : "Nicht ausgelöst"} tone={feature.active === true ? "warning" : "neutral"} />)}</ul>{!showAll && !sellActive.length && <p className="text-sm text-slate-500">Keine aktive Verkaufsprüfung. Über „Alle Prüfungen zeigen“ werden auch Werte, Schwellen und Datenlücken der übrigen Prüfungen sichtbar.</p>}</details>}
  </section>;
}

function SignalRow({ label, detail, badge, tone }: { label: string; detail: string; badge: string; tone: "good" | "warning" | "neutral" }) {
  return <li className="list-none text-sm"><div className="flex flex-wrap items-start gap-2"><span className="font-semibold text-[#304052]">{label}</span><span className={`rounded px-1.5 py-0.5 text-[11px] ${tone === "good" ? "bg-teal-50 text-teal-800" : tone === "warning" ? "bg-amber-50 text-amber-900" : "bg-slate-100 text-slate-600"}`}>{badge}</span></div><p className="mt-1 leading-5 text-[#687386]">{detail}</p></li>;
}

const componentLabels: Record<string, string> = {
  overall: "Gesamtscore", technical: "Technisch", fundamental: "Fundamental", chart: "Chartverhalten", moving_average: "Gleitende Durchschnitte",
  k4_rs_leadership: "Führungsstärke der RS-Linie", k13_rs_dynamics: "Dynamik der relativen Stärke", rs_rating: "RS-Rating", high_position: "Position zum Allzeit- / 52-Wochen-Hoch", up_down_volume: "Volumen an Gewinn- und Verlusttagen", cmf: "CMF / Akkumulation",
  fundamental_core: "Fundamentale Kernkriterien", k9_eps_sales_alignment: "Zusammenspiel von EPS und Umsatz", price_action_core: "Kurs- und Volumenverhalten", k35_down_week_quality: "Qualität der Verlustwochen", k38_hh_hl_good_close: "Höhere Hochs / Tiefs und Schlussposition",
  price_above_200_sma: "Kurs über 200-SMA", price_above_50_sma: "Kurs über 50-SMA", price_above_21_ema: "Kurs über 21-EMA", price_above_10_sma: "Kurs über 10-SMA", ma_order: "Ordnung der Durchschnitte", persistence: "Beständigkeit über den Linien", slope: "Richtung der Durchschnitte",
  above_21_ema: "RS über 21-EMA", above_50_sma: "RS über 50-SMA", rs_52w_high: "RS zum 52-Wochen-Hoch", white_space: "Abstand und Stabilität der RS-Linie", sequence: "Reihenfolge der RS-Zeiträume", acceleration: "Beschleunigung der RS", three_vs_six: "RS 3 Monate gegen 6 Monate", six_vs_twelve: "RS 6 Monate gegen 12 Monate"
};
const factLabels: Record<string, string> = {
  score: "Punkte", status: "Datenstatus", data_quality: "Datenqualität", data_coverage: "Datenabdeckung", available_weight: "Verfügbare Gewichtung", base_weight: "Basisgewicht", effective_weight: "Effektives Gewicht",
  cmf_20: "CMF über 20 Tage", rating: "Rating", ath_points: "Punkte am Allzeithoch", high_52w_points: "Punkte am 52-Wochen-Hoch", max_points: "Maximale Punkte", ratio: "Volumenverhältnis", threshold: "Schwelle", up_volume: "Volumen an Gewinntagen", down_volume: "Volumen an Verlusttagen", rs_3m: "RS 3 Monate", rs_6m: "RS 6 Monate", rs_12m: "RS 12 Monate",
  available_days_21: "Belegte Tage für 21-EMA", available_days_50: "Belegte Tage für 50-SMA", persistence_21_pct: "Tage über 21-EMA (%)", persistence_50_pct: "Tage über 50-SMA (%)", combined_persistence_pct: "Gewichtete Beständigkeit (%)", persistence_window_days: "Zeitraum der Beständigkeit (Tage)", new_rs_52w_high: "Neues RS-Hoch", distance_to_rs_52w_high_pct: "Abstand zum RS-Hoch (%)", available_days: "Belegte Tage", stability_score: "Stabilität (Punkte)", white_space_score: "Freiraum (Punkte)", current_separation: "Aktueller Abstand (Punkte)", distance_rs_to_21_pct: "RS-Abstand zum 21-EMA (%)", distance_rs_to_50_pct: "RS-Abstand zum 50-SMA (%)", positive_separation_ratio: "Anteil mit positivem Abstand", rs_line: "RS-Linie", rs_ema21: "21-EMA der RS", rs_sma50: "50-SMA der RS",
  legacy_core_score: "Kernbewertung (Punkte)", matched_quarters: "Verglichene Quartale", period: "Zeitraum", divergence_pp: "Abweichung (Prozentpunkte)", research_reason: "Prüfhinweis", research_reasons: "Prüfhinweise", research_trigger: "Weitere Prüfung angezeigt", eps_growth_yoy_pct: "EPS-Wachstum zum Vorjahr (%)", revenue_growth_yoy_pct: "Umsatzwachstum zum Vorjahr (%)", persistent_divergence: "Anhaltende Abweichung", persistent_divergence_quarters: "Quartale mit anhaltender Abweichung", noise_pct: "Toleranz (%)",
  negative_count: "Negative Signale im Score", positive_count: "Positive Signale im Score", scored_signal_keys: "Signale im Score", strong: "Starker Wochenschluss", higher_low: "Höheres Tief", higher_high: "Höheres Hoch", weeks_last_8: "Letzte 8 Wochen", closing_range_pct: "Schlussposition in der Handelsspanne (%)", weekly_return_pct: "Wochenrendite (%)", hh_hl_weeks_last_8: "Wochen mit höheren Hochs / Tiefs (von 8)", consecutive_hh_hl_weeks: "Folge höherer Hochs / Tiefs (Wochen)", strong_hh_hl_weeks_last_8: "Starke Wochen mit höheren Hochs / Tiefs (von 8)", down_weeks: "Verlustwochen", lookback_weeks: "Rückblick (Wochen)",
  ema21_direction: "Richtung 21-EMA", sma50_direction: "Richtung 50-SMA", ema21_change_pct: "Änderung 21-EMA (%)", sma50_change_pct: "Änderung 50-SMA (%)", flat_tolerance_pct: "Toleranz für Seitwärtsbewegung (%)", lookback_trading_days: "Rückblick (Handelstage)", ordered: "Durchschnitte aufsteigend geordnet", above_streak_days: "Tage in Folge darüber", below_streak_days: "Tage in Folge darunter", above_21_streak_days: "Tage in Folge über 21-EMA", above_50_streak_days: "Tage in Folge über 50-SMA", below_21_streak_days: "Tage in Folge unter 21-EMA", below_50_streak_days: "Tage in Folge unter 50-SMA", above: "Kurs über Durchschnitt", price: "Kurs", average: "Durchschnitt"
};
const label = (key: string) => componentLabels[key] || factLabels[key] || key.replaceAll("_", " ");

export function HistoricalScores({ assessment }: { assessment: RecordValue }) {
  const groups = ["overall", "technical", "fundamental", "chart", "moving_average"];
  const weak = groups.filter((group) => group !== "overall").flatMap((group) => Object.entries(record(record(assessment[`${group}_v2`]).components)).map(([key, value]) => ({ group, key, value: record(value) }))).filter(({ value }) => numeric(value.score) !== null && Number(value.score) < 100);
  return <section className="space-y-3" aria-label="Historische Score-Teilbewertungen"><h3 className="text-lg font-semibold text-[#172033]">Score-Teilbewertungen damals</h3><p className="text-sm text-[#687386]">Jeden Baustein öffnen, um Messwerte und Unterbewertungen zu sehen. Die effektive Gewichtung berücksichtigt verfügbare Daten. Punkteabzüge sind keine zusätzlichen formalen Warnungen.</p>
    {weak.length > 0 && <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900"><h4 className="font-semibold">Wo Punkte fehlen</h4><ul className="mt-2 grid gap-2 sm:grid-cols-2">{weak.map(({ group, key, value }) => <li key={`${group}-${key}`}>{label(key)}: <strong>{number(Number(value.score))} / 100</strong> · {number((100 - Number(value.score)) * (numeric(value.effective_weight) || 0))} Punkte Abzug im Bereich {label(group)}</li>)}</ul></div>}
    <div className="grid gap-3 lg:grid-cols-2">{groups.map((group) => { const value = record(assessment[`${group}_v2`]); return Object.keys(value).length ? <details key={group} className="rounded-xl border border-slate-200 p-4" open={group === "technical" || group === "chart"}><summary className="cursor-pointer font-semibold text-[#172033]">{label(group)} · {numeric(value.score) === null ? "Nicht belegbar" : `${number(Number(value.score))} / 100`} · {status(value.status)}</summary><p className="my-3 text-xs text-slate-500">Datenabdeckung: {numeric(value.data_coverage) === null ? "Nicht belegt" : `${number(Number(value.data_coverage) * 100)} %`}</p><ScoreComponents value={value} /></details> : null; })}</div>
    {!groups.some((group) => Object.keys(record(assessment[`${group}_v2`])).length) && <p className="text-sm text-slate-500">Für diesen historischen Stand sind keine Score-Bausteine gespeichert.</p>}
  </section>;
}

function ScoreComponents({ value }: { value: RecordValue }) {
  return <div className="space-y-2">{Object.entries(record(value.components)).map(([key, item]) => { const component = record(item); const raw = record(component.raw); return <details key={key} className="rounded-lg bg-slate-50 p-3"><summary className="cursor-pointer text-sm"><span className="font-medium text-[#304052]">{label(key)}</span><span className={`ml-2 font-semibold ${numeric(component.score) !== null && Number(component.score) < 70 ? "text-amber-800" : "text-slate-700"}`}>{numeric(component.score) === null ? "Nicht belegbar" : `${number(Number(component.score))} / 100`}</span><span className="mt-1 block text-xs text-slate-500">Basis {number((numeric(component.base_weight) || 0) * 100)} % · effektiv {number((numeric(component.effective_weight) || 0) * 100)} % · {status(component.status)}</span></summary><div className="mt-3 space-y-3">{Object.keys(record(raw.components)).length > 0 ? <ScoreComponents value={raw} /> : <Facts value={raw} />}{Object.keys(record(raw.raw)).length > 0 && <Facts value={record(raw.raw)} />}</div></details>; })}</div>;
}

function Facts({ value }: { value: RecordValue }) {
  const items = Object.entries(value).filter(([key]) => !["components", "weights", "raw", "mapping", "match_method", "thresholds_unchanged", "scored_signal_keys"].includes(key));
  if (!items.length) return <p className="text-xs text-slate-500">Keine weiteren Messwerte gespeichert.</p>;
  return <dl className="space-y-2 text-xs text-slate-600">{items.map(([key, item]) => <div key={key} className="break-words"><dt className="font-medium">{label(key)}</dt><dd className="mt-0.5">{Array.isArray(item) ? <div className="space-y-2">{item.map((child, index) => typeof child === "object" && child !== null ? <div key={index} className="border-l-2 border-slate-200 pl-3"><Facts value={record(child)} /></div> : <span className="mr-2" key={index}>{fact(child, key)}</span>)}</div> : typeof item === "object" && item !== null ? <div className="border-l-2 border-slate-200 pl-3"><Facts value={record(item)} /></div> : fact(item, key)}</dd></div>)}</dl>;
}

function fact(value: unknown, key: string): string {
  if (value === null || value === undefined) return "Nicht belegt";
  if (typeof value === "boolean") return value ? "Ja" : "Nein";
  if (typeof value === "number") return ["data_coverage", "available_weight", "base_weight", "effective_weight", "positive_separation_ratio"].includes(key) ? `${number(value * 100)} %` : number(value);
  if (key === "status") return status(value);
  return ({ up: "Steigend", down: "Fallend", flat: "Seitwärts", full: "Vollständig", partial: "Teilweise", missing: "Fehlt" })[String(value) as "up"] || String(value);
}

export function HistoricalTradeChart({ entry }: { entry: TradeJournalEntryDetail }) {
  const [retrospective, setRetrospective] = useState(false);
  const [period, setPeriod] = useState("position");
  const chart = entry.historical_chart;
  if (!chart) return null;
  const windowDays = period === "3m" ? 93 : period === "1m" ? 31 : period === "6m" ? 186 : null;
  const { points, markers, lastPriceDate } = historicalChartView(chart, retrospective, windowDays);
  const currencyFormat = (value: number) => `${number(value)} ${chart.currency}`;
  return <section className="space-y-3" aria-label="Historischer Chart mit Kauf und Verkauf"><div className="flex flex-wrap items-center justify-between gap-3"><h3 className="text-lg font-semibold text-[#172033]">Chart zum {entry.entry_type === "sell" ? "Verkauf" : entry.entry_type === "buy" ? "Kauf" : "Eintrag"}</h3><label className="flex items-center gap-2 text-sm text-slate-600">Zeitraum<select aria-label="Historischer Chartzeitraum" className="rounded-lg border p-2" value={period} onChange={(event) => setPeriod(event.target.value)}><option value="1m">1 Monat</option><option value="3m">3 Monate</option><option value="6m">6 Monate</option><option value="position">Gesamte Haltedauer</option></select></label></div>
    <div className="flex flex-wrap gap-2">{[{ value: false, label: "Vor der Ausführung bekannt" }, { value: true, label: "Ausführungstag im Rückblick" }].map((mode) => <button key={mode.label} type="button" aria-pressed={retrospective === mode.value} onClick={() => setRetrospective(mode.value)} className={`rounded-lg border px-3 py-2 text-sm font-semibold ${retrospective === mode.value ? "border-teal-700 bg-teal-50 text-teal-900" : "border-slate-200 text-slate-600"}`}>{mode.label}</button>)}</div>
    <p className="text-sm leading-6 text-slate-600">{retrospective ? `Tageskerzen bis ${date(chart.execution_date)}. Der vollständige Ausführungstag enthält auch Kursbewegungen nach deiner Ausführung. Die damalige Bewertung bleibt auf dem früheren Datenstand.` : `Nur abgeschlossene Tageskerzen bis ${date(chart.assessment_as_of)}. Am Ausführungstag steht ausschließlich die Datumsmarkierung; keine spätere Tageskerze fließt ein.`} Kurse in {chart.currency}; Brokerpreise stehen separat an den Markierungen. Intraday-Kurse sind nicht archiviert.</p>
    {chart.points.length > 0 ? <LineChartCard key={`${entry.id}-${retrospective}-${period}`} title={`${entry.ticker} · historischer Tageschart (${chart.currency})`} caption={`Letzte verfügbare Kerze ${lastPriceDate ? date(lastPriceDate) : "nicht belegt"} · Kauf K / Verkauf V · Volumen und gleitende Durchschnitte`} points={points} chartMode="candlestick" volumeKey="volume" showPreviousCloseChange series={[{ key: "close", label: "Schlusskurs", color: "#334155", formatter: currencyFormat }, { key: "sma10", label: "10-SMA", color: "#f59e0b", formatter: currencyFormat }, { key: "ema21", label: "21-EMA", color: "#8b5cf6", formatter: currencyFormat }, { key: "sma50", label: "50-SMA", color: "#2563eb", formatter: currencyFormat }, { key: "sma200", label: "200-SMA", color: "#d946ef", formatter: currencyFormat }]} markers={markers.map((marker) => ({ key: marker.entry_id || `${marker.entry_type}-${marker.date}`, date: marker.date, color: marker.entry_type === "buy" ? "#0f766e" : "#dc2626", code: marker.entry_type === "buy" ? "K" : "V", legendLabel: marker.entry_type === "buy" ? "Kaufdatum" : "Verkaufsdatum", label: `${marker.entry_type === "buy" ? "Kauf" : "Verkauf"}${marker.price === null ? "" : ` · ${number(marker.price)} ${marker.currency} (Brokerpreis)`}${marker.selected ? " · ausgewählte Ausführung" : ""}` }))} /> : <p className="rounded-lg bg-slate-50 p-4 text-sm text-slate-500">Keine historischen Kurse für diesen Zeitraum in der Datenbank.</p>}
    <ul className="flex flex-wrap gap-x-5 gap-y-2 text-sm">{markers.map((marker, index) => <li key={index} className={marker.entry_type === "buy" ? "text-teal-800" : "text-red-700"}><strong>{marker.entry_type === "buy" ? "K · Kauf" : "V · Verkauf"}</strong> {date(marker.date)}{marker.price === null ? "" : ` · ${number(marker.price)} ${marker.currency}`}{marker.selected ? " · ausgewählt" : ""}</li>)}</ul>
    {markers.length < chart.markers.length && <p className="text-xs text-slate-500">Frühere Ausführungen liegen außerhalb dieses Zeitraums. „Gesamte Haltedauer“ zeigt alle Kauf- und Verkaufsmarkierungen.</p>}
    {retrospective && chart.last_date !== chart.execution_date && <p className="text-sm text-amber-900">Für den Ausführungstag fehlt eine Tageskerze. Angezeigt werden die tatsächlich gespeicherten Kurse.</p>}
  </section>;
}
