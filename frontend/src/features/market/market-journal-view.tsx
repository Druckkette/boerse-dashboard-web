"use client";

import { useId, useState, type ReactNode } from "react";
import { ChevronDown, CircleAlert, RotateCw, Zap } from "lucide-react";
import { LineChartCard } from "@/components/ui/line-chart-card";
import type { MarketAmpel, MarketAmpelLight } from "@/lib/types/api";
import { labelForStatus } from "./data-status";
import { MarketContextScoresPanel } from "./market-context-scores-panel";
import { confirmedMarketPoint, marketDate, marketHeadline, marketNumber, marketPercent, percentageDistance, powerTrendProgress } from "./market-journal-presentation";
import styles from "./market-journal.module.css";

export const marketDayOptions = [60, 90, 130, 200] as const;
export const marketIndexes = [
  { ticker: "^GSPC", label: "S&P500" },
  { ticker: "^IXIC", label: "NASDAQ" },
  { ticker: "^RUT", label: "Russell 2000" }
] as const;
export type MarketJournalTicker = (typeof marketIndexes)[number]["ticker"];

type MarketJournalProps = {
  data: MarketAmpel;
  days: (typeof marketDayOptions)[number];
  indexes: readonly (typeof marketIndexes)[number][];
  isFetching: boolean;
  updateFailed: boolean;
  onDaysChange: (days: (typeof marketDayOptions)[number]) => void;
  onRefresh: () => void;
  onTickerChange?: (ticker: MarketJournalTicker) => void;
};

