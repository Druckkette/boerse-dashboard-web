import { test, expect } from "@playwright/test";

test.beforeEach(async ({ request }) => {
  await request.post("http://127.0.0.1:18380/__fixture/chart-reset");
});

for (const mode of ["product", "classic"])
  for (const width of [1440, 390])
    test(`beta chart analysis opens from navigation and stays read-only at ${width}px (${mode})`, async ({ page }) => {
      await page.context().addCookies([{ name: "dashboard-ui", value: mode, url: "http://127.0.0.1:18301" }]);
      await page.setViewportSize({ width, height: 1000 });
      const calls: { path: string; method: string }[] = [];
      const errors: string[] = [];
      page.on("pageerror", (error) => errors.push(error.message));
      page.on("request", (request) => {
        if (request.url().includes("/api/v1/")) calls.push({ path: new URL(request.url()).pathname, method: request.method() });
      });
      await page.goto("/");
      if (width >= 1024) {
        await page.locator("aside").getByRole("link", { name: "Chartanalyse", exact: true }).click();
      } else if (mode === "product") {
        await page.getByRole("button", { name: "Mehr", exact: true }).click();
        await page.getByRole("dialog", { name: "Weitere Bereiche" }).getByRole("link", { name: "Chartanalyse", exact: true }).click();
      } else {
        await page.getByLabel("Bereich öffnen", { exact: true }).selectOption("/chart-analysis");
      }
      await expect(page.getByRole("heading", { name: "Chartanalyse", exact: true })).toBeVisible();
      await expect(page.getByRole("button", { name: "Universum nach Mustern scannen" })).toHaveCount(0);
      await page.getByText("Musterparameter ansehen", { exact: true }).click();
      await expect(page.getByLabel("Cup: Maximale Tiefe (%)", { exact: true })).toHaveAttribute("readonly", "");
      await expect(page.getByRole("button", { name: "Parameter speichern", exact: true })).toHaveCount(0);
      await expect(page.getByLabel("Austrocknendes Volumen als Pflichtkriterium")).toBeDisabled();
      await page.getByLabel("Muster filtern", { exact: true }).selectOption("cup_with_handle");
      await page.getByLabel("Treffer nach Aktie filtern").fill("IBKR");
      await page.getByRole("link", { name: "IBKR · Cup with Handle", exact: true }).click();
      await expect(page).toHaveURL(/chart-analysis\/IBKR\?pattern=.+&rules=/);
      await expect(page.getByTestId("pattern-overlays").locator("path")).toHaveCount(1);
      await expect(page.getByRole("button", { name: "Kursdaten aktualisieren", exact: true })).toHaveCount(0);
      await expect(page.getByRole("button", { name: "Aktie aktualisieren", exact: true })).toBeEnabled();
      await page.getByLabel("Historischer Prüfzeitpunkt", { exact: true }).fill("2025-05-01");
      await expect(page.getByLabel("Muster im Chart", { exact: true })).not.toContainText("Cup with Handle");
      await page.getByLabel("Aktie im Chart öffnen", { exact: true }).fill("TBBK");
      await page.getByRole("button", { name: "Chart öffnen", exact: true }).click();
      await expect(page).toHaveURL(/chart-analysis\/TBBK\?refresh=1$/);
      await expect(page.getByLabel("Muster im Chart", { exact: true })).toContainText("Cup without Handle");
      await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
      expect(calls.every((call) => call.method === "GET")).toBeTruthy();
      expect(calls.some((call) => call.path.startsWith("/api/v1/jobs"))).toBeFalsy();
      expect(errors).toEqual([]);
    });

