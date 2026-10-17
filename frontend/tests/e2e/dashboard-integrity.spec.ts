import { test, expect } from "@playwright/test";

test.use({ baseURL: "http://127.0.0.1:18300", httpCredentials: { username: "owner", password: "test-only-private-password" } });
const position = { ticker: "TEST", name: "Test holding", shares: 50, entry_price: 10, current_price: 15, currency: "EUR", market_value: 750, pnl_abs: 250, pnl_pct: 50, weight_pct: 75, status: "ok", stop_price: 12, price_as_of: "2026-10-15", atr_pct: null, risk_contribution: null, beta_balancer_score: null, position_loss_risk: 150, position_loss_risk_pct: 15 };

for (const mode of ["product", "classic"]) for (const width of [1440, 390]) test(`stop validation and transparent portfolio analysis at ${width}px (${mode})`, async ({ page }) => {
  await page.context().addCookies([{name:"dashboard-ui",value:mode,url:"http://127.0.0.1:18300"}]);
  await page.setViewportSize({ width, height: 1000 });
  const writes: unknown[] = [], errors: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  await page.route("**/api/v1/workspace**", route => route.fulfill({ json: { source: "database", watchlist: [], recent_tickers: [], items: [] } }));
  await page.route("**/api/v1/portfolio/**", async route => {
    const path = new URL(route.request().url()).pathname;
    if (route.request().method() === "PATCH") { writes.push(route.request().postDataJSON()); return route.fulfill({ json: { position } }); }
    if (path.endsWith("snapshot")) return route.fulfill({ json: { positions: [position], kpis: [{ label: "Depotwert", value: "1.000 EUR", detail: "Test", tone: "neutral" }], cash: 250, cash_ratio_pct: 25, currency: "EUR", total_value: 1000 } });
    if (path.endsWith("analysis")) return route.fulfill({ json: { as_of: "2026-10-15", currency: "EUR", cash_ratio_pct: 25, attribution: { model: "current_holdings", start: "2026-09-15", end: "2026-10-15", currency: "EUR", result: null, cash_fx: null, external_cash_flow: 0, rows: [], covered_count: 0, total_count: 1, note: "Simulation des heutigen Bestands. Keine historische Depotperformance.", decomposition: "Keine erfundenen Kurse." }, sectors: [{ name: "Technologie", weight_pct: 75 }], industry_groups: [], top_positions: [{ ticker: "TEST", weight_pct: 75 }], stops: [], correlations: [], correlation_note: "Gemeinsame beobachtete Kurse.", earnings: { windows: [{ days: 7, weight_pct: 75 }], missing_weight_pct: 0, rows: [] }, scenarios: { sector: "all", sector_shock_pct: -10, sector_impact: -75, fx_shock_pct: -5, fx_impact: 0, note: "Statische Szenarien" }, notes: [] } });
    return route.fulfill({ json: { source: "missing", model: "unavailable", points: [], items: [], rows: [], cash_flows: [], transactions: [], data_status: "missing", message: "Keine gespeicherte Historie" } });
  });
  await page.goto("/portfolio");
  const stop = page.getByRole("textbox", { name: "TEST Stopp EUR", exact: true }).filter({ visible: true });
  await stop.fill("abc");
  await stop.press("Tab");
  await expect(stop).toHaveAttribute("aria-invalid", "true");
  expect(writes).toEqual([]);
  await stop.fill(""); await stop.press("Tab"); expect(writes).toEqual([]);
  await page.getByRole("button", { name: "TEST Stopp entfernen", exact: true }).filter({ visible: true }).click();
  await expect.poll(() => writes.length).toBe(1);
  expect(writes[0]).toEqual({ stop_price: null });
  await page.locator("summary").filter({ hasText: /^Depotanalyse/ }).click();
  await expect(page.getByText("Simulation des heutigen Bestands", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Szenarien", exact: true }).click();
  await expect(page).toHaveURL(/portfolio=/);
  await expect(page.getByText("Statische Szenarien", { exact: true })).toBeVisible();
  if (width === 390) await expect(mode === "classic" ? page.getByRole("combobox", { name: "Bereich öffnen" }) : page.getByRole("navigation", { name: "Mobile Hauptnavigation" })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
  expect(errors).toEqual([]);
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: `/tmp/dashboard-portfolio-${width}.png`, fullPage: true });
});

test("fast Enter uses the new ticker rather than the previous search result", async ({ page }) => {
  await page.route("**/api/v1/stocks/search?**", route => route.fulfill({ json: { query: new URL(route.request().url()).searchParams.get("q"), rows: [{ ticker: "OLD", name: "Old result" }] } }));
  await page.goto("/stocks");
  const search = page.getByRole("combobox", { name: "Aktie global suchen", exact: true });
  await search.fill("OLD");
  await expect(page.getByRole("option").first()).toContainText("OLD");
  await search.fill("NVDA"); await search.press("Enter");
  await expect(page).toHaveURL(/\/stocks\/NVDA/);
});

test("unavailable portfolio remains an error and private cross-site writes are rejected", async ({ page, request }) => {
  await page.route("**/api/v1/portfolio/snapshot", route => route.fulfill({ status: 503, json: { detail: "Datenbank derzeit nicht verfügbar" } }));
  await page.goto("/portfolio");
  await expect(page.getByText("Daten derzeit nicht verfügbar. Fehlende Werte werden nicht als Null dargestellt.", { exact: true })).toBeVisible();
  await expect(page.getByText("Keine offenen Positionen", { exact: true })).toHaveCount(0);
  const cross = await request.patch("/api/v1/settings", { headers: { Origin: "https://attacker.invalid", "Sec-Fetch-Site": "cross-site" }, data: { atr_threshold: 2 } });
  expect(cross.status()).toBe(403);
});

test("portfolio curve distinguishes a usable simulation from unavailable historical valuations", async ({ page }) => {
  await page.route("**/api/v1/portfolio/snapshot", route => route.fulfill({ json: { positions: [position], kpis: [], cash: 0, cash_ratio_pct: 0, currency: "EUR", total_value: 750 } }));
  await page.route("**/api/v1/portfolio/curve?**", route => {
    const history = new URL(route.request().url()).searchParams.get("model") === "execution_history";
    return route.fulfill({ json: { model: history ? "execution_history" : "current_holdings", source: "database", data_status: "limited", as_of: "2026-10-15", base_date: "2026-10-14", complete_points: history ? 0 : 2, total_points: 2,
      message: history ? "Historische Kursbewertungen fehlen; TR-Buchungen sind dokumentiert." : "Simulation des heutigen Bestands, keine historische Depotperformance.",
      points: ["2026-10-14", "2026-10-15"].map((date, index) => ({ date, depot_value: history ? null : 750 + index * 10, positions_value: history ? null : 750 + index * 10, cash: 0, portfolio_index: history ? null : 100 + index * 2, sp500_index: 100 + index, valuation_complete: !history })) } });
  });
  await page.goto("/portfolio");
  await expect(page.getByRole("heading", { name: "Simulation des heutigen Bestands", exact: true })).toBeVisible();
  await expect(page.locator('path[stroke="#34d399"]')).toHaveCount(1);
  await page.getByText("Darstellung & Zeitraum ändern", {exact:true}).click();
  await page.getByRole("combobox", { name: "Darstellung", exact: true }).selectOption("execution_history");
  await expect(page.getByRole("status").filter({ hasText: "Für diese Auswahl fehlen vollständige Depotbewertungen" })).toBeVisible();
  await expect(page.locator('path[stroke="#34d399"]')).toHaveCount(0);
  await page.getByRole("combobox", { name: "Darstellung", exact: true }).selectOption("current_holdings");
  await expect(page.locator('path[stroke="#34d399"]')).toHaveCount(1);
});

test("automatic portfolio curve keeps the TR ledger and January basis", async ({ page }) => {
  await page.route("**/api/v1/portfolio/snapshot", route => route.fulfill({ json: { positions: [position], kpis: [], cash: 0, cash_ratio_pct: 0, currency: "EUR", total_value: 750 } }));
  const requests: string[] = [];
  await page.route("**/api/v1/portfolio/curve?**", route => {
    const params = new URL(route.request().url()).searchParams;
    requests.push(params.get("start_date") || "");
    return route.fulfill({ json: { model: "execution_history", source: "trade_republic_transactions", data_status: "limited", as_of: "2026-10-15", base_date: "2026-01-01", complete_points: 2, total_points: 2, message: "Bestand und Cash aus sämtlichen TR-Buchungen rekonstruiert.", points: ["2026-01-01", "2026-01-02"].map((date, index) => ({ date, portfolio_index: 100 + index, sp500_index: 100 + index, depot_value: 1000 + index * 10, positions_value: 200 + index * 10, cash: 800 })) } });
  });
  await page.goto("/portfolio");
  await page.getByText("Darstellung & Zeitraum ändern", {exact:true}).click();
  await page.getByRole('textbox', { name: 'Startdatum', exact: true }).fill("2026-01-01");
  await expect(page.getByRole("heading", { name: "Depotkurve aus Ausführungen", exact: true })).toBeVisible();
  await expect(page.getByText("Basis 2026-01-01 · Stand 2026-10-15", { exact: true })).toBeVisible();
  await expect(page.locator('path[stroke="#34d399"]')).toHaveCount(1);
  await expect(page.getByRole("heading", { name: "Simulation des heutigen Bestands", exact: true })).toHaveCount(0);
  expect(requests).toContain("2026-01-01");
});

test("open portfolio rolls over at Berlin midnight and renders the shared single-point basis", async ({ page }) => {
  await page.clock.install({ time: new Date("2026-12-31T22:59:59Z") });
  await page.route("**/api/v1/portfolio/snapshot", route => route.fulfill({ json: { positions: [position], kpis: [], cash: 0, cash_ratio_pct: 0, currency: "EUR", total_value: 750 } }));
  await page.route("**/api/v1/portfolio/curve?**", route => {
    const start = new URL(route.request().url()).searchParams.get("start_date")!;
    return route.fulfill({ json: { model: "execution_history", source: "trade_republic_transactions", data_status: "fresh", as_of: start, base_date: start, complete_points: 1, total_points: 1, message: "TR-Jahresanfang", points: [{ date: start, portfolio_index: 100, sp500_index: 100, depot_value: 1000, positions_value: 500, cash: 500 }] } });
  });
  await page.goto("/portfolio");
  await page.getByText("Darstellung & Zeitraum ändern", {exact:true}).click();
  const input = page.getByRole("textbox", { name: "Startdatum", exact: true });
  await expect(input).toHaveValue("2026-01-01");
  await page.clock.runFor(1000);
  await expect(input).toHaveValue("2027-01-01");
  await expect(page.getByText("Basis 2027-01-01 · Stand 2027-01-01", { exact: true })).toBeVisible();
  await expect(page.locator('circle[data-series="portfolio_index"]')).toHaveCount(1);
  await expect(page.locator('circle[data-series="sp500_index"]')).toHaveCount(1);
  await input.fill("2026-07-01");
  await page.clock.runFor(60_000);
  await expect(input).toHaveValue("2026-07-01");
});
