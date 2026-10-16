import { test, expect } from "@playwright/test";

const asOf = "2026-10-08";
const ampel = (ticker: string) => ({
  ticker, name: ticker === "^IXIC" ? "Nasdaq Composite" : "S&P 500", as_of: asOf, confirmed_as_of: asOf, quote_as_of: asOf, as_of_time: "2026-10-08T22:00:00Z",
  intraday: false, logic: "ibd", source: "database", data_status: "fresh", message: "", component_errors: [], warning_count: 1,
  breadth_mode: "schutz", volatility_regime: "Risk Off bestätigt", vix_regime: "Stress",
  // A stale/old backend hero must never override the actual phase in the UI.
  hero: { mode: "Defensiv", tone: "bad", action: "Alter Override", reasons: ["Trendwende-Ampel: GRÜN – Bestätigung"] },
  phase_info: { phase: "gruen", label: "GRÜN - Bestätigung", tone: "good", reason: "Startschuss bestätigt", action: "Frühe Bestätigungsphase. Exponierung vorsichtig aufbauen.", next_step: "Vollständige Trendbestätigung abwarten." },
  lights: [],
  cycle: { anchor_date: "2026-09-21", anchor_current: true, floor_mark: 100, floor_current: true, startschuss_low: 103, startschuss_current: true, ftd_negated: false, startschuss_bonus: false, ma_order: true, market_structure: "up", diagnostics: [] },
  change_cards: [], distance_tiles: [], chart_markers: [],
  chart_points: [ { date: "2026-10-07", open: 110, high: 113, low: 109, close: 112, volume: 1000, phase: "gruen" }, { date: asOf, open: 112, high: 115, low: 111, close: 114, volume: 1100, phase: "gruen" } ],
  warning_checks: [{ code: "W04", label: "Distributionstage (25T)", passed: false, detail: "4 Distributionstage", active_warning: true, tone: "warning" }],
  powertrend: { enabled: true, state: "on", formal_active: true, start_date: "2026-09-25", reason: "Alle Bedingungen erfüllt", low_above_21_streak: 10, ema21_over_50_streak: 5, sma50_rising_1d: true, positive_or_flat_day: true }
});

const scores = (ticker: string) => ({
  version: "market_context_v2", ticker, as_of: asOf, phase: "gruen", informational_only: true, notes: ["Eine Zusatzquelle fehlt; betroffener Beitrag bleibt unbewertet."],
  scores: [["index", "Index"], ["breadth", "Marktbreite"], ["powertrend", "Powertrend"], ["equal_weight", "Equal Weight"], ["volatility", "Volatilität"]].map(([key, title]) => ({
    key, title, scope: "Informationsscore", score: 0, status: "Schwach", tone: "bad", data_status: "partial", coverage_pct: 80, message: "Die Trendampel bleibt maßgeblich.",
    subscores: [{ key: "sample", label: "Beispiel-Unterscore", weight: 100, score: 0, status: "Schwach", tone: "bad", data_status: "partial", coverage_pct: 80, criteria: [
      { id: key === "index" ? "W04" : key === "breadth" ? "W14" : "E01", label: "Gewichteter Beitrag", weight: .5, score: 0, contribution: 0, evaluation: "rated", value: "Aktiv", rule: "Explizite Regel", explanation: "Begründung" },
      { id: "INFO", label: "Nur Information", weight: 0, score: null, contribution: null, evaluation: "info", value: "Messwert", rule: "Kein Scorebeitrag", explanation: "" },
      { id: "MISSING", label: "Fehlende Daten", weight: 1, score: null, contribution: null, evaluation: "missing", value: "Nicht verfügbar", rule: "Kein Malus", explanation: "" }
    ] }]
  }))
});

for (const width of [1440, 390]) {
  test(`market context stays below the binding ampel, preserves old panels and fits ${width}px`, async ({ browser }) => {
    const context = await browser.newContext({ viewport: { width, height: 1000 }, httpCredentials: { username: "owner", password: "test-only-private-password" } });
    const page = await context.newPage();
    const errors: string[] = [];
    const calls: string[] = [];
    page.on("pageerror", error => errors.push(error.message));
    await page.route("**/api/v1/market/**", route => {
      const url = new URL(route.request().url());
      const ticker = url.searchParams.get("ticker") || "^GSPC";
      if (url.pathname.endsWith("/ampel")) return route.fulfill({ json: ampel(ticker) });
      if (url.pathname.endsWith("/context-scores")) {
        calls.push(url.search);
        return route.fulfill({ json: scores(ticker) });
      }
      if (url.pathname.endsWith("/overview")) return route.fulfill({ json: { kpis: [], data_status: "fresh", as_of: asOf } });
      if (url.pathname.endsWith("/volatility")) return route.fulfill({ json: { as_of: asOf, source: "missing", regime: "Nicht berechnet", status_cards: [], points: [] } });
      if (url.pathname.endsWith("/breadth-overview")) return route.fulfill({ json: { as_of: asOf, source: "missing", data_status: "missing", signals: [], points: [], message: "Keine Breitenwerte" } });
      return route.fulfill({ json: { source: "missing", intermarket: [], sector_rotation: [] } });
    });
    await page.goto("http://127.0.0.1:18300/market");
    await expect(page.locator("#context-scores article")).toHaveCount(5);
    const phase = page.locator("#trend").getByText("GRÜN - Bestätigung", { exact: true });
    await expect(phase.first()).toBeVisible();
    await expect(page.getByText("Alter Override", { exact: true })).toHaveCount(0);
    await expect(page.getByText("Defensiv", { exact: true })).toHaveCount(0);
    await expect(page.locator("#warnings")).toContainText("Frühwarnzeichen");
    await expect(page.locator("#warnings")).toContainText("Warnzeichen");
    await expect(page.locator("#breadth")).toContainText("Marktbreite");
    await expect(page.locator("#sentiment")).toContainText("Stimmungs- und Positionierungsindikatoren");
    const powertrendBox = await page.locator("#trend").getByText("Powertrend", { exact: true }).first().boundingBox();
    const statusBox = await phase.first().boundingBox();
    expect(powertrendBox!.y).toBeLessThan(statusBox!.y);
    await expect(page.locator("#trend").getByText("Bodenmarke", { exact: true })).toBeVisible();
    await expect(page.locator("#trend").getByText("Rally-Day-1-Tief", { exact: true })).toHaveCount(0);
    const contextBox = await page.locator("#context-scores").boundingBox();
    const phaseBox = await phase.first().boundingBox();
    expect(contextBox!.y).toBeGreaterThan(phaseBox!.y);
    const index = page.getByRole("article", { name: "Index Informationsscore" });
    await index.getByText("Beiträge & Regeln", { exact: true }).click();
    await expect(index).toContainText("W04");
    await expect(index).toContainText("Gewicht 0,5");
    await expect(index).toContainText("Anteil am Unterscore: 0 Punkte");
    await expect(index).toContainText("Nicht bewertbar");
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({ path: `/tmp/boerse-market-context-${width}.png`, fullPage: true });
    await page.locator("#context-scores").screenshot({ path: `/tmp/boerse-market-context-cards-${width}.png` });
    await page.getByRole("button", { name: /NASDAQ/ }).click();
    await expect(page.locator("#context-scores")).toContainText("^IXIC");
    expect(calls.every(query => new URLSearchParams(query).get("as_of") === asOf)).toBeTruthy();
    expect(errors).toEqual([]);
    await context.close();
  });
}