export function MarketJournalView({ data, days, indexes, isFetching, onDaysChange, onRefresh, onTickerChange, updateFailed }: MarketJournalProps) {
  const confirmedDate = data.confirmed_as_of || data.as_of;
  const quote = data.chart_points.at(-1);
  const previous = data.chart_points.at(-2);
  const quoteChange = percentageDistance(quote?.close, previous?.close);
  const confirmed = confirmedMarketPoint(data);
  const previousClose = previous?.close;
  const chartPoints = data.chart_points.map(point => ({
    date: point.date, open: point.open, high: point.high, low: point.low, close: point.close,
    volume: point.volume, ema21: point.ema21, sma10: point.sma10, sma50: point.sma50,
    sma200: point.sma200, vol_sma50: point.vol_sma50, dist_52w_pct: point.dist_52w_pct
  }));
  return (
    <section className={styles.journal} aria-label="Marktampel und Kontext">
      <header className={styles.toolbar}>
        <div className={styles.heading}><h1>Marktampel</h1><span className={styles.mono}>{data.logic === "ibd" ? "IBD" : "Standard"} / {labelForStatus(data.data_status)}</span></div>
        <div className={styles.indexPicker} aria-label="Index auswählen">
          {indexes.map(index => <button key={index.ticker} type="button" aria-pressed={data.ticker === index.ticker} disabled={!onTickerChange} onClick={() => onTickerChange?.(index.ticker)}>{index.label}</button>)}
        </div>
      </header>
      {updateFailed ? <p className={styles.notices} role="alert">Aktualisierung fehlgeschlagen. Angezeigt wird der letzte erfolgreich geladene Datenstand.</p> : null}
      {data.component_errors?.length ? <p className={styles.notices} role="status">Teilweise verfügbar: {data.component_errors.join(" · ")}</p> : null}
      {data.powertrend.enabled ? <JournalPowertrend data={data} /> : null}
      <div className={styles.content}>
        <div className={styles.hero}>
          <section className={styles.position} aria-label="Bestätigte Marktphase">
            <div className={styles.phaseLabel} data-tone={data.phase_info.tone}><span className={styles.dot} aria-hidden="true" />{data.phase_info.label}</div>
            <h2 className={styles.headline}>{marketHeadline(data.phase_info.phase)}</h2>
            <p className={styles.action}>{data.phase_info.action}</p>
            <p className={styles.confirmed}>Bestätigt bis {marketDate(confirmedDate)}.{data.intraday ? " Der vorläufige Tageskurs ändert die bestätigte Ampel nicht." : " Nur abgeschlossene Handelstage bestätigen die Phase."}</p>
            <div className={styles.next}><h3 className={styles.eyebrow}>Was als Nächstes zählt</h3><p>{data.phase_info.next_step}</p></div>
            <JournalWarnings data={data} />
          </section>
          <section className={styles.quote} aria-label="Marktampel Indexchart">
            <div className={styles.quoteHead}>
              <h2>{data.name} <span className={styles.muted}>/ {data.ticker}</span></h2>
              <div className={styles.periods} aria-label="Chartzeitraum">
                {marketDayOptions.map(option => <button key={option} type="button" aria-pressed={days === option} onClick={() => onDaysChange(option)}>{option}T</button>)}
                <button type="button" aria-label="Marktampel aktualisieren" onClick={onRefresh} disabled={isFetching}><RotateCw size={14} className={isFetching ? "animate-spin" : undefined} /></button>
              </div>
            </div>
            <div className={`${styles.price} ${styles.mono}`}><strong>{marketNumber(quote?.close)}</strong><span data-tone={quoteChange == null ? "neutral" : quoteChange >= 0 ? "good" : "bad"}>{marketPercent(quoteChange)}</span></div>
            <p className={styles.quoteDate}>{marketDate(data.quote_as_of || quote?.date || data.as_of)} · {data.intraday ? "Vorläufiger Intraday-Kurs" : "Bestätigter Schlusskurs"}</p>
            <LineChartCard
              className={styles.chart}
              title={`${data.name} Trendwende-Ampel`}
              caption={`${data.phase_info.reason} Stand ${data.as_of}. ${data.message}`}
              hideTextHeader
              points={chartPoints}
              chartMode="candlestick"
              showPreviousCloseChange
              volumeKey="volume"
              markers={data.chart_markers}
              candleColors={{ up: "var(--mj-green)", down: "var(--mj-red)" }}
              readoutMode="hover"
              levels={[
                ...(previousClose != null ? [{ key: "previous_close", label: "Vortagesschluss", value: previousClose, color: "var(--mj-soft)" }] : []),
                ...(data.cycle.floor_mark != null ? [{ key: "floor", label: "Bodenmarke", value: data.cycle.floor_mark, color: "var(--mj-red)" }] : []),
                ...(data.cycle.startschuss_low != null ? [{ key: "startschuss", label: data.cycle.ftd_negated ? "FTD-Tief (negiert)" : "Startschuss-Tief", value: data.cycle.startschuss_low, color: data.cycle.ftd_negated ? "var(--mj-soft)" : "var(--mj-amber)" }] : [])
              ]}
              series={[
                { key: "ema21", label: "21-EMA", color: "var(--mj-ma21)" },
                { key: "sma50", label: "50-SMA", color: "var(--mj-ma50)" },
                { key: "sma200", label: "200-SMA", color: "var(--mj-ma200)" }
              ]}
              statusLabel={data.phase_info.label}
              statusTone={data.phase_info.tone}
            />
          </section>
        </div>
        <JournalMarkers data={data} />
        <JournalPhases lights={data.lights} />
        <details className={styles.rules}>
          <summary><span>Regeldefinitionen · {data.lights.length} Ampelzustände</span><ChevronDown size={15} aria-hidden="true" /></summary>
          <div className={styles.ruleGrid}>{data.lights.map(light => <div key={light.key} data-tone={light.tone}><h3>{light.label}{light.active ? <span>aktiv</span> : null}</h3><p>{light.rule}</p></div>)}</div>
        </details>
        <details className={styles.rules}>
          <summary><span>Zyklusdetails & Trendabstände</span><ChevronDown size={15} aria-hidden="true" /></summary>
          <div className={styles.cycleDetails}>
            <p><strong>Definition:</strong> {data.phase_info.reason}</p>
            <p><strong>Letzte Statusänderung:</strong> {data.phase_info.last_changed_at ? `${marketDate(data.phase_info.last_changed_at)}: ${data.phase_info.last_change_reason || data.phase_info.label}` : "Im geladenen Kursfenster noch kein Phasenwechsel. Ankertag und Bodenmarke sind separate Zyklusmarken."}</p>
            {data.cycle.diagnostics.length ? <p>{data.cycle.diagnostics.join(" · ")}</p> : null}
            {data.cycle.startschuss_date ? <p>FTD-Datum: {marketDate(data.cycle.startschuss_date)} · {data.cycle.ftd_negated ? "Negiert, historisches Signal" : "Gültige Bestätigung"}</p> : null}
            {confirmed ? <p>Basis der bestätigten Struktur: {marketDate(confirmed.date)}, Schlusskurs {marketNumber(confirmed.close)}.</p> : null}
            <div className={styles.distanceTable}>{data.distance_tiles.map(tile => <div key={tile.label}><span>{tile.label}</span><strong>{tile.value}</strong><small>{tile.indicator} · {tile.detail}</small></div>)}</div>
            {data.change_cards.filter(card => !card.title.startsWith("Heute ") && !["Distribution", "EW-Breite", "Volatilität", "Trendwende-Ampel"].includes(card.title)).map(card => <p key={card.title}>{card.title}: {card.value} · {card.detail} {card.detail2} {card.detail3}</p>)}
          </div>
        </details>
        <MarketContextScoresPanel ticker={data.ticker} asOf={confirmedDate} />
        <footer className={styles.footer}><span>Bestätigt bis {marketDate(confirmedDate)}</span><span>Marktjournal · {data.logic === "ibd" ? "IBD" : "Standard"} · {data.intraday ? "Tageskurs vorläufig" : "Tageskurs bestätigt"}</span></footer>
      </div>
    </section>
  );
}

