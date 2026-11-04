import type { MarketAmpel, MarketAmpelPowerTrend } from "@/lib/types/api";

export function marketNumber(value: number | null | undefined, digits = 2) {
  return value == null || !Number.isFinite(value) ? "—" : new Intl.NumberFormat("de-DE", { maximumFractionDigits: digits }).format(value);
}

export function marketPercent(value: number | null | undefined) {
  if (value == null || !Number.isFinite(value)) return "—";
  return `${value > 0 ? "+" : ""}${marketNumber(value)} %`;
}

export function marketDate(value: string | null | undefined) {
  if (!value) return "Noch nicht gesetzt";
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  return match ? `${match[3]}.${match[2]}.${match[1]}` : value;
}

export function percentageDistance(value: number | null | undefined, reference: number | null | undefined) {
  if (value == null || reference == null || !Number.isFinite(value) || !Number.isFinite(reference) || reference <= 0) return null;
  return (value / reference - 1) * 100;
}

export function confirmedMarketPoint(data: MarketAmpel) {
  const confirmedDate = data.confirmed_as_of || data.as_of;
  return data.chart_points.filter(point => point.date <= confirmedDate).at(-1);
}

export function marketHeadline(phase: string) {
  switch (phase) {
    case "rot": return "Korrektur.";
    case "gelb_startschuss": return "Startschuss.";
    case "gruen": return "Bestätigung.";
    case "aufwaertstrend": return "Aufwärtstrend.";
    case "gelb_rally_unter_druck": return "Rally unter Druck.";
    case "gelb_trend_unter_druck": return "Trend unter Druck.";
    default: return "Marktphase offen.";
  }
}

export function powerTrendProgress(powertrend: MarketAmpelPowerTrend) {
  const lowDays = Math.max(0, 10 - powertrend.low_above_21_streak);
  const averageDays = Math.max(0, 5 - powertrend.ema21_over_50_streak);
  const missing = [
    ...(lowDays ? [`Tagestief noch ${lowDays} ${lowDays === 1 ? "weiteren Handelstag" : "weitere Handelstage"} in Folge strikt über der 21-EMA`] : []),
    ...(averageDays ? [`21-EMA noch ${averageDays} ${averageDays === 1 ? "weiteren Handelstag" : "weitere Handelstage"} in Folge strikt über der 50-SMA`] : []),
    ...(!powertrend.sma50_rising_1d ? ["50-SMA steigt gegenüber dem vorherigen Handelstag"] : []),
    ...(!powertrend.positive_or_flat_day ? ["Schlusskurs mindestens auf Vortagesniveau"] : [])
  ];
  const active = powertrend.state === "on";
  const pressure = powertrend.state === "under_pressure";
  return {
    label: active ? "Aktiv" : pressure ? "Unter Druck" : "Aus",
    tone: active ? "good" as const : pressure ? "warning" as const : "neutral" as const,
    passed: 4 - missing.length,
    missing: active ? [] : missing,
    nextLabel: active ? "Was den Powertrend beendet" : pressure ? "Was zur Erholung fehlt" : "Was zur Aktivierung fehlt",
    summary: active
      ? "Der Powertrend ist intakt. Kürzere aktuelle Startzähler beenden ihn nicht."
      : pressure
        ? "Der Powertrend besteht formal weiter. Für die Erholung müssen die vier Startbedingungen wieder gleichzeitig erfüllt sein."
        : "Die vier Startbedingungen müssen am selben vollständigen, bestätigten Handelstag erfüllt sein.",
    endRule: "Abschaltung erst, wenn die 21-EMA strikt unter die 50-SMA fällt. Gleichstand beendet den Powertrend nicht.",
    pressureRule: "Unter Druck bei drei aufeinanderfolgenden Schlusskursen unter der 21-EMA oder einem Schlusskurs mehr als 0,5 ATR21 unter der 50-SMA."
  };
}
