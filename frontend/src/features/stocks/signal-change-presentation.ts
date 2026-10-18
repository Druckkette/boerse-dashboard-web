import type { StockSignalChange } from "../../lib/types/api";

export function signalChangePresentation(change: StockSignalChange): {
  title: string;
  tone: "bad" | "good" | "neutral";
} {
  const tone = change.effect === "deterioration" ? "bad"
    : change.effect === "improvement" ? "good" : "neutral";
  if (change.kind === "unchanged") return { title: "Unverändert", tone: "neutral" as const };
  if (change.source === "rule") {
    return { title: change.effect === "improvement" ? "Kriterium wieder erfüllt" : "Kriterium nicht mehr erfüllt", tone };
  }
  if (change.category === "positive") {
    return { title: change.kind === "resolved" ? "Stärkesignal entfallen" : "Neues Stärkesignal", tone };
  }
  if (change.category === "negative") {
    return { title: change.kind === "resolved" ? "Entschärft" : "Neues Warnsignal", tone };
  }
  return { title: change.kind === "resolved" ? "Entfallen" : "Neu", tone };
}
