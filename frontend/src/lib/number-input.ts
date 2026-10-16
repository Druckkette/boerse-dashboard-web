export type NumberInput = { kind: "empty" } | { kind: "invalid" } | { kind: "value"; value: number };

export function positiveDecimalInput(raw: string): NumberInput {
  const text = raw.trim();
  if (!text) return { kind: "empty" };
  if (!/^(?:\d+(?:[.,]\d+)?|[.,]\d+)$/.test(text)) return { kind: "invalid" };
  const value = Number(text.replace(",", "."));
  return Number.isFinite(value) && value > 0 ? { kind: "value", value: Number(value.toFixed(4)) } : { kind: "invalid" };
}
