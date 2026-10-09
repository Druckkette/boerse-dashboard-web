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
    if (specifier.startsWith(".") && context.parentURL?.startsWith(pathToFileURL(srcRoot).href)) {
      const target = fileURLToPath(new URL(specifier, context.parentURL));
      for (const suffix of [".tsx", ".ts"]) {
        if (existsSync(target + suffix)) return { url: pathToFileURL(target + suffix).href, shortCircuit: true };
      }
    }
    return nextResolve(specifier === "next/link" ? "next/link.js" : specifier, context);
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

const { PortfolioAlerts, HomeEarnings, HomeChanges, earningsTime } = await import("../src/features/home/home-sections.tsx");
const render = (component, props) => renderToStaticMarkup(React.createElement(component, props));
test("portfolio groups confirmed sells, observations and data checks independently", () => {
  const html = render(PortfolioAlerts, { alerts: [
    { id: "sell:A", ticker: "A", category: "action", label: "Verkaufen", tone: "bad", detail: "Bestätigtes Signal", recommendation_pct: 50, last_seen_date: "2026-10-08", generated_at: "2026-10-08T21:15:00Z", freshness: "current", href: "/sell-monitor/A" },
    { id: "stop:A", ticker: "A", category: "observe", label: "Stop fehlt", tone: "warning", detail: "Kein Stop", href: "/sell-monitor/A" },
    { id: "data:B", ticker: "B", category: "data", label: "Daten prüfen", tone: "warning", detail: "Kurs veraltet", signal: "Unter 50-SMA", freshness: "stale", href: "/sell-monitor/B" },
  ] });
  assert.ok(html.indexOf("Handlungsbedarf") < html.indexOf("Beobachten"));
  assert.ok(html.includes("Tranche 50 %"));
  assert.ok(html.includes("Monitor"));
  assert.ok(html.includes("Gespeichertes Signal: Unter 50-SMA"));
  assert.equal((html.match(/href="\/sell-monitor\/A"/g) || []).length, 2);
});
test("calendar defaults to fourteen days of portfolio appointments", () => {
  const event = (ticker, days, scopes) => ({ ticker, name: ticker, date: "2026-10-09", days_until: days, time: "amc", source: "fmp", scopes, href: `/stocks/${ticker}` });
  const html = render(HomeEarnings, { calendar: { today: "2026-10-09", status: "available", rows: [event("DEPOT", 0, ["portfolio"]), event("WATCH", 0, ["watchlist"]), event("LATER", 14, ["portfolio"])] } });
  assert.ok(html.includes("DEPOT"));
  assert.ok(!html.includes("WATCH"));
  assert.ok(!html.includes("LATER"));
  assert.ok(html.includes("Nachbörslich (US)"));
  assert.ok(html.includes("09.10.2026"));
});
test("unknown time and conflicting provider dates are transparent", () => {
  assert.equal(earningsTime(""), "Veröffentlichungszeit unbekannt");
  assert.equal(earningsTime("bmo"), "Vorbörslich (US)");
  assert.match(earningsTime("16:30"), /Zeitzone unbestätigt/);
  const html = render(HomeEarnings, { calendar: { status: "available", rows: [{ ticker: "A", name: "Company", date: "2026-10-09", days_until: 0, time: "", source: "nasdaq", date_conflict: true, scopes: ["portfolio"], href: "/stocks/A" }] } });
  assert.ok(html.includes("Abweichende Anbietertermine"));
});
test("negative comparison and both membership scopes remain visible", () => {
  const html = render(HomeChanges, { changes: [{ ticker: "A", scopes: ["portfolio", "watchlist"], kind: "signal", summary: "Stärke verloren", details: ["Score 82 → 74", "Entfallen: Kurs über 50-SMA"], previous_as_of: "2026-10-07", as_of: "2026-10-08", href: "/stocks/A", tone: "warning" }] });
  assert.ok(html.includes("Stärke verloren"));
  assert.ok(html.includes("Score 82 → 74"));
  assert.ok(html.includes("07.10"));
  assert.ok(html.includes("08.10"));
});