export function JournalPowertrend({ data }: { data: MarketAmpel }) {
  const powertrend = data.powertrend;
  const progress = powerTrendProgress(powertrend);
  const confirmed = confirmedMarketPoint(data);
  const averageGap = percentageDistance(confirmed?.ema21, confirmed?.sma50);
  const checks = [
    { label: "Tagestief > 21-EMA", value: `${Math.min(powertrend.low_above_21_streak, 10)}/10`, count: 10, filled: Math.min(powertrend.low_above_21_streak, 10) },
    { label: "21-EMA > 50-SMA", value: `${Math.min(powertrend.ema21_over_50_streak, 5)}/5`, count: 5, filled: Math.min(powertrend.ema21_over_50_streak, 5) },
    { label: "50-SMA steigt", value: powertrend.sma50_rising_1d ? "Ja" : "Nein", count: 1, filled: Number(powertrend.sma50_rising_1d) },
    { label: "Tag positiv / neutral", value: powertrend.positive_or_flat_day ? "Ja" : "Nein", count: 1, filled: Number(powertrend.positive_or_flat_day) }
  ];
  return <section className={styles.power} aria-label="Powertrend Status" data-tone={progress.tone}>
    <div className={styles.powerIdentity}>
      <div className={styles.powerName}><Zap size={15} aria-hidden="true" /><h2>Powertrend</h2></div>
      <div className={`${styles.powerState} ${styles.mono}`}>{progress.label}</div>
      <p className={styles.powerDate}>{powertrend.start_date && powertrend.state !== "off" ? `Seit ${marketDate(powertrend.start_date)}` : `Stand ${marketDate(data.confirmed_as_of || data.as_of)}`}{powertrend.state === "under_pressure" && powertrend.pressure_since ? ` · Unter Druck seit ${marketDate(powertrend.pressure_since)}` : ""}</p>
    </div>
    <div className={styles.powerChecks}>{checks.map(check => <div key={check.label} className={styles.powerCheck}><span>{check.label}</span><strong>{check.value}</strong><div className={styles.streak} aria-hidden="true">{Array.from({ length: check.count }, (_, i) => <i key={i} data-filled={i < check.filled} />)}</div></div>)}</div>
    <div className={styles.powerProgress}>
      {powertrend.state !== "off" ? <p>{progress.summary}</p> : null}
      <p><strong>{progress.nextLabel}{powertrend.state !== "on" ? ` · ${progress.passed}/4 Bedingungen gleichzeitig erfüllt` : ""}</strong></p>
      {progress.missing.length ? <ul>{progress.missing.map(item => <li key={item}>{item}</li>)}</ul> : powertrend.state !== "on" ? <p>Alle angezeigten Startbedingungen sind erfüllt; eine bestätigte Aktivierung beziehungsweise Erholung ist noch nicht gemeldet.</p> : null}
      {powertrend.state !== "off" ? <p>{progress.endRule}</p> : null}
      {averageGap != null ? <p className={styles.mono}>21-EMA zur 50-SMA: {marketPercent(averageGap)} · Bestätigter Stand</p> : null}
      <details className={styles.powerRules}><summary>Powertrend-Regeln & letzter Statusgrund</summary>{powertrend.state === "off" ? <><p>{progress.summary}</p><p>{progress.endRule}</p></> : null}<p>{progress.pressureRule}</p><p>{powertrend.reason}</p><p>Für Aktivierung und Erholung zählen nur vollständige, bestätigte Handelstage. Der Powertrend überspringt keine Ampelphase.</p></details>
    </div>
  </section>;
}

