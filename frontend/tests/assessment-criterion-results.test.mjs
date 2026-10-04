import assert from "node:assert/strict";
import test from "node:test";
import { criterionResults } from "../src/features/stocks/assessment-criterion-results.ts";

test("K4 distinguishes true, false and missing subcriteria and keeps weights", () => {
  const rows = criterionResults("k4_rs_leadership", { raw: { components: {
    above_21_ema: { score: 100, status: "available", base_weight: .25, raw: { above_21_ema: true } },
    above_50_sma: { score: 0, status: "available", base_weight: .15, raw: { above_50_sma: false } },
    rs_52w_high: { score: null, status: "missing", base_weight: .3 },
  } } });
  assert.deepEqual(rows.map(r => r.outcome), ["passed", "failed", "missing"]);
  assert.equal(rows[0].weight, .25);
});
test("graded boundary is explicit, neutral and partial data remain distinct", () => {
  assert.equal(criterionResults("cmf", { score: 70, status: "partial" })[0].outcome, "passed");
  assert.equal(criterionResults("cmf", { score: 69.9 })[0].outcome, "failed");
  assert.match(criterionResults("cmf", { score: 70 })[0].detail, /70\/100/);
  assert.equal(criterionResults("cmf", { score: null, status: "neutral" })[0].outcome, "neutral");
  assert.equal(criterionResults("cmf", { score: null })[0].outcome, "missing");
});
test("K4 nested persistence and separation expose all parts without treating missing data as zero", () => {
  const rows = criterionResults("k4_rs_leadership", { raw: { components: {
    persistence: { score: 90, base_weight: .2, raw: { persistence_21_pct: 90, persistence_50_pct: 60, available_days_21: 63, available_days_50: 63 } },
    white_space: { score: 80, base_weight: .1, raw: { current_separation: 100, stability_score: 70, distance_rs_to_21_pct: 1.5, distance_rs_to_50_pct: null } },
  } } });
  assert.deepEqual(rows[0].children.map(r => r.weight), [.6, .4]);
  assert.deepEqual(rows[1].children.map(r => r.weight), [.35, .65]);
  assert.deepEqual(rows[1].children[0].children.map(r => r.outcome), ["passed", "missing"]);
});
test("fundamental rules use authoritative booleans instead of score threshold", () => {
  const rows = criterionResults("fundamental_core", {}, [
    { category: "fundamental", label: "EPS", passed: true, detail: "Wachstum ausreichend" },
    { category: "fundamental", label: "Umsatz", passed: false, detail: "Nicht verfügbar: keine Umsatz-Quartalshistorie gespeichert" },
    { category: "fundamental", label: "Fundamental-Datenquelle", passed: true, detail: "Cache" },
    { category: "fundamental", label: "Institutionelle Unterstützung", passed: true, detail: "13F-Kontext" },
  ]);
  assert.deepEqual(rows.map(r => r.outcome), ["passed", "missing"]);
});
test("neutral K38 still exposes failed highs and unknown return separately", () => {
  const rows = criterionResults("k38_hh_hl_good_close", { status: "neutral", raw: { higher_high: false, higher_low: true } });
  assert.deepEqual(rows.map(r => r.outcome), ["failed", "passed", "missing", "missing"]);
});
test("only score relevant active chart signals appear in the score breakdown", () => {
  const rows = criterionResults("price_action_core", { raw: { scored_signal_keys: ["up", "down"] } }, [], [
    { key: "up", label: "Positive", category: "positive", detail: "Positive signal", score_relevant: true },
    { key: "down", label: "Negative", category: "negative", detail: "Negative signal", score_relevant: true },
    { key: "context", label: "Context", category: "positive", detail: "Context", score_relevant: false },
  ]);
  assert.deepEqual(rows.map(r => r.outcome), ["passed", "failed"]);
});

test("inapplicable ETF fundamentals are not displayed as passed", () => {
  const rows = criterionResults("fundamental_core", {}, [{ category: "fundamental", label: "Operative Fundamentalkriterien", passed: true, detail: "Fundamentalkriterium für diesen Wertpapiertyp nicht anwendbar." }]);
  assert.equal(rows[0].outcome, "missing");
});
