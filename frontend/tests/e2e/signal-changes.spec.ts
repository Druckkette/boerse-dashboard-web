import { test, expect } from "@playwright/test";

test.use({ baseURL: "http://127.0.0.1:18300", httpCredentials: {
  username: "owner", password: "test-only-private-password",
} });

for (const width of [390, 1440]) test(`TSLA deteriorations are correctly described in both views at ${width}px`, async ({ page }) => {
  await page.setViewportSize({ width, height: 900 });
  await page.route("**/api/v1/stocks/TSLA/changes", route => route.fulfill({ json: {
    ticker: "TSLA", previous_as_of: "2026-10-15", current_as_of: "2026-10-16",
    changes: [
      { kind: "new", source: "rule", effect: "deterioration", category: "trend", label: "Kurs über 50-SMA", detail: "Vorher: 362.44 vs 358.76 · Aktuell: 354.72 vs 359.46" },
      { kind: "resolved", source: "chart_signal", effect: "deterioration", category: "positive", label: "Leben über den Durchschnitten", detail: "Vorher: 28T über 50-SMA · Aktuell: Auslöseschwelle aktuell nicht mehr erfüllt." },
      { kind: "resolved", source: "chart_signal", effect: "deterioration", category: "positive", label: "Positive Kurslücken", detail: "Vorher: 1 in 10T, Schluss obere Hälfte · Aktuell: Auslöseschwelle aktuell nicht mehr erfüllt." },
    ],
  } }));
  await page.goto("/stocks/TSLA");
  const panel = page.locator("section").filter({ has: page.getByRole("heading", { name: "Seit dem vorherigen Handelstag" }) });
  for (const mode of ["product", "classic"]) {
    await expect(page.locator("html")).toHaveAttribute("data-ui", mode);
    await expect(panel).toContainText("Kriterium nicht mehr erfüllt: Kurs über 50-SMA");
    await expect(panel).toContainText("Stärkesignal entfallen: Leben über den Durchschnitten");
    await expect(panel).toContainText("Stärkesignal entfallen: Positive Kurslücken");
    await expect(panel).not.toContainText("Entschärft");
    await expect(panel).not.toContainText("Neu: Kurs über 50-SMA");
    await expect(panel.locator('[data-effect="deterioration"]')).toHaveCount(3);
    await expect(panel.locator('[data-effect="deterioration"] svg').first()).toHaveCSS("color", "rgb(194, 65, 59)");
    await expect(panel.getByText("3 Änderungen", { exact: true })).toHaveCSS("color", "rgb(194, 65, 59)");
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
    if (mode === "product") await page.getByRole("button", { name: "Zur klassischen Ansicht wechseln", exact: true }).click();
  }
});

test("only the disappearance of a negative chart signal is labeled Entschärft and green", async ({ page }) => {
  await page.route("**/api/v1/stocks/TSLA/changes", route => route.fulfill({ json: {
    ticker: "TSLA", previous_as_of: "2026-10-15", current_as_of: "2026-10-16",
    changes: [
      { kind: "resolved", source: "chart_signal", effect: "improvement", category: "negative", label: "Stau-Tage", detail: "Warnschwelle unterschritten" },
      { kind: "new", source: "chart_signal", effect: "improvement", category: "positive", label: "Positive Kurslücken", detail: "1 in 10T" },
      { kind: "new", source: "chart_signal", effect: "neutral", category: "neutral", label: "Inside Day", detail: "" },
    ],
  } }));
  await page.goto("/stocks/TSLA");
  const panel = page.locator("section").filter({ has: page.getByRole("heading", { name: "Seit dem vorherigen Handelstag" }) });
  await expect(panel.getByText("Entschärft: Stau-Tage", { exact: true })).toHaveCSS("color", "rgb(19, 138, 87)");
  await expect(panel.getByText("Neues Stärkesignal: Positive Kurslücken", { exact: true })).toHaveCSS("color", "rgb(19, 138, 87)");
  await expect(panel.getByText("Neu: Inside Day", { exact: true })).toHaveCSS("color", "rgb(104, 115, 134)");
});