test("beta quality diagnostics retain filters, fifty-row pages and clickable charts", async ({ page }) => {
  const skipped = Array.from({ length: 80 }, (_, index) => ({ ticker: `MISS${index}`, code: "missing_history", reason: "Keine gespeicherten Kurse vorhanden." }));
  const partial = Array.from({ length: 39 }, (_, index) => ({ ticker: `PART${index}`, code: "invalid_ohlc", reason: "Ungültige Tageskurse; saubere Abschnitte wurden geprüft." }));
  await page.route("**/api/v1/chart-analysis/results?*", async (route) => {
    const response = await route.fetch();
    await route.fulfill({ json: {
      ...(await response.json()), scanned_count: 121, analysed_count: 41, partial_count: 40, skipped_count: 80,
      skipped, quality_counts: { missing_history: 80, invalid_ohlc: 39, extreme_jump: 1 },
      quality_issues: [...skipped, ...partial, { ticker: "IBKR", code: "extreme_jump", reason: "Auffälliger Kurssprung; eine echte Kursbewegung ist möglich." }],
    } });
  });
  await page.goto("/chart-analysis");
  await expect(page.getByLabel("Auswertbarkeit des Aktienuniversums")).toContainText("Teilweise auswertbar40");
  await page.getByText("Datenqualität und ausgeschlossene Aktien ansehen", { exact: true }).click();
  const issues = page.getByRole("list", { name: "Datenhinweise", exact: true });
  await expect(issues.getByRole("listitem")).toHaveCount(50);
  await page.getByRole("button", { name: "Weitere Hinweise", exact: true }).click();
  await expect(page.getByText("51–100 / 120 Hinweise", { exact: true })).toBeVisible();
  await page.getByLabel("Datenhinweise nach Grund filtern").selectOption("jumps");
  await page.getByLabel("Datenhinweise nach Auswertbarkeit filtern").selectOption("partial");
  await page.getByLabel("Datenhinweise nach Aktie filtern").fill("IBKR");
  await expect(issues.getByRole("listitem")).toHaveCount(1);
  await issues.getByRole("link", { name: "IBKR", exact: true }).click();
  await expect(page.getByTestId("pattern-overlays").locator("path")).toHaveCount(1);
});

test("beta chart refresh uses the scoped capability flow and reloads chart data", async ({ page }) => {
  let chartReads = 0;
  let refreshes = 0;
  const forbidden: string[] = [];
  const handle = `beta_${"a".repeat(32)}`;
  page.on("request", (request) => {
    const path = new URL(request.url()).pathname;
    if (path === "/api/v1/chart-analysis/IBKR") chartReads++;
    if (path.startsWith("/api/v1/jobs") || (path.startsWith("/api/v1/chart-analysis/") && request.method() !== "GET")) forbidden.push(path);
  });
  await page.route("**/api/v1/beta/stocks/IBKR/refresh", async (route) => {
    expect(route.request().postDataJSON()).toEqual({ mode: "manual" });
    refreshes++;
    await route.fulfill({ json: { job_id: handle, capability: "test-scoped-capability", status: "queued", finished: false, progress: 0 } });
  });
  await page.route(`**/api/v1/beta/stock-refresh/${handle}/status`, async (route) => {
    expect(route.request().headers()["x-beta-capability"]).toBe("test-scoped-capability");
    await route.fulfill({ json: { job_id: handle, status: "done", finished: true, progress: 100 } });
  });
  await page.goto("/chart-analysis/IBKR?refresh=1");
  await expect(page.getByTestId("pattern-overlays").locator("path")).toHaveCount(1);
  await page.getByRole("button", { name: "Aktie aktualisieren", exact: true }).click();
  await expect(page.getByText("Aktualisierung abgeschlossen.", { exact: true })).toBeVisible();
  await expect.poll(() => chartReads).toBeGreaterThanOrEqual(2);
  expect(refreshes).toBe(1);
  expect(forbidden).toEqual([]);
});

test("beta chart management endpoints stay forbidden", async ({ request }) => {
  expect((await request.put("/api/v1/chart-analysis/config", { data: {} })).status()).toBe(403);
  expect((await request.post("/api/v1/chart-analysis/scan", { data: {} })).status()).toBe(403);
  expect((await request.post("/api/v1/jobs", { data: { type: "scan_chart_patterns" } })).status()).toBe(403);
  expect((await request.get("/api/v1/chart-analysis/results?repair_prices=true")).status()).toBe(403);
});

test("missing beta chart prices trigger only one scoped refresh and no private job", async ({ page }) => {
  let refreshes = 0;
  const forbidden: string[] = [];
  page.on("request", (request) => {
    const path = new URL(request.url()).pathname;
    if (path.startsWith("/api/v1/jobs")) forbidden.push(path);
  });
  await page.route("**/api/v1/beta/stocks/NODATA/freshness", (route) => route.fulfill({ json: { ticker: "NODATA", fresh: false, refresh_needed: true } }));
  await page.route("**/api/v1/beta/stocks/NODATA/refresh", async (route) => {
    expect(route.request().postDataJSON()).toEqual({ mode: "auto" });
    refreshes++;
    await route.fulfill({ status: 404, json: { detail: "Test: Aktie noch nicht im gemeinsamen Datenbestand." } });
  });
  await page.goto("/chart-analysis/NODATA?refresh=1");
  await expect(page.getByRole("alert").filter({ hasText: "Test: Aktie noch nicht im gemeinsamen Datenbestand" })).toBeVisible();
  await expect(page.getByText(/Kursstand: Keine Kurse vorhanden/)).toBeVisible();
  expect(refreshes).toBe(1);
  expect(forbidden).toEqual([]);
});
