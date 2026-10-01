import type { TradeJournalEntryDetail } from "@/lib/types/api";

type HistoricalChart = NonNullable<TradeJournalEntryDetail["historical_chart"]>;

export function historicalChartView(chart: HistoricalChart, retrospective: boolean, windowDays: number | null) {
  const lastDay = retrospective ? chart.execution_date : chart.assessment_as_of < chart.execution_date ? chart.assessment_as_of : chart.execution_date;
  const start = windowDays === null ? "" : new Date(new Date(`${chart.execution_date}T12:00:00Z`).valueOf() - windowDays * 86400000).toISOString().slice(0, 10);
  const points: { date: string; [key: string]: string | number | null | undefined }[] = chart.points.filter((point) => point.date <= lastDay && point.date <= chart.execution_date && (!start || point.date >= start)).map((point) => ({ ...point }));
  const lastPriceDate = points.at(-1)?.date;
  const markers = chart.markers.filter((marker) => marker.date <= chart.execution_date && (!start || marker.date >= start));
  // Empty execution-date slots preserve exact markers without inventing a
  // candle, borrowing another session, or mixing broker EUR with stock USD.
  markers.forEach((marker) => { if (!points.some((point) => point.date === marker.date)) points.push({ date: marker.date, close: null }); });
  points.sort((a, b) => a.date.localeCompare(b.date));
  return { points, markers, lastPriceDate };
}
