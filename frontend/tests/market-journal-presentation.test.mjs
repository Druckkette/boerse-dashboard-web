import assert from "node:assert/strict";
import test from "node:test";
import { confirmedMarketPoint, marketDate, marketPercent, percentageDistance, powerTrendProgress } from "../src/features/market/market-journal-presentation.ts";

const powertrend = (overrides = {}) => ({
  enabled: true, state: "off", formal_active: false, start_date: null, pressure_since: null,
  low_above_21_streak: 9, ema21_over_50_streak: 4, sma50_rising_1d: true,
  positive_or_flat_day: true, reason: "", ...overrides
});

test("Powertrend reports the remaining consecutive sessions for both start conditions", () => {
  const result = powerTrendProgress(powertrend());
  assert.equal(result.label, "Aus");
  assert.equal(result.passed, 2);
  assert.equal(result.missing.length, 2);
  assert.match(result.missing[0], /noch 1 weiteren Handelstag.*21-EMA/);
  assert.match(result.missing[1], /noch 1 weiteren Handelstag.*50-SMA/);
  assert.match(result.summary, /am selben.*bestätigten Handelstag/);
});

test("Powertrend does not manufacture activation from four displayed checks", () => {
  const result = powerTrendProgress(powertrend({ low_above_21_streak: 10, ema21_over_50_streak: 5 }));
  assert.equal(result.passed, 4);
  assert.equal(result.label, "Aus");
  assert.deepEqual(result.missing, []);
});

test("An intact Powertrend keeps its state even when start streaks have fallen", () => {
  const result = powerTrendProgress(powertrend({ state: "on", formal_active: true, low_above_21_streak: 1 }));
  assert.equal(result.label, "Aktiv");
  assert.deepEqual(result.missing, []);
  assert.match(result.summary, /Kürzere aktuelle Startzähler beenden ihn nicht/);
  assert.match(result.endRule, /strikt unter/);
  assert.match(result.endRule, /Gleichstand beendet.*nicht/);
});

test("A Powertrend under pressure remains formal and explains complete recovery", () => {
  const result = powerTrendProgress(powertrend({ state: "under_pressure", formal_active: true, low_above_21_streak: 1, ema21_over_50_streak: 5, positive_or_flat_day: false }));
  assert.equal(result.label, "Unter Druck");
  assert.match(result.summary, /besteht formal weiter/);
  assert.match(result.summary, /vier Startbedingungen wieder gleichzeitig/);
  assert.match(result.missing[0], /noch 9 weitere Handelstage/);
  assert.ok(result.missing.includes("Schlusskurs mindestens auf Vortagesniveau"));
  assert.match(result.pressureRule, /drei aufeinanderfolgenden Schlusskursen/);
  assert.match(result.pressureRule, /0,5 ATR21/);
});

test("Cycle distances and the Powertrend MA comparison use the confirmed session", () => {
  const confirmed = { date: "2026-11-03", close: 102, ema21: 99, sma50: 100 };
  const quote = { date: "2026-11-04", close: 115, ema21: 101, sma50: 100 };
  const point = confirmedMarketPoint({ confirmed_as_of: "2026-11-03", as_of: "2026-11-04", chart_points: [confirmed, quote] });
  assert.equal(point, confirmed);
  assert.equal(marketPercent(percentageDistance(point.close, 100)), "+2 %");
  assert.equal(marketPercent(percentageDistance(quote.close, 100)), "+15 %");
  assert.equal(marketPercent(percentageDistance(point.ema21, point.sma50)), "-1 %");
  assert.equal(confirmedMarketPoint({ as_of: "2026-11-02", chart_points: [quote] }), undefined);
});

test("Missing and zero reference marks never create fabricated distances", () => {
  for (const reference of [0, null, undefined, NaN]) assert.equal(percentageDistance(100, reference), null);
  assert.equal(percentageDistance(null, 100), null);
  assert.equal(marketPercent(null), "—");
  assert.equal(marketPercent(0), "0 %");
  assert.equal(marketDate("2026-11-03"), "03.11.2026");
});
