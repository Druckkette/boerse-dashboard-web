import { showDisplaySettings } from "./ui-preferences";
import { test, expect } from "@playwright/test";

test.use({ baseURL: "http://127.0.0.1:18300", httpCredentials: {
  username: "owner", password: "test-only-private-password",
} });

for (const width of [390, 1440]) test(`stock analysis keeps useful signals without unsupported history or source panels at ${width}px`, async ({ page }) => {
  await page.setViewportSize({ width, height: 900 });
  // This test checks visibility across layouts; signal API contracts have separate tests.
  await page.route("**/api/v1/stocks/TSLA/changes", route => route.fulfill({
    json: { ticker: "TSLA", current_as_of: "2026-10-07", previous_as_of: "2026-10-06", changes: [] },
  }));
  const diagnosticRequests: string[] = [];
  page.on("request", request => {
    if (/\/api\/v1\/stocks\/[^/]+\/(score-history|provenance)(\?|$)/.test(request.url())) diagnosticRequests.push(request.url());
  });
  for (const mode of ["product", "classic"]) {
    await page.goto("/stocks/TSLA");
    await expect(page.locator("html")).toHaveAttribute("data-ui", mode);
    await expect(page.getByRole("heading", { name: "Seit dem vorherigen Handelstag" })).toBeVisible();
    await expect(page.getByText("Scoreverlauf und Ursachen", { exact: true })).toHaveCount(0);
    await expect(page.getByText("Datenherkunft und Berechnungsgrundlage", { exact: true })).toHaveCount(0);
    await expect(page.getByText("Chartwerte als Tabelle", { exact: true })).toHaveCount(0);
    await page.goto("/stocks/TSLA?tab=chart");
    await expect(page.locator("[data-chart-surface]")).toBeVisible();
    await expect(page.getByText("Chartwerte als Tabelle", { exact: true })).toHaveCount(0);
    await expect(page.getByRole("table")).toHaveCount(0);
    if (mode === "product") { await showDisplaySettings(page); await page.getByRole("button", { name: "Zur klassischen Ansicht wechseln", exact: true }).click(); }
  }
  expect(diagnosticRequests).toEqual([]);
});
