export function formatNumber(value?: number | null, digits = 2) {
  if (typeof value !== "number" || !Number.isFinite(value)) return "–";
  return new Intl.NumberFormat("de-DE", {
    minimumFractionDigits: 0,
    maximumFractionDigits: digits
  }).format(value);
}

export function formatPercent(value?: number | null, digits = 1, signed = true) {
  if (typeof value !== "number" || !Number.isFinite(value)) return "–";
  const prefix = signed && value > 0 ? "+" : "";
  return `${prefix}${formatNumber(value, digits)}%`;
}

export function formatMoney(value?: number | null, currency = "USD", digits = 2) {
  if (typeof value !== "number" || !Number.isFinite(value)) return "–";
  return new Intl.NumberFormat("de-DE", {
    style: "currency",
    currency,
    minimumFractionDigits: 0,
    maximumFractionDigits: digits
  }).format(value);
}

export function formatDateTime(value?: string | null) {
  if (!value) return "–";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return new Intl.DateTimeFormat("de-DE", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit"
  }).format(parsed);
}

export function portfolioStatusLabel(status: "ok" | "watch" | "risk" | "sell") {
  return { ok: "Intakt", watch: "Beobachten", risk: "Risiko", sell: "Verkaufen" }[status];
}

export function qualityLabel(status: "trusted" | "limited" | "blocked") {
  return { trusted: "Verlässlich", limited: "Eingeschränkt", blocked: "Daten prüfen" }[status];
}
