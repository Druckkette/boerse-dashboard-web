import { test, expect } from "@playwright/test";

for (const width of [1440, 390]) {
  test(`private home separates decisions, earnings and changes at ${width}px`, async ({ browser }) => {
    const context = await browser.newContext({ viewport: { width, height: 1000 }, httpCredentials: { username: "owner", password: "test-only-private-password" } });
    const page = await context.newPage();
    const errors: string[] = [];
    const calls: string[] = [];
    page.on("pageerror", error => errors.push(error.message));
    page.on("request", request => { if (request.url().includes("/api/v1/")) calls.push(new URL(request.url()).pathname); });
    const watchlist = Array.from({ length: 12 }, (_, i) => ({ ticker: `WATCH${i}`, name: `Watch company ${i}`, overall_score: 80 + i, data_status: "available", verdict_tone: "good", as_of: "2026-10-08" }));
    const data = {
      generated_at: "2026-10-09T08:00:00Z", errors: [],
      market: { indices: [{ ticker: "^GSPC", label: "S&P 500", phase: "gelb_rally_unter_druck", phase_label: "Rally unter Druck", phase_status: "available", status: "available", previous_phase: "gruen", previous_phase_label: "Grün", previous_phase_as_of: "2026-10-07", as_of: "2026-10-08", close: 7000, change_pct: -1 }], phase_label: "Rally unter Druck", phase: "gelb_rally_unter_druck", status: "available", logic: "ibd", session: { phase: "closed", last_completed_as_of: "2026-10-08" } },
      portfolio: { positions_count: 3, positions: [], stop_coverage_count: 2, stop_coverage_total: 3 }, review_positions_count: 3,
      portfolio_alerts: [
        { id: "sell:APP", ticker: "APP", category: "action", label: "Verkaufen", tone: "bad", detail: "Bestätigter Bruch der 21-EMA", recommendation_pct: 50, last_seen_date: "2026-10-08", generated_at: "2026-10-08T21:30:00Z", freshness: "current", href: "/sell-monitor/APP" },
        { id: "sell:WAIT", ticker: "WAIT", category: "observe", label: "Beobachten", tone: "warning", detail: "Bestätigung ausstehend · Signal offen", href: "/sell-monitor/WAIT" },
        { id: "sell:OLD", ticker: "OLD", category: "data", label: "Daten prüfen", tone: "warning", detail: "Verkaufsmonitor nicht aktuell", signal: "Unter 50-SMA", last_seen_date: "2026-10-02", generated_at: "2026-10-02T21:30:00Z", freshness: "stale", href: "/sell-monitor/OLD" },
      ],
      earnings: { today: "2026-10-09", status: "available", rows: [
        { ticker: "APP", name: "AppLovin", date: "2026-10-09", days_until: 0, time: "amc", source: "nasdaq", scopes: ["portfolio"], href: "/stocks/APP" },
        { ticker: "WATCH0", name: "Watch company 0", date: "2026-10-10", days_until: 1, time: "", source: "fmp", scopes: ["watchlist"], href: "/stocks/WATCH0" },
        { ticker: "LATER", name: "Later company", date: "2026-10-28", days_until: 19, time: "bmo", source: "fmp", scopes: ["portfolio"], href: "/stocks/LATER" },
      ] },
      changes: Array.from({ length: 9 }, (_, i) => ({ ticker: `CHANGE${i}`, name: `Changed company ${i}`, scopes: i === 8 ? ["watchlist"] : ["portfolio"], kind: "score", summary: "Stärke verloren", details: ["Score 82 → 74", "RS 91 → 84"], as_of: "2026-10-08", previous_as_of: "2026-10-07", href: `/stocks/CHANGE${i}`, tone: "warning" })),
      priorities: [], priorities_total: 0, sell_rows: [], opportunities: [], industry_groups: [], watchlist, watchlist_total: 12,
    };
    await page.route("**/api/v1/home", route => route.fulfill({ json: data }));
    await page.route("**/api/v1/workspace", route => route.fulfill({ json: { source: "database", watchlist: watchlist.map(row => row.ticker), recent_tickers: [], todos: "" } }));
    await page.route("**/api/v1/portfolio/snapshot", route => route.fulfill({ json: { kpis: [{ label: "Gewinn/Verlust zum Vortagsschluss", value: "+100 EUR", detail: "Letzter abgeschlossener Handelstag", tone: "good" }], positions: [] } }));
    await page.route("**/api/v1/portfolio/buy-strength**", route => route.fulfill({ json: { items: [] } }));
    await page.goto("http://127.0.0.1:18300/");
    const portfolio = page.locator("section").filter({ has: page.getByRole("heading", { name: "Mein Depot", exact: true }) });
    const earnings = page.locator("section").filter({ has: page.getByRole("heading", { name: "Anstehende Earnings", exact: true }) });
    const changes = page.locator("section").filter({ has: page.getByRole("heading", { name: "Was hat sich verändert?", exact: true }) });
    await expect(portfolio).toContainText("Tranche 50 %");
    await expect(portfolio).toContainText("Bestätigung ausstehend");
    await expect(portfolio).toContainText("Aktualität prüfen");
    await expect(portfolio).not.toContainText("Earnings");
    await expect(page.getByText("Aufgaben & Veränderungen", { exact: true })).toHaveCount(0);
    await expect(earnings).toContainText("AppLovin");
    await expect(earnings).not.toContainText("WATCH0");
    await earnings.getByLabel("Watchlist einbeziehen").check();
    await expect(earnings).toContainText("WATCH0");
    await expect(earnings).toContainText("Veröffentlichungszeit unbekannt");
    await earnings.getByLabel("Earnings-Zeitraum").selectOption("30");
    await expect(earnings).toContainText("LATER");
    await changes.getByRole("button", { name: "Alle 9 Veränderungen anzeigen" }).click();
    await expect(changes).toContainText("CHANGE8");
    await changes.getByRole("button", { name: "Watchlist", exact: true }).click();
    await expect(changes).toContainText("CHANGE8");
    await expect(changes).not.toContainText("CHANGE0");
    const watch = page.locator("section").filter({ has: page.getByRole("heading", { name: "Meine Watchlist", exact: true }) });
    await watch.getByRole("button", { name: "Alle 12 Aktien anzeigen" }).click();
    await expect(watch).toContainText("WATCH11");
    await expect(watch).toContainText("91");
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
    expect(errors).toEqual([]);
    expect(calls.some(path => path.includes("/refresh"))).toBeFalsy();
    expect(calls.some(path => /notifications|diagnostics/.test(path))).toBeFalsy();
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({ path: `/tmp/boerse-home-${width}.png`, fullPage: true });
    await context.close();
  });
}
