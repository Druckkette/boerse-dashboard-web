type ChartDatum = { date: string; [key: string]: string | number | null | undefined };

export function lastChartDataIndex(points: ChartDatum[], keys: string[]): number {
  return points.findLastIndex((point) => keys.some((key) => typeof point[key] === "number" && Number.isFinite(point[key])));
}

export function previousChartClose(points: ChartDatum[], index: number): number | null {
  for (let previous = index - 1; previous >= 0; previous -= 1) {
    const close = points[previous].close;
    if (typeof close === "number" && Number.isFinite(close)) return close;
  }
  return null;
}
