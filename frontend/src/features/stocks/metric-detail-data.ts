export function splitMetricDetail(text: string) {
  const parts = text.split(" · ");
  const periods: { label: string; value: string }[] = [];
  const notes: string[] = [];
  for (const part of parts) {
    const entries = part.split(", ");
    const matches = entries.map(entry => entry.match(/^((?:\d{4}(?:[- ]?Q[1-4])?|Q[1-4](?:[- ]?\d{4})?|Jahr \d+))\s+([+-]?\d+(?:[.,]\d+)?%|n\/a|–|-)$/));
    if (matches.length && matches.every(Boolean)) {
      for (const match of matches) periods.push({ label: match![1], value: match![2] });
    } else if (part.trim()) notes.push(part);
  }
  return { periods, notes };
}
