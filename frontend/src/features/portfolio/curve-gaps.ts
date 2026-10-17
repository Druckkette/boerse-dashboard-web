export function curveGaps(
  points: {
    date: string;
    portfolio_index: number | null;
    missing_instruments?: string[];
  }[],
) {
  const result: {
    from: string;
    to: string;
    count: number;
    instruments: string[];
  }[] = [];
  let gap: (typeof result)[number] | undefined;
  for (const point of points) {
    if (point.portfolio_index == null) {
      if (!gap) {
        gap = { from: point.date, to: point.date, count: 0, instruments: [] };
        result.push(gap);
      }
      gap.to = point.date;
      gap.count += 1;
      gap.instruments = [
        ...new Set([...gap.instruments, ...(point.missing_instruments || [])]),
      ];
    } else gap = undefined;
  }
  return result;
}