function JournalWarnings({ data }: { data: MarketAmpel }) {
  const active = data.warning_checks.filter(check => check.active_warning);
  if (!active.length) return <p className={styles.confirmed}>Keine aktiven Warnzeichen</p>;
  return <details className={styles.warnings}>
    <summary><span><CircleAlert size={15} aria-hidden="true" />{data.warning_count} aktive Warnzeichen</span><ChevronDown size={15} aria-hidden="true" /></summary>
    <ul>{active.map(check => <li key={check.code || check.label}><strong>{check.label}</strong><p>{check.detail}</p></li>)}</ul>
    <p className={styles.phaseNote}>Die Warnzeichen ergänzen die Marktphase. Preis- und Strukturregeln bleiben maßgeblich.</p>
  </details>;
}

function JournalMarkers({ data }: { data: MarketAmpel }) {
  const cycle = data.cycle;
  const confirmed = confirmedMarketPoint(data);
  const quote = data.chart_points.at(-1);
  const floorDistance = cycle.floor_distance_pct ?? percentageDistance(confirmed?.close, cycle.floor_mark);
  const startDistance = cycle.startschuss_distance_pct ?? percentageDistance(confirmed?.close, cycle.startschuss_low);
  const intradayFloorDistance = data.intraday ? percentageDistance(quote?.close, cycle.floor_mark) : null;
  return <section className={styles.markers} aria-label="Marken und Marktstruktur">
    <div className={styles.sectionHead}><h2>Zyklus & Marktstruktur</h2><span>Bestätigt bis {marketDate(data.confirmed_as_of || data.as_of)}</span></div>
    <dl className={styles.markerGrid}>
      <Marker label="Ankertag" value={marketDate(cycle.anchor_date)} empty={!cycle.anchor_date} note={cycle.anchor_date && cycle.anchor_current === false ? "Historischer letzter Wert" : undefined} />
      <Marker label="Bodenmarke" value={marketNumber(cycle.floor_mark)} empty={cycle.floor_mark == null} note={cycle.floor_current === false && cycle.floor_mark != null ? "Historischer letzter Wert" : undefined}>
        {floorDistance != null ? <span className={styles.distance} data-tone={floorDistance >= 0 ? "good" : "bad"}><span>{marketPercent(floorDistance)}</span><span className={styles.markerNote}>zum bestätigten Schluss</span></span> : null}
        {intradayFloorDistance != null ? <span className={styles.markerNote}>Intraday {marketPercent(intradayFloorDistance)}</span> : null}
      </Marker>
      <Marker label={cycle.ftd_negated ? "FTD-Tief (negiert)" : "Startschuss-Tief"} value={cycle.startschuss_low == null ? "Noch nicht gesetzt" : marketNumber(cycle.startschuss_low)} empty={cycle.startschuss_low == null} note={cycle.ftd_negated ? "Negiert · keine gültige Bestätigung" : cycle.startschuss_current === false && cycle.startschuss_low != null ? "Historischer letzter Wert" : undefined}>
        {startDistance != null ? <span className={styles.distance} data-tone={cycle.ftd_negated ? "neutral" : startDistance >= 0 ? "good" : "bad"}>{marketPercent(startDistance)}</span> : null}
      </Marker>
      <Marker label="MA-Ordnung" value={cycle.ma_order == null ? "Nicht bewertbar" : cycle.ma_order ? "Korrekt" : "Gestört"} empty={cycle.ma_order == null} />
      <Marker label="Marktstruktur" value={cycle.market_structure === "up" ? "Höhere Hochs/Tiefs" : cycle.market_structure === "down" ? "Tiefere Hochs/Tiefs" : cycle.market_structure === "mixed" ? "Gemischt" : "Noch offen"} />
      <Marker label="Aufwärtstrend-Hoch" value={cycle.uptrend_high == null ? "Noch nicht gesetzt" : marketNumber(cycle.uptrend_high)} empty={cycle.uptrend_high == null} />
    </dl>
    {cycle.ftd_intraday_undercut && !cycle.ftd_negated ? <p className={styles.phaseNote}>FTD-Tief intraday unterschritten; der bestätigte Schlusskurs hält die Marke. Keine dauerhafte FTD-Negation.</p> : null}
    {cycle.ftd_negated ? <p className={styles.phaseNote}>Startschuss/FTD negiert. Der Rallyversuch bleibt aktiv, solange die Bodenmarke hält.</p> : null}
  </section>;
}

