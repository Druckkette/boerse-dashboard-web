export function localizeKpiValue(value: string): string {
  if (value === "n/a") return "Nicht verfügbar";
  const match =
    /^([+-]?)(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d+))?(?: (EUR|USD|GBP|CHF)|(%))?$/.exec(
      value,
    );
  if (!match) return value;
  const [, sign, integer, decimals, currency, percent] = match;
  // Format the documented decimal grammar without rounding financial strings.
  const grouped = BigInt(integer.replaceAll(",", "")).toLocaleString("de-DE");
  return `${sign}${grouped}${decimals ? `,${decimals}` : ""}${currency ? ` ${currency}` : percent || ""}`;
}
export function localizeKpiDetail(value: string): string {
  return value.replace(/^[+-]?\d+(?:\.\d+)?%/, (match) =>
    localizeKpiValue(match),
  );
}
