import assert from "node:assert/strict";
import test from "node:test";
import { normalizedWeights, settingsChanges } from "../src/features/settings/settings-draft.ts";

test("save payload contains changed settings only, including nested weights", () => {
  const saved = { risk_per_position_pct: 1, pushover_configured: true, position_monitor_interval_minutes: 1, assessment_score_weights: { overall: { technical: 30, fundamental: 70 } } };
  const draft = structuredClone(saved);
  draft.risk_per_position_pct = 2;
  draft.assessment_score_weights.overall.technical = 40;
  assert.deepEqual(settingsChanges(saved, draft), { risk_per_position_pct: 2, assessment_score_weights: draft.assessment_score_weights });
  assert.equal(saved.assessment_score_weights.overall.technical, 30);
});

test("reverting a change leaves no pending save", () => {
  const saved = { risk_per_position_pct: 1, pushover_enabled: false };
  assert.deepEqual(settingsChanges(saved, structuredClone(saved)), {});
});

test("normalization preserves proportions, zero weights and the saved configuration", () => {
  const source = { overall: { technical: 60, fundamental: 30, chart: 0, moving_average: 30 }, technical: { a: 0, b: 0 } };
  const result = normalizedWeights(source);
  assert.deepEqual(result.overall, { technical: 50, fundamental: 25, chart: 0, moving_average: 25 });
  assert.deepEqual(result.technical, { a: 0, b: 0 });
  assert.equal(source.overall.technical, 60);
});
