import { test, expect } from "@playwright/test";

test("beta home and navigation contain only the six public destinations", async ({ page }) => {
  const calls: string[] = [];
  page.on("request", request => { if (request.url().includes("/api/v1/")) calls.push(new URL(request.url()).pathname); });
  await page.goto("/");
  await expect(page.getByText("Top-3-Aktien des Tages")).toBeVisible();
  await expect(page.locator("aside nav a")).toHaveCount(6);
  await expect(page.locator("aside")).not.toContainText("Portfolio");
  await expect(page.locator("aside")).not.toContainText("Settings");
  await expect(page.getByText("Mein Depot")).toHaveCount(0);
  expect(calls.every(path => path === "/api/v1/beta/home")).toBeTruthy();
  for (const path of ["/market", "/sectors", "/industry-groups", "/stocks", "/sell-check"]) {
    const response = await page.goto(path);
    expect(response?.status()).toBe(200);
    await expect(page.locator("aside nav")).toBeVisible();
  }
});

test("stock comparison renders projected beta rows and missing-data warnings without private requests", async ({ page }) => {
  const errors: string[] = [];
  const calls: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  page.on("request", request => { if (request.url().includes("/api/v1/")) calls.push(new URL(request.url()).pathname); });
  await page.goto("/stocks");
  const response = page.waitForResponse(response => response.url().includes("/stocks/assessment/compare?"));
  await page.getByRole("button", { name: /^Aktienvergleich/ }).click();
  const reply = await response;
  expect(reply.status()).toBe(200);
  expect(await reply.json()).not.toHaveProperty("missing_tickers");
  const panel = page.locator("section").filter({ has: page.getByRole("button", { name: /^Aktienvergleich/ }) });
  await expect(panel.locator("table").first().locator("tbody tr")).toHaveCount(5);
  await expect(panel).toContainText("Kursdaten fehlen oder sind zu kurz für: GOOGL.");
  for (const name of ["Technisch", "Fundamental", "Gleitende Durchschnitte", "Chartverhalten", "Gesamtscore"]) {
    await panel.getByRole("button", { name, exact: true }).click();
    await expect(panel.locator("table").first().locator("tbody tr")).toHaveCount(5);
  }
  await panel.getByRole("button", { name: "Aktualisieren", exact: true }).click();
  await expect(panel.locator("table").first().locator("tbody tr")).toHaveCount(5);
  expect(calls).not.toContain("/api/v1/workspace");
  expect(errors).toEqual([]);
});

test("fresh stock stays unchanged until manual update; score reloads even on another tab", async ({ page }) => {
  let posts = 0;
  page.on("request", request => { if (request.method() === "POST" && request.url().endsWith("/refresh")) posts++; });
  await page.goto("/stocks/AAPL");
  await expect(page.getByText("Aktuell", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Aktie aktualisieren", exact: true })).toBeEnabled();
  expect(posts).toBe(0);
  await page.getByRole("button", { name: "Aktie aktualisieren", exact: true }).click();
  await expect(page.getByRole("progressbar", { name: "Aktienrefresh-Fortschritt" })).toBeVisible();
  await page.getByRole("button", { name: "Technik", exact: true }).click();
  await expect(page.getByText("Aktualisierung abgeschlossen.")).toBeVisible({ timeout: 15_000 });
  await expect(page.locator("main")).toContainText("Technical91/100");
  await page.getByRole("button", { name: "Übersicht", exact: true }).click();
  await expect(page.locator("main")).toContainText(/777[.,]77/);
  expect(posts).toBe(1);
});

test("two stale stock views share the existing single refresh and expose no private actions", async ({ browser }) => {
  const context = await browser.newContext({ httpCredentials: { username: "beta", password: "test-only-beta-password" } });
  const first = await context.newPage();
  const second = await context.newPage();
  await Promise.all([first.goto("http://127.0.0.1:18301/stocks/NVDA"), second.goto("http://127.0.0.1:18301/stocks/NVDA")]);
  for (const page of [first, second]) {
    await expect(page.getByRole("progressbar", { name: "Aktienrefresh-Fortschritt" })).toBeVisible();
    await expect(page.getByText("Zur Watchlist", { exact: true })).toHaveCount(0);
    await expect(page.getByText("Als Position merken", { exact: true })).toHaveCount(0);
    await expect(page.getByText("Aktualisierung abgeschlossen.")).toBeVisible({ timeout: 15_000 });
  }
  const result = await context.request.get("http://127.0.0.1:18380/__fixture/stats");
  expect((await result.json()).enqueued).toBe(2); // one AAPL manual + one shared NVDA auto
  await context.close();
});

test("free sell check displays the entered purchase and all rule categories", async ({ page }) => {
  await page.goto("/sell-check");
  await page.getByLabel("Aktie / Ticker").fill("NVDA");
  await page.getByLabel("Einstiegskurs").fill("31.25");
  await page.getByLabel("Einstiegsdatum").fill("2026-02-02");
  await page.getByLabel("Währung", { exact: true }).selectOption("EUR");
  await page.getByRole("button", { name: "Verkaufen bewerten" }).click();
  await expect(page.getByText(/Einstieg: 31.25 EUR am 2026-02-02/)).toBeVisible();
  for (const name of ["Nothalt", "Offensives Verkaufen", "Defensives Verkaufen"]) await expect(page.getByRole("heading", { name, exact: true })).toBeVisible();
});

test("direct private APIs/pages, spoofed headers, RSC, exports and server actions are denied", async ({ request }) => {
  for (const path of ["/portfolio", "/settings", "/setup", "/jobs", "/sell-monitor", "/trade-journal", "/portfolio.png", "/api/v1/home", "/api/v1/workspace", "/api/v1/industry-groups/rs/diagnostics", "/api/v1/jobs", "/api/v1/stocks/NVDA/report.pdf", "/api/v1/stocks/screening/export"]) {
    const response = await request.get(path, { headers: { RSC: "1", "x-beta-proxy-key": "wrong", "x-role": "admin" } });
    expect(response.status(), path).toBe(403);
  }
  const mutation = await request.post("/api/v1/jobs", { data: { type: "refresh_universe" } });
  expect(mutation.status()).toBe(403);
  const action = await request.post("/stocks", { headers: { "Next-Action": "arbitrary", origin: "http://127.0.0.1:18301" } });
  expect(action.status()).toBe(403);
  const csrf = await request.post("/api/v1/beta/stocks/NVDA/refresh", { data: { mode: "manual" }, headers: { origin: "https://other.example" } });
  expect(csrf.status()).toBe(403);
});

test("same build uses independent owner authentication and missing beta config fails closed", async ({ playwright }) => {
  const anon = await playwright.request.newContext({ httpCredentials: [] });
  expect((await anon.get("http://127.0.0.1:18301/")).status()).toBe(401);
  expect((await anon.get("http://127.0.0.1:18302/")).status()).toBe(503);
  expect((await anon.get("http://127.0.0.1:18300/")).status()).toBe(401);
  const owner = await playwright.request.newContext({ httpCredentials: { username: "owner", password: "test-only-private-password" } });
  expect((await owner.get("http://127.0.0.1:18300/portfolio")).status()).toBe(200);
  expect((await owner.get("http://127.0.0.1:18301/")).status()).toBe(401);
  await owner.dispose();
  await anon.dispose();
});
