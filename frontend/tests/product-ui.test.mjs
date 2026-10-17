import assert from "node:assert/strict";
import test from "node:test";
import { localizeKpiValue, localizeKpiDetail } from "../src/lib/kpi-format.ts";
import { curveGaps } from "../src/features/portfolio/curve-gaps.ts";

test("documented backend KPI numbers retain signs, currency, precision and missing values", () => {
  for (const [raw, expected] of [
    ["182,602 USD", "182.602 USD"],
    ["-10,074.62 USD", "-10.074,62 USD"],
    ["+3.40%", "+3,40%"],
    ["13", "13"],
    ["0.00%", "0,00%"],
    ["n/a", "Nicht verfügbar"],
  ])
    assert.equal(localizeKpiValue(raw), expected);
  assert.equal(
    localizeKpiDetail("-4.20% · offene Positionen · Kursstand 2026-10-16"),
    "-4,20% · offene Positionen · Kursstand 2026-10-16",
  );
  assert.equal(
    localizeKpiValue("Faktor 2.5 bei 3,000 Aktien"),
    "Faktor 2.5 bei 3,000 Aktien",
  );
  assert.equal(localizeKpiValue("12,34 EUR"), "12,34 EUR");
  assert.equal(localizeKpiValue("9,007,199,254,740,993.20 EUR"), "9.007.199.254.740.993,20 EUR");
});
test("gap display groups only observed missing points and never converts a real zero or mutates the curve", () => {
  const points = [
    { date: "2026-01-01", portfolio_index: 100 },
    { date: "2026-01-02", portfolio_index: null },
    { date: "2026-01-05", portfolio_index: null },
    { date: "2026-01-06", portfolio_index: 0 },
    { date: "2026-01-07", portfolio_index: null },
  ];
  const original = structuredClone(points);
  assert.deepEqual(curveGaps(points), [
    { from: "2026-01-02", to: "2026-01-05", count: 2, instruments: [] },
    { from: "2026-01-07", to: "2026-01-07", count: 1, instruments: [] },
  ]);
  assert.deepEqual(points, original);
  assert.deepEqual(curveGaps([]), []);
});
test('gap disclosure uses the instruments supplied by the backend and never invents a cause', () => {
 const points=[{date:'2026-02-24',portfolio_index:null,missing_instruments:['DE000HM1C7B4']},{date:'2026-02-25',portfolio_index:null,missing_instruments:['DE000HM1C7B4','SECOND']},{date:'2026-02-26',portfolio_index:100,missing_instruments:[]}];
 const original=structuredClone(points);
 assert.deepEqual(curveGaps(points),[{from:'2026-02-24',to:'2026-02-25',count:2,instruments:['DE000HM1C7B4','SECOND']}]);
 assert.deepEqual(points,original);
});
