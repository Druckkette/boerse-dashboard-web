import { test, expect } from "@playwright/test";

test.use({ baseURL: "http://127.0.0.1:18300", httpCredentials: {
  username: "owner", password: "test-only-private-password",
} });

test("13F separates the complete trend from early filings on mobile", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.route("**/api/v1/stocks/AAPL/institutional/13f", route => route.fulfill({ json: {
    ticker: "AAPL", source: "database", as_of: "2026-06-30",
    item: { ticker: "AAPL", cusip: "037833100", report_period: "2026-06-30", previous_period: "2026-03-31", holder_count: 1000, large_holder_count: 800, trend: "positive", source_url: "https://www.sec.gov" },
    preliminary: { report_period: "2026-09-30", holder_count: 50, total_shares: 10000, total_value_usd: 2000000 },
    source_status: { checked_at: "2026-10-18T07:00:00Z", latest_filing_date: "2026-10-16", excluded_filings_count: 1 },
  } }));
  await page.goto("/stocks/AAPL?tab=institutions");
  const panel = page.locator("section").filter({ has: page.getByRole("heading", { name: "Institutionelle 13F-Trends" }) });
  await expect(panel).toContainText("2026-03-31 bis 2026-06-30");
  await expect(panel).toContainText("Neue Meldungen zum 2026-09-30 · vorläufig");
  await expect(panel).toContainText("fließt nicht in den Trend-Score ein");
  await expect(panel).toContainText("Neueste geladene Einreichung: 2026-10-16");
  await expect(panel).toContainText("widersprüchliche Quelldaten");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
});
