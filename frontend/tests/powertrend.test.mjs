import assert from "node:assert/strict";
import test from "node:test";
import { registerHooks } from "node:module";
import { readFileSync, existsSync } from "node:fs";
import { fileURLToPath, pathToFileURL } from "node:url";
import path from "node:path";
import ts from "typescript";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

// Render the production TSX components directly, with the same JSX transform as Next.
const srcRoot = fileURLToPath(new URL("../src/", import.meta.url));
registerHooks({
  resolve(specifier, context, nextResolve) {
    if (specifier.startsWith("@/")) {
      const target = path.join(srcRoot, specifier.slice(2));
      for (const suffix of [".tsx", ".ts"]) {
        if (existsSync(target + suffix)) return { url: pathToFileURL(target + suffix).href, shortCircuit: true };
      }
    }
    return nextResolve(specifier, context);
  },
  load(url, context, nextLoad) {
    if (url.startsWith(pathToFileURL(srcRoot).href) && /\.tsx?$/.test(url)) {
      return { format: "module", shortCircuit: true, source: ts.transpileModule(readFileSync(fileURLToPath(url), "utf8"), {
        compilerOptions: { jsx: ts.JsxEmit.ReactJSX, module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 }
      }).outputText };
    }
    return nextLoad(url, context);
  }
});
const { PowerTrendBadge, PowerTrendCard } = await import("../src/features/market/powertrend-card.tsx");
const { StatusChip } = await import("../src/components/ui/status-chip.tsx");
const powertrend = (state) => ({ enabled: true, state, formal_active: state !== "off", start_date: "2026-08-19", pressure_since: state === "under_pressure" ? "2026-09-25" : null, low_above_21_streak: 1, ema21_over_50_streak: 5, sma50_rising_1d: true, positive_or_flat_day: true, reason: "" });

for (const phase of ["ROT - Abwarten", "GELB - Startschuss", "GRÜN", "GELB - Trenddruck"]) {
  test(`${phase} can display an independently green active Powertrend`, () => {
    const html = renderToStaticMarkup(React.createElement("div", null,
      React.createElement(StatusChip, { tone: "bad" }, phase),
      React.createElement(PowerTrendBadge, { powertrend: powertrend("on") }),
      React.createElement(PowerTrendCard, { powertrend: powertrend("on") })
    ));
    assert.ok(html.includes(phase));
    assert.ok(html.includes("⚡ Powertrend aktiv"));
    assert.ok(html.includes("Powertrend gestartet am 19.08.2026"));
    assert.ok(html.includes("Die vier Bedingungen waren am Startdatum vollständig erfüllt."));
    assert.ok(html.includes("text-[#138a57]"));
    assert.ok(!html.includes("formal aktiv"));
  });
}
test("AUFWÄRTSTREND and Powertrend under pressure remain separate with recovery progress", () => {
  const html = renderToStaticMarkup(React.createElement("div", null,
    React.createElement(StatusChip, { tone: "good" }, "AUFWÄRTSTREND"),
    React.createElement(PowerTrendBadge, { powertrend: powertrend("under_pressure") }),
    React.createElement(PowerTrendCard, { powertrend: powertrend("under_pressure") })
  ));
  assert.ok(html.includes("AUFWÄRTSTREND"));
  assert.ok(html.includes("⚡ Powertrend unter Druck"));
  assert.ok(html.includes("Powertrend gestartet am 19.08.2026 · unter Druck seit 25.09.2026"));
  assert.ok(html.includes("1/10"));
  assert.ok(html.includes("Voraussetzungen für die Rückkehr"));
  assert.ok(!html.includes("⚡ Powertrend aktiv"));
});
test("off is displayed neutrally and pressure without date remains understandable", () => {
  const html = renderToStaticMarkup(React.createElement(PowerTrendBadge, { powertrend: powertrend("off") }));
  assert.ok(html.includes("Powertrend aus"));
  const card = renderToStaticMarkup(React.createElement(PowerTrendCard, { powertrend: { ...powertrend("under_pressure"), pressure_since: null } }));
  assert.ok(card.includes("aktuell unter Druck"));
});
