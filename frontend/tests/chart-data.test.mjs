import assert from "node:assert/strict";
import test from "node:test";
import { lastChartDataIndex, previousChartClose } from "../src/components/ui/chart-data.ts";

test("execution marker without prices does not erase the last real chart readout", () => {
  const points = [{ date: "2026-09-21", close: 56.64, sma50: 48.45 }, { date: "2026-09-22", close: null }];
  assert.equal(lastChartDataIndex(points, ["close", "sma50"]), 0);
  assert.equal(lastChartDataIndex([{ date: "2026-09-22", close: null }], ["close"]), -1);
  assert.equal(lastChartDataIndex([{ date: "2026-09-22", value: 0 }], ["value"]), 0);
});

test("previous close skips empty execution dates and never uses a future quote", () => {
  const points = [{ date: "2026-09-18", close: 58.15 }, { date: "2026-09-19", close: null }, { date: "2026-09-21", close: 56.64 }, { date: "2026-09-22", close: 999 }];
  assert.equal(previousChartClose(points, 2), 58.15);
  assert.equal(previousChartClose(points, 0), null);
});
