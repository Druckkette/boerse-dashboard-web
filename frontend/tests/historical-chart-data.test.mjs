import assert from "node:assert/strict";
import test from "node:test";
import { historicalChartView } from "../src/features/trade-journal/historical-chart-data.ts";

const chart = {
  execution_date: "2026-09-22", assessment_as_of: "2026-09-21", currency: "USD",
  points: ["2025-01-03", "2026-09-17", "2026-09-21", "2026-09-22", "2026-09-23"].map((date) => ({ date, close: 56.64 })),
  markers: [
    { date: "2025-01-03", entry_type: "buy", price: 30, currency: "EUR" },
    { date: "2026-09-17", entry_type: "buy", price: 51.5, currency: "EUR" },
    { date: "2026-09-22", entry_type: "sell", price: 47.98, currency: "EUR" },
    { date: "2026-09-23", entry_type: "buy", price: 60, currency: "EUR" }
  ]
};

test("pre-execution chart hides sale candle but retains exact buy and sell dates", () => {
  const view = historicalChartView(chart, false, null);
  assert.equal(view.lastPriceDate, "2026-09-21");
  assert.equal(view.points.at(-1).date, "2026-09-22");
  assert.equal(view.points.at(-1).close, null);
  assert.equal(view.points.at(-1).open, undefined);
  assert.equal(view.markers.length, 3);
  assert.equal(view.points[0].date, "2025-01-03");
  assert.equal(chart.points[3].close, 56.64, "view must not change the API data");
});

test("retrospective chart includes sale-day candle and excludes future bars and markers", () => {
  const view = historicalChartView(chart, true, null);
  assert.equal(view.lastPriceDate, "2026-09-22");
  assert.equal(view.points.at(-1).close, 56.64);
  assert.ok(view.points.every((point) => point.date <= chart.execution_date));
  assert.ok(view.markers.every((marker) => marker.date <= chart.execution_date));
});

test("short window hides earlier buys while full holding period restores them", () => {
  assert.equal(historicalChartView(chart, false, 31).markers.length, 2);
  assert.equal(historicalChartView(chart, false, null).markers.length, 3);
});

test("missing sale-day data produces a date marker without a fabricated price", () => {
  const view = historicalChartView({ ...chart, points: chart.points.filter((point) => point.date !== "2026-09-22") }, true, 31);
  assert.equal(view.lastPriceDate, "2026-09-21");
  assert.equal(view.points.at(-1).close, null);
  assert.equal(view.markers.at(-1).price, 47.98);
});
