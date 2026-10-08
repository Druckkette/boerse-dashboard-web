import assert from "node:assert/strict";
import test from "node:test";
import { splitMetricDetail } from "../src/features/stocks/metric-detail-data.ts";

test("period comparisons preserve order, negative values, missing data and rule notes", () => {
  assert.deepEqual(splitMetricDetail("2026 Q3 +127.8%, 2026 Q2 -14.5%, 2026 Q1 n/a · 2026 Q2 unter 20%"), {
    periods: [{ label: "2026 Q3", value: "+127.8%" }, { label: "2026 Q2", value: "-14.5%" }, { label: "2026 Q1", value: "n/a" }],
    notes: ["2026 Q2 unter 20%"]
  });
});
test("unrecognized formats and narrative commas remain intact", () => {
  const text = "Nicht verfügbar: Spin-off, Vorjahr fehlt";
  assert.deepEqual(splitMetricDetail(text), { periods: [], notes: [text] });
  assert.deepEqual(splitMetricDetail("2025 +66.7%, 2024 +147.1% · alle >=20%").periods.map(p => p.label), ["2025", "2024"]);
});
