import { test, expect } from "@playwright/test";

const changes = ["Gesamtscore +10", "Technischer Score +10.6", "RS 78 → 81", "Neu: Entfernung zum 52-Wochen-Hoch", "Neu: Entfernung zum All-Time-High"];
const base = {
  previous_rank: null, last_close: 128.49, daily_opportunity_score: 74.7,
  quality_score: 71, daily_dynamics_score: 81.5, overall_score: 71, overall_score_delta: null,
  technical_score: 77.5, technical_score_delta: 10.6, fundamental_score: 52.3,
  moving_average_score: 95.5, chart_behavior_score: 73, rs_rating: 81, rs_rating_delta: null,
  relative_performance_1d: 1.47, relative_performance_5d: 5.36, volume_ratio: 0.49,
  dollar_volume_mio: 121.1, positive_changes: changes, reasons: changes,
  warnings: ["RS-Bewertung >=90: Aktuell 81"],
};
const data = { as_of: "2026-10-15", generated_at: "2026-10-15T18:00:00Z", status: "current", rows: [
  { ...base, rank: 1, ticker: "EHC", name: "Encompass Health Corporation Common Stock" },
  { ...base, rank: 2, ticker: "TEST", name: "Example Company", positive_changes: [], reasons: ["Trend-Score 96"], warnings: ["Earnings in 2 Kalendertagen", "EPS >=20%: Aktuell 17%"] },
  { ...base, rank: 3, ticker: "GCT", name: "GigaCloud Technology Inc - Class A Ordinary Shares", warnings: [], positive_changes: ["5T vs. SPY +5.6 %"], reasons: ["5T vs. SPY +5.6 %"] },
] };

for (const beta of [false, true]) for (const width of [1440, 390]) {
  test(`top daily explanations are unique and readable at ${width}px (${beta ? "beta" : "private"})`, async ({ browser }) => {
    const context = await browser.newContext({ viewport: { width, height: 1000 }, httpCredentials: beta ? { username: "beta", password: "test-only-beta-password" } : { username: "owner", password: "test-only-private-password" } });
    const page = await context.newPage();
    const errors: string[] = [];
    page.on("pageerror", error => errors.push(error.message));
    await page.route("**/api/v1/stocks/top-daily", route => route.fulfill({ json: data }));
    await page.goto(`http://127.0.0.1:${beta ? 18301 : 18300}/stocks`);
    const panel = page.getByRole("region", { name: "Top 3 Aktien des Tages" });
    const ehc = panel.getByRole("article", { name: "EHC · Rang 1" });
    await expect(ehc.getByText("Gesamtscore", { exact: true })).toHaveCount(1);
    await expect(ehc.getByText("+10,6 Punkte")).toBeVisible();
    await expect(ehc.getByText("78 → 81")).toBeVisible();
    await expect(ehc.getByText("Entfernung zum 52-Wochen-Hoch", { exact: true })).toHaveCount(1);
    await expect(ehc).toContainText("RS-Rating 81 · Kriterium ab 90 noch nicht erfüllt");
    await expect(ehc).toContainText("fehlen 9 Punkte");
    await expect(ehc.locator(".bg-amber-50")).toHaveCount(0);
    await expect(panel).not.toContainText(">=");
    await expect(panel).not.toContainText("Warum interessant");
    await expect(ehc.getByText("Fundamental", { exact: true })).not.toBeVisible();
    await ehc.getByText("Weitere Kennzahlen", { exact: true }).click();
    await expect(ehc.getByText("Fundamental", { exact: true })).toBeVisible();
    await expect(ehc.getByRole("link", { name: "Aktie genauer prüfen" })).toHaveAttribute("href", "/stocks/EHC");
    const noChange = panel.getByRole("article", { name: "TEST · Rang 2" });
    await expect(noChange).toContainText("Keine neue Verbesserung im gespeicherten Vergleich.");
    await expect(noChange).toContainText("Trend-Score 96");
    await expect(noChange).toContainText("Earnings in 2 Kalendertagen");
    await expect(noChange).toContainText("EPS mindestens 20%");
    await expect(panel.getByRole("article", { name: "GCT · Rang 3" })).toContainText("+5,6 Prozentpunkte");
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
    expect(errors).toEqual([]);
    await panel.screenshot({ path: `/tmp/boerse-top-daily-${beta ? "beta" : "private"}-${width}.png` });
    await context.close();
  });
}
