export const BUY_STRENGTH_WEEK_OPTIONS = [1, 2, 3, 4, 5, 6] as const;
export const DEFAULT_BUY_STRENGTH_WEEKS = 3;

export function normalizeBuyStrengthWeeks(value: unknown): number {
  const raw = Array.isArray(value) ? value[0] : value;
  const parsed = Number(raw);
  if (BUY_STRENGTH_WEEK_OPTIONS.includes(parsed as (typeof BUY_STRENGTH_WEEK_OPTIONS)[number])) {
    return parsed;
  }
  return DEFAULT_BUY_STRENGTH_WEEKS;
}

export function buyStrengthWindowLabel(weeks: number): string {
  return `${weeks} ${weeks === 1 ? "Woche" : "Wochen"}`;
}
