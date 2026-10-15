import { assessmentDisplayText } from "./assessment-display-text";

const decimal = (value: string) => Number(value).toLocaleString("de-DE", { maximumFractionDigits: 2 });

/** Format saved explanations without reconstructing missing comparison values. */
export function dailyChangeDisplay(text: string): { label: string; value: string } {
  const score = /^(Gesamtscore|Technischer Score) \+(\d+(?:\.\d+)?)$/.exec(text);
  if (score) return { label: score[1], value: `+${decimal(score[2])} Punkte` };
  const rs = /^RS (\d+) → (\d+)$/.exec(text);
  if (rs) return { label: "RS-Rating", value: `${rs[1]} → ${rs[2]}` };
  const relative = /^5T vs\. SPY \+(\d+(?:\.\d+)?) %$/.exec(text);
  if (relative) return { label: "Vorsprung zum S&P-500-ETF · 5 Handelstage", value: `+${decimal(relative[1])} Prozentpunkte` };
  return { label: assessmentDisplayText(text), value: "" };
}

export function dailyWarningDisplay(text: string): { title: string; detail: string; informational: boolean } {
  const rs = /^RS-Bewertung\s*(?:>=|≥)\s*(\d+):\s*Aktuell\s*(\d+)\s*$/.exec(text);
  if (rs && Number(rs[2]) < Number(rs[1])) {
    return {
      title: `RS-Rating ${rs[2]} · Kriterium ab ${rs[1]} noch nicht erfüllt`,
      detail: `Für dieses zusätzliche Stärkekriterium fehlen ${Number(rs[1]) - Number(rs[2])} Punkte. Das RS-Rating vergleicht die Kursstärke mit anderen Aktien.`,
      informational: true,
    };
  }
  return { title: assessmentDisplayText(text), detail: "", informational: false };
}

export function dailyExplanations(row: { reasons: string[]; positive_changes: string[] }) {
  const changes = [...new Set(row.positive_changes)];
  const changeText = new Set(changes.map(assessmentDisplayText));
  return {
    changes: changes.filter(text => !text.startsWith("Neu: ")),
    signals: changes.filter(text => text.startsWith("Neu: ")).map(text => assessmentDisplayText(text.slice(5))),
    reasons: [...new Set(row.reasons)].filter(text => !changeText.has(assessmentDisplayText(text))).map(assessmentDisplayText),
  };
}
