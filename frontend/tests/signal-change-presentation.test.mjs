import assert from "node:assert/strict";
import test from "node:test";
import { signalChangePresentation } from "../src/features/stocks/signal-change-presentation.ts";

test("lost strength is red; only disappearing warnings are Entschärft", () => {
  const base = { kind: "resolved", source: "chart_signal", label: "Signal", detail: "" };
  assert.deepEqual(signalChangePresentation({ ...base, category: "positive", effect: "deterioration" }), { title: "Stärkesignal entfallen", tone: "bad" });
  assert.deepEqual(signalChangePresentation({ ...base, category: "negative", effect: "improvement" }), { title: "Entschärft", tone: "good" });
  assert.deepEqual(signalChangePresentation({ ...base, category: "neutral", effect: "neutral" }), { title: "Entfallen", tone: "neutral" });
});

test("new strength is green, new warnings are red, neutral signals stay neutral", () => {
  const base = { kind: "new", source: "chart_signal", label: "Signal", detail: "" };
  assert.deepEqual(signalChangePresentation({ ...base, category: "positive", effect: "improvement" }), { title: "Neues Stärkesignal", tone: "good" });
  assert.deepEqual(signalChangePresentation({ ...base, category: "negative", effect: "deterioration" }), { title: "Neues Warnsignal", tone: "bad" });
  assert.deepEqual(signalChangePresentation({ ...base, category: "neutral", effect: "neutral" }), { title: "Neu", tone: "neutral" });
});

test("a broken rule never claims the positively worded criterion is new", () => {
  const base = { source: "rule", category: "trend", label: "Kurs über 50-SMA", detail: "" };
  assert.deepEqual(signalChangePresentation({ ...base, kind: "new", effect: "deterioration" }), { title: "Kriterium nicht mehr erfüllt", tone: "bad" });
  assert.deepEqual(signalChangePresentation({ ...base, kind: "resolved", effect: "improvement" }), { title: "Kriterium wieder erfüllt", tone: "good" });
});