function Marker({ label, value, children, empty, note }: { label: string; value: string; children?: ReactNode; empty?: boolean; note?: string }) {
  return <div><dt>{label}</dt><dd data-empty={empty || undefined}>{value}</dd>{children}{note ? <small className={styles.markerNote}>{note}</small> : null}</div>;
}

function JournalPhases({ lights }: { lights: MarketAmpelLight[] }) {
  const [selected, setSelected] = useState<string | null>(null);
  const detailId = useId();
  const main = lights.filter(light => ["rot", "gelb_startschuss", "gruen", "aufwaertstrend"].includes(light.key));
  const branches = lights.filter(light => !main.includes(light));
  const chosen = lights.find(light => light.key === selected);
  const labels: Record<string, string> = { rot: "Korrektur", gelb_startschuss: "Startschuss", gruen: "Bestätigung", aufwaertstrend: "Etablierter Trend" };
  if (!lights.length) return null;
  return <section className={styles.phases} aria-label="Ampelphasen und Übergänge">
    <div className={styles.sectionHead}><h2>Der Weg durch die Marktphasen</h2><span>Phase anklicken für die geltende Regel</span></div>
    <div className={styles.route}>{main.map(light => <button key={light.key} type="button" className={styles.phase} aria-current={light.active ? "step" : undefined} aria-pressed={selected === light.key} aria-controls={detailId} aria-label={`Regeldefinition ${light.label}`} data-tone={light.tone} onClick={() => setSelected(selected === light.key ? null : light.key)}><span className={styles.rail} aria-hidden="true"><i /></span><span className={styles.eyebrow}>{light.label}</span><strong>{labels[light.key]}</strong><small>{light.active ? "Hier steht der Markt" : light.key === "gelb_startschuss" ? "Möglicher Start einer neuen Rally" : "Nur bei weiterer Bestätigung"}</small></button>)}</div>
    <div className={styles.branches}>{branches.map(light => <button key={light.key} type="button" className={styles.branch} aria-current={light.active ? "step" : undefined} aria-pressed={selected === light.key} aria-controls={detailId} aria-label={`Regeldefinition ${light.label}`} data-tone={light.tone} onClick={() => setSelected(selected === light.key ? null : light.key)}><span aria-hidden="true">↳</span><div><strong>{light.label}{light.active ? " · aktiv" : ""}</strong><small>{light.key === "gelb_rally_unter_druck" ? "Rückschlag nach Startschuss oder Grün" : "Rückschlag im bestätigten Aufwärtstrend"}</small></div></button>)}</div>
    <div id={detailId} aria-live="polite" hidden={!chosen}>{chosen ? <div className={styles.phaseDetail}><strong>{chosen.label}{chosen.active ? " · aktiv" : ""}</strong><p>{chosen.rule}</p></div> : null}</div>
    <p className={styles.phaseNote}>Regelabhängige Übergänge, keine Prognose. Harte Brüche können zurück zu Rot führen.</p>
  </section>;
}
