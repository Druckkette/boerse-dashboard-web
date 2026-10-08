/** Display-only wording; never use this text to evaluate a rule. */
export function assessmentDisplayText(text: string): string {
  return text
    .replace(/MA-Ordnung \(21>50>200\)/g, "Durchschnitte in Aufwärtstrend-Reihenfolge")
    .replace(/21\s*>\s*50\s*>\s*200/g, "21-Tage-Linie über 50-Tage-Linie über 200-Tage-Linie")
    .replace(/>=|≥/g, " mindestens ")
    .replace(/<=|≤/g, " höchstens ")
    .replace(/>(?=\s*[$+−\-\d])/g, " mehr als ")
    .replace(/<(?=\s*[$+−\-\d])/g, " weniger als ")
    .replace(/\bin (\d+)T\b/g, "in $1 Handelstagen")
    .replace(/\b(\d+)T\b/g, "$1 Handelstage")
    .replace(/\bVol\./g, "Volumen")
    .replace(/\bvs\b\.?/g, "gegenüber")
    .replace(/\s{2,}/g, " ")
    .replace(/\(\s+/g, "(")
    .trim();
}
