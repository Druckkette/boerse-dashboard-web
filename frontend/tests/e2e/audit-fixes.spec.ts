import { test, expect } from "@playwright/test";

test.use({ baseURL: "http://127.0.0.1:18300", httpCredentials: { username: "owner", password: "test-only-private-password" } });

test("explicit percent stop replaces a price stop and failed sale retries reuse one booking id", async ({ page }) => {
  let position = { ticker: "TEST", name: "Synthetic", shares: 10, entry_price: 100, current_price: 110,
    currency: "USD", market_value: 1100, pnl_abs: 100, pnl_pct: 10, weight_pct: 100, status: "ok",
    stop_price: 90, stop_pct: null as number | null, buy_date: "2026-10-01", broker: "Test", account: "" };
  const sales: Record<string, unknown>[] = [];
  let savedStop: Record<string, unknown> | undefined;
  await page.route("**/api/v1/portfolio/**", async route => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/snapshot")) return route.fulfill({ json: { positions: [position], kpis: [], cash: 0, cash_ratio_pct: 0, currency: "USD", total_value: 1100 } });
    if (path.endsWith("/positions") && route.request().method() === "POST") {
      savedStop = route.request().postDataJSON();
      position = { ...position, stop_pct: 15, stop_price: 85 };
      return route.fulfill({ json: { position } });
    }
    if (path.endsWith("/sell")) {
      sales.push(route.request().postDataJSON());
      if (sales.length === 1) return route.fulfill({ status: 503, json: { detail: "Synthetischer Antwortfehler" } });
      return route.fulfill({ json: { ticker: "TEST", remaining_position: position, cash_balance: 220, transaction: {} } });
    }
    return route.fulfill({ json: { positions: [], items: [], points: [], mappings: [], cash_flows: [], model: "current_holdings", data_status: "missing", source: "missing", message: "Synthetische Testdaten" } });
  });
  await page.goto("/portfolio");
  await page.locator("summary").filter({ hasText: "Positionen, Verkäufe und Cashflows" }).click();
  const editor = page.locator("section").filter({ has: page.getByRole("heading", { name: "Position erfassen", exact: true }) }).last();
  await editor.getByPlaceholder("NVDA").fill("TEST");
  await editor.getByPlaceholder("NVDA").press("Tab");
  await expect(editor.getByLabel("Stoppart", { exact: true })).toHaveValue("price");
  await editor.getByLabel("Stoppart", { exact: true }).selectOption("pct");
  await editor.getByLabel("Stopp %").fill("15");
  await editor.getByRole("button", { name: "Position speichern" }).click();
  await expect.poll(() => savedStop?.stop_mode).toBe("pct");
  expect(savedStop?.stop_pct).toBe(15);
  expect(savedStop?.stop_price).toBeNull();
  const sell = page.locator("section").filter({ has: page.getByRole("heading", { name: "Verkauf buchen", exact: true }) }).last();
  await expect(sell.getByText("Buchungswährung: USD")).toBeVisible();
  await sell.getByLabel("Stück", { exact: true }).fill("2");
  await sell.getByLabel("Preis", { exact: true }).fill("110");
  await sell.getByRole("button", { name: "Verkauf buchen", exact: true }).click();
  await expect(sell.getByRole("alert")).toContainText("Synthetischer Antwortfehler");
  await sell.getByRole("button", { name: "Verkauf buchen", exact: true }).click();
  await expect.poll(() => sales.length).toBe(2);
  expect(sales[0].booking_id).toBeTruthy();
  expect(sales[1].booking_id).toBe(sales[0].booking_id);
  expect(sales[1].currency).toBe("USD");
});
