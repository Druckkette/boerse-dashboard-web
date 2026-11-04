"use client";

import { useQuery } from "@tanstack/react-query";
import { ChevronDown } from "lucide-react";
import { api } from "@/lib/api/client";
import type { MarketContextScore, MarketContextScores, MarketScoreCriterion } from "@/lib/types/api";
import { marketDate, marketNumber } from "./market-journal-presentation";
import { useMarketRefetchInterval } from "./query-timing";
import styles from "./market-journal.module.css";

export function MarketContextScoresPanel({ ticker, asOf }: { ticker: string; asOf: string }) {
  const refetchInterval = useMarketRefetchInterval();
  const query = useQuery({
    queryKey: ["market-context-scores", ticker, asOf],
    queryFn: () => api.marketContextScores(ticker, asOf),
    enabled: Boolean(asOf),
    staleTime: 60_000,
    refetchInterval
  });
  if (!query.data || query.data.ticker !== ticker || query.data.as_of !== asOf) {
    return <section id="context-scores" className={styles.context}>
      <div className={styles.contextIntro}><h2>Kontext zur Ampel</h2><p role="status">{query.isError ? "Kontext-Kennzahlen nicht verfügbar. Die bestätigte Trendampel wird oben angezeigt." : query.data ? `Für die bestätigte Sitzung ${marketDate(asOf)} liegt noch kein passender Kontext-Datenstand vor.` : "Kontext-Kennzahlen werden geladen …"}</p></div>
    </section>;
  }
  return <ContextScoresView data={query.data} updateFailed={query.isError} />;
}

export function ContextScoresView({ data, updateFailed = false }: { data: MarketContextScores; updateFailed?: boolean }) {
  return <section id="context-scores" aria-label="Informationsscores zur Marktphase" className={styles.context}>
    <div className={styles.contextIntro}>
      <h2>Kontext zur Ampel</h2>
      <p>Die fünf Kennzahlen ergänzen die Marktphase. Sie verändern weder die Trendampel noch ihre Handlung.</p>
      <p>{data.ticker} · Stand {marketDate(data.as_of)}<br />Punkte von 100 · Kennzahl für Details anklicken</p>
    </div>
    <div className={styles.contextScores}>{data.scores.map(score => <ContextScoreRow key={score.key} item={score} />)}</div>
    <div className={styles.contextNotes}>
      <p>Unter 40: schwach · 40 bis unter 65: gemischt · ab 65: konstruktiv. Höhere Werte beschreiben günstigere Bedingungen. Die Gewichte sind ein erklärbarer Startentwurf.</p>
      {updateFailed ? <p role="status">Aktualisierung nicht verfügbar; angezeigt wird der letzte erfolgreich geladene Datenstand.</p> : null}
      {data.notes.length > 0 ? <details><summary>Hinweise zum Datenstand ({data.notes.length})</summary><ul>{data.notes.map(note => <li key={note}>{note}</li>)}</ul></details> : null}
    </div>
  </section>;
}

function ContextScoreRow({ item }: { item: MarketContextScore }) {
  return <article className={styles.score} aria-label={`${item.title} Informationsscore`}>
    <details>
      <summary className={styles.scoreSummary} aria-label={`${item.title}: Beiträge & Regeln`}>
        <span className={styles.scoreName}>{item.title}</span>
        <ScoreBar score={item.score} label={`${item.title} Score`} />
        <span className={styles.scoreNumber}>{marketNumber(item.score)}</span>
        <span className={styles.scoreStatus}>{item.status}</span>
        <ChevronDown size={14} aria-hidden="true" />
      </summary>
      <div className={styles.scoreDetails}>
        <p>{item.scope}</p>
        <p>{item.message}</p>
        {item.data_status !== "complete" ? <p>{item.score == null ? "Gesamtwert nicht bewertbar" : "Teilweise bewertbar"} · Bewertete Beiträge {marketNumber(item.coverage_pct)} %</p> : null}
        <p>Unterscore = gewichteter Mittelwert der bewertbaren Kriterien. Für die Kennzahl zählt jedes Gruppengewicht nur im Umfang seiner verfügbaren Beiträge. Fehlende Beiträge erhalten keinen Malus; bei weniger als 50 % bewertbarer Gewichtung bleibt der Gesamtwert offen.</p>
        {item.subscores.map(sub => <section key={sub.key} className={styles.subscore}>
          <div className={styles.subscoreHead}><h3><strong>{sub.label}</strong></h3><span>{sub.weight ? `${marketNumber(sub.weight)} % Gewicht` : "Nur Information"} · {marketNumber(sub.score)} / 100</span></div>
          {sub.weight > 0 ? <ScoreBar score={sub.score} label={`${item.title}: ${sub.label}`} /> : null}
          {sub.data_status !== "complete" ? <p className={styles.phaseNote}>{sub.score == null ? "Nicht bewertbar" : "Teilwerte fehlen"}</p> : null}
          {sub.criteria.map(criterion => <CriterionContribution key={criterion.id} item={criterion} />)}
        </section>)}
      </div>
    </details>
  </article>;
}

function CriterionContribution({ item }: { item: MarketScoreCriterion }) {
  const label = item.evaluation === "missing" ? "Nicht bewertbar" : item.evaluation === "info" ? "Nur Information" : item.evaluation === "not_applicable" ? "Aktuell nicht anwendbar" : `${marketNumber(item.score)} / 100`;
  return <div className={styles.criterion}>
    <strong>{item.id} · {item.label}</strong>
    <p>{item.value}</p>
    <div className={styles.criterionMeta}><span>Gewicht {marketNumber(item.weight)}</span><span>{label}</span></div>
    {item.contribution != null ? <p>Anteil am Unterscore: {marketNumber(item.contribution)} Punkte</p> : null}
    <p>{item.rule}</p>
    {item.explanation ? <p>{item.explanation}</p> : null}
  </div>;
}

function ScoreBar({ score, label }: { score: number | null; label: string }) {
  return <span role={score == null ? undefined : "meter"} aria-label={label} aria-valuemin={score == null ? undefined : 0} aria-valuemax={score == null ? undefined : 100} aria-valuenow={score ?? undefined} className={styles.scoreTrack}><span style={{ width: `${score == null ? 0 : Math.max(0, Math.min(score, 100))}%` }} /></span>;
}
