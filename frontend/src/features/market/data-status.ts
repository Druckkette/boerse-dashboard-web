import type { Tone } from "@/lib/types/api";

export type MarketDataSource = "database" | "synthetic_fixture" | "missing";
export type MarketDataStatus = "fresh" | "stale" | "missing" | "fallback";

export function labelForSource(source?: MarketDataSource | "synthetic_fallback") {
  if (source === "database") return "gespeichert";
  if (source === "synthetic_fixture") return "Fixture";
  if (source === "synthetic_fallback") return "Fallback";
  if (source === "missing") return "Cache fehlt";
  return "unbekannt";
}

export function labelForStatus(status?: MarketDataStatus) {
  if (status === "fresh") return "frisch";
  if (status === "stale") return "veraltet";
  if (status === "fallback") return "Fallback";
  if (status === "missing") return "fehlt";
  return "unbekannt";
}

export function toneForSource(source?: MarketDataSource | "synthetic_fallback"): Tone {
  if (source === "database") return "good";
  if (source === "synthetic_fixture") return "neutral";
  if (source === "synthetic_fallback") return "warning";
  if (source === "missing") return "warning";
  return "neutral";
}

export function toneForStatus(status?: MarketDataStatus): Tone {
  if (status === "fresh") return "good";
  if (status === "stale") return "warning";
  if (status === "fallback") return "warning";
  if (status === "missing") return "bad";
  return "neutral";
}
