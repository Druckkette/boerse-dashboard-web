import { test, expect, webkit, type Page } from "@playwright/test";

test.use({
  baseURL: "http://127.0.0.1:18300",
  httpCredentials: {
    username: "owner",
    password: "test-only-private-password",
  },
});
const position = {
  ticker: "TEST",
  name: "Eine ausgesprochen lange Unternehmensbezeichnung mit mehreren Geschäftsbereichen",
  shares: 50,
  entry_price: 10,
  current_price: 15,
  currency: "EUR",
  market_value: 1234567890,
  pnl_abs: 250,
  pnl_pct: 50,
  weight_pct: 75,
  status: "ok",
  stop_price: 12,
  price_as_of: "2026-10-16",
  previous_close_date: "2026-10-15",
  daily_pnl_abs: -100,
  daily_pnl_pct: -1,
  atr_pct: null,
  risk_contribution: null,
  beta_balancer_score: null,
  position_loss_risk: 150,
  position_loss_risk_pct: 15,
};
const points = Array.from({ length: 30 }, (_, i) => ({
  date: `2026-01-${String(i + 1).padStart(2, "0")}`,
  portfolio_index: i === 4 ? null : 100 + i,
  sp500_index: 100 + i / 2,
  depot_value: 1000 + i,
  positions_value: 500,
  cash: 500,
}));
async function portfolio(page: Page) {
  await page.route("**/api/v1/portfolio/**", (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("snapshot"))
      return route.fulfill({
        json: {
          positions: [position],
          kpis: [
            {
              label: "Depotwert",
              value: "1,234,567,890 EUR",
              tone: "neutral",
              detail: "aus Import",
            },
            {
              label: "Gewinn/Verlust zum Vortagsschluss",
              value: "-100.00 EUR",
              tone: "bad",
              detail: "-1.00% zum Vortag",
            },
            {
              label: "Stop-Abdeckung",
              value: "100%",
              tone: "good",
              detail: "1 von 1 Positionen",
            },
          ],
          currency: "EUR",
          total_value: 1000,
          cash: 250,
          cash_ratio_pct: 25,
        },
      });
    if (path.endsWith("curve"))
      return route.fulfill({
        json: {
          model: "execution_history",
          source: "trade_republic_transactions",
          data_status: "limited",
          as_of: "2026-01-30",
          base_date: "2026-01-01",
          complete_points: 29,
          total_points: 30,
          message: "Für TEST fehlt ein belegter Tageskurs.",
          points,
        },
      });
    return route.fulfill({
      json: {
        items: [],
        positions: [],
        mappings: [],
        cash_flows: [],
        points: [],
        message: "Keine weiteren Daten",
        source: "missing",
      },
    });
  });
}
for (const width of [320, 390, 844, 1440])
  test(`new presentation fits ${width}px, switch persists and writes no financial data`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: 844 });
    await portfolio(page);
    const writes: string[] = [];
    const errors: string[] = [];
    page.on("request", (r) => {
      if (
        r.url().includes("/api/v1/") &&
        !["GET", "HEAD", "OPTIONS"].includes(r.method())
      )
        writes.push(r.url());
    });
    page.on("pageerror", (error) => errors.push(error.message));
    await page.goto("/portfolio");
    await expect(
      page.getByRole("heading", { name: "Positionen", exact: true }),
    ).toBeVisible();
    await expect(page.locator("html")).toHaveAttribute("data-ui", "product");
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBeTruthy();
    if (width < 1024) {
      await expect(
        page.getByRole("navigation", { name: "Mobile Hauptnavigation" }),
      ).toBeVisible();
      expect(
        await page
          .locator("main>header")
          .evaluate((e) => e.getBoundingClientRect().height),
      ).toBeLessThan(115);
    }
    await expect(page.locator("main")).toContainText("1.234.567.890 EUR");
    await page
      .getByRole("button", {
        name: "Zur klassischen Ansicht wechseln",
        exact: true,
      })
      .click();
    await expect(page.locator("html")).toHaveAttribute("data-ui", "classic");
    await page.reload();
    await expect(page.locator("html")).toHaveAttribute("data-ui", "classic");
    if (width < 1024)
      await expect(
        page.getByRole("combobox", { name: "Bereich öffnen" }),
      ).toBeVisible();
    await page
      .getByRole("button", { name: "Zur neuen Ansicht wechseln", exact: true })
      .click();
    await expect(page.locator("html")).toHaveAttribute("data-ui", "product");
    expect(writes).toEqual([]);
    expect(errors).toEqual([]);
    await page.screenshot({
      path: `/tmp/product-ui-portfolio-${width}.png`,
      fullPage: true,
    });
  });
test("stop draft survives focus changes, blocks view switching and saves only explicitly", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await portfolio(page);
  const writes: unknown[] = [];
  await page.route("**/api/v1/portfolio/positions/TEST/stop", (route) => {
    writes.push(route.request().postDataJSON());
    return route.fulfill({ status: 503, json: { detail: "Testfehler" } });
  });
  await page.goto("/portfolio");
  const stop = page
    .getByRole("textbox", { name: "TEST Stopp EUR", exact: true })
    .filter({ visible: true });
  await stop.fill("13.25");
  await stop.press("Tab");
  await expect(stop).toHaveValue("13.25");
  expect(writes).toEqual([]);
  await expect(
    page.getByRole("button", { name: "Zur klassischen Ansicht wechseln" }),
  ).toBeDisabled();
  await page
    .getByRole("button", { name: "TEST Stopp speichern" })
    .filter({ visible: true })
    .click();
  await expect.poll(() => writes.length).toBe(1);
  expect(writes[0]).toEqual({ stop_price: 13.25 });
  await expect(stop).toHaveValue("13.25");
  await stop.press("Escape");
  await expect(stop).toHaveValue("12");
  await expect(
    page.getByRole("button", { name: "Zur klassischen Ansicht wechseln" }),
  ).toBeEnabled();
});
test("chart defaults to scrolling, exposes true gaps, offers deliberate touch mode without a redundant data table", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await portfolio(page);
  await page.goto("/portfolio");
  const chart = page.locator("section").filter({
    has: page.getByRole("heading", { name: "Depotkurve", exact: true }),
  });
  const surface = chart.locator("[data-chart-surface]");
  await expect(surface).toHaveCSS("touch-action", "pan-y");
  await chart
    .getByRole("button", { name: "Werte ablesen & verschieben" })
    .click();
  await expect(surface).toHaveCSS("touch-action", "none");
  await chart.getByRole("button", { name: "Scrollen erlauben" }).click();
  await expect(surface).toHaveCSS("touch-action", "pan-y");
  await page.getByText("29 von 30 Tagen bewertet", { exact: false }).click();
  await expect(
    page.getByText(
      "Fehlende Depotbewertung: 2026-01-05 bis 2026-01-05 · 1 Tag",
      { exact: true },
    ),
  ).toBeVisible();
  await expect(chart.getByText("Chartwerte als Tabelle", { exact: true })).toHaveCount(0);
  await expect(chart.getByRole("table")).toHaveCount(0);
  await chart
    .getByRole("button", { name: "In den Chart hineinzoomen" })
    .click();
  await expect(
    chart.getByRole("button", { name: "Chart zurücksetzen" }),
  ).toBeEnabled();
  await chart.getByRole("button", { name: "Chart zurücksetzen" }).click();
});
const entry = {
  id: "entry-1",
  ticker: "TEST",
  instrument_name: "Test Aktie",
  isin: "US1234567890",
  source: "trade_republic",
  entry_type: "buy",
  trade_date: "2026-10-16",
  trade_time: "10:00:00",
  shares: 2,
  price: 100,
  currency: "EUR",
  gross_amount: 200,
  fees: 1,
  tax: 0,
  status: "open",
  context_status: "missing",
  context_label: "Historische Daten fehlen",
  has_note: true,
  basis_text: "Originalnotiz",
  primary_reasons: "Originalnotiz",
  sell_reason: "",
  questionnaire: { setup: "unknown", rule_deviation: "unknown" },
  chart_images: [],
  stock_snapshot: {},
  portfolio_snapshot: {},
  market_snapshot: {},
  sell_assessment: {},
  created_at: "2026-10-16T10:00:00Z",
};
test("journal filters apply atomically; one full-screen edit layer preserves failed note saves and back state", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const requests: string[] = [];
  const writes: unknown[] = [];
  await page.route("**/api/v1/trade-journal**", (route) => {
    const request = route.request(),
      path = new URL(request.url()).pathname;
    if (request.method() === "PATCH") {
      writes.push(request.postDataJSON());
      return route.fulfill({
        status: 503,
        json: { detail: "Testfehler beim Speichern" },
      });
    }
    if (path.endsWith("/entry-1")) return route.fulfill({ json: { entry } });
    requests.push(request.url());
    return route.fulfill({ json: { entries: [entry], total: 1 } });
  });
  await page.goto("/trade-journal");
  await page.getByRole("button", { name: "Filter (0)", exact: true }).click();
  const filters = page.getByRole("dialog", { name: "Journalfilter" });
  const count = requests.length;
  await filters
    .getByRole("combobox", { name: "Art", exact: true })
    .selectOption("buy");
  expect(requests.length).toBe(count);
  await filters.getByRole("button", { name: "Filter anwenden" }).click();
  await expect(page).toHaveURL(/type=buy/);
  await expect(page.getByRole("button", { name: "Filter (1)" })).toBeVisible();
  const row = page
    .getByRole("button")
    .filter({ hasText: "Test Aktie" })
    .first();
  await row.click();
  const details = page.getByRole("dialog", { name: "Handelsdetails" });
  await expect(details).toBeVisible();
  await details
    .getByRole("button", { name: "Notiz bearbeiten", exact: true })
    .click();
  await expect(page.getByRole("dialog")).toHaveCount(1);
  const note = details.getByRole("textbox", {
    name: "Entscheidungsgrund / Notiz",
  });
  await note.fill("Nicht verlieren");
  await details.getByRole("button", { name: "Speichern", exact: true }).click();
  await expect(
    details.getByText("Speichern fehlgeschlagen:", { exact: false }),
  ).toBeVisible();
  await expect(note).toHaveValue("Nicht verlieren");
  expect(writes).toHaveLength(1);
  expect(writes[0]).not.toHaveProperty("shares");
  expect(writes[0]).not.toHaveProperty("price");
  await details.getByRole("button", { name: "Abbrechen", exact: true }).click();
  await expect(
    details.getByRole("button", { name: "Notiz bearbeiten", exact: true }),
  ).toBeFocused();
  await details.getByRole("button", { name: "Zur Übersicht" }).click();
  await expect(details).toHaveCount(0);
  await expect(page).toHaveURL(/type=buy/);
  await expect(row).toBeFocused();
});
test("mobile beta More menu and classic fallback contain no private destinations", async ({
  browser,
}) => {
  const context = await browser.newContext({
    viewport: { width: 390, height: 844 },
    httpCredentials: { username: "beta", password: "test-only-beta-password" },
  });
  const page = await context.newPage();
  try {
    await page.goto("http://127.0.0.1:18301/");
    await page.getByRole("button", { name: "Mehr", exact: true }).click();
    const menu = page.getByRole("dialog", { name: "Weitere Bereiche" });
    await expect(menu).toBeVisible();
    expect(
      await menu
        .locator("a")
        .evaluateAll((links) => links.map((link) => link.getAttribute("href"))),
    ).toEqual(["/sectors", "/industry-groups"]);
    await page.keyboard.press("Escape");
    await expect(menu).not.toBeVisible();
    await page
      .getByRole("button", { name: "Zur klassischen Ansicht wechseln" })
      .click();
    await expect(
      page.getByRole("combobox", { name: "Bereich öffnen" }),
    ).toBeVisible();
    await expect(page.locator("main")).not.toContainText("Mein Depot");
  } finally {
    await context.close();
  }
});
for (const width of [320, 390])
  test(`WebKit mobile import and variant fallback at ${width}px`, async () => {
    const browser = await webkit.launch();
    const context = await browser.newContext({
      viewport: { width, height: 844 },
      isMobile: true,
      hasTouch: true,
      httpCredentials: {
        username: "owner",
        password: "test-only-private-password",
      },
    });
    const page = await context.newPage();
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    try {
      await page.route("**/api/v1/portfolio/isin-mappings", (route) =>
        route.fulfill({ json: { mappings: [] } }),
      );
      await page.goto("http://127.0.0.1:18300/portfolio/imports");
      await expect(
        page.getByLabel("TR-CSV auswählen", { exact: true }),
      ).toBeEnabled();
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      ).toBeTruthy();
      await page
        .getByRole("button", { name: "Zur klassischen Ansicht wechseln" })
        .click();
      await page.reload();
      await expect(page.locator("html")).toHaveAttribute("data-ui", "classic");
      await expect(
        page.getByLabel("TR-CSV auswählen", { exact: true }),
      ).toBeEnabled();
      expect(errors).toEqual([]);
    } finally {
      await context.close();
      await browser.close();
    }
  });

test("settings save bar appears only for drafts, avoids navigation and preserves failed saves", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const settings = {
    atr_threshold: 1.5,
    risk_per_position_pct: 1,
    target_risk_contribution: 0.2,
    max_depot_loss_lower_pct: 4,
    max_depot_loss_upper_pct: 8,
    position_monitor_enabled: false,
    position_monitor_interval_minutes: 1,
    position_monitor_threshold_atr: 1.5,
    position_monitor_atr_period: 14,
    position_monitor_lookback_days: 420,
    position_monitor_cooldown_hours: 18,
    position_monitor_reference: "previous_close",
    position_monitor_ma_alerts_enabled: true,
    position_monitor_assessment_alerts_enabled: true,
    position_monitor_assessment_interval_minutes: 15,
    pushover_enabled: false,
    pushover_configured: false,
    rs_rating_source: "computed",
    data_jobs_enabled: true,
    market_ampel_logic: "current",
    sell_rule_setup: {},
    assessment_score_weights: {
      overall: {
        technical: 30,
        fundamental: 30,
        chart: 30,
        moving_average: 10,
      },
      technical: {
        k4_rs_leadership: 30,
        k13_rs_dynamics: 20,
        rs_rating: 20,
        high_position: 10,
        up_down_volume: 10,
        cmf: 10,
      },
      fundamental: { fundamental_core: 80, k9_eps_sales_alignment: 20 },
      chart: {
        price_action_core: 60,
        k35_down_week_quality: 20,
        k38_hh_hl_good_close: 20,
      },
      moving_average: {
        price_above_200_sma: 20,
        price_above_50_sma: 15,
        price_above_21_ema: 10,
        price_above_10_sma: 5,
        ma_order: 15,
        persistence: 15,
        slope: 20,
      },
    },
  };
  const writes: unknown[] = [];
  await page.route("**/api/v1/settings", (route) => {
    if (route.request().method() === "PATCH") {
      writes.push(route.request().postDataJSON());
      return route.fulfill({
        status: 503,
        json: { detail: "Testfehler beim Speichern" },
      });
    }
    return route.fulfill({ json: settings });
  });
  await page.goto("/settings");
  const save = page.getByRole("button", {
    name: "Änderungen speichern",
    exact: true,
  });
  await expect(save).toHaveCount(0);
  await page
    .getByRole("combobox", { name: "Einstellungsbereich", exact: true })
    .selectOption("risk");
  const risk = page.getByRole("spinbutton", {
    name: "Risiko je Position (%)",
    exact: true,
  });
  await risk.fill("1.5");
  await expect(save).toBeEnabled();
  await expect(
    page.getByRole("button", { name: "Zur klassischen Ansicht wechseln" }),
  ).toBeDisabled();
  await save.click();
  await expect(
    page.getByRole("alert").filter({ hasText: "Testfehler beim Speichern" }),
  ).toBeVisible();
  await expect(risk).toHaveValue("1.5");
  expect(writes).toEqual([{ risk_per_position_pct: 1.5 }]);
  await page.getByRole("button", { name: "Verwerfen", exact: true }).click();
  await expect(risk).toHaveValue("1");
  await expect(save).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Zur klassischen Ansicht wechseln" }),
  ).toBeEnabled();
});

test("a touch swipe across the chart scrolls the page and enlarged content still fits", async ({
  browser,
}) => {
  const context = await browser.newContext({
    viewport: { width: 390, height: 844 },
    isMobile: true,
    hasTouch: true,
    httpCredentials: {
      username: "owner",
      password: "test-only-private-password",
    },
  });
  const page = await context.newPage();
  try {
    await portfolio(page);
    await page.goto("http://127.0.0.1:18300/portfolio");
    const surface = page.locator("[data-chart-surface]").first();
    await surface.scrollIntoViewIfNeeded();
    const box = (await surface.boundingBox())!;
    const x = box.x + box.width / 2;
    const y = Math.min(710, box.y + box.height * 0.8);
    const before = await page.evaluate(() => scrollY);
    const session = await context.newCDPSession(page);
    await session.send("Input.dispatchTouchEvent", {
      type: "touchStart",
      touchPoints: [{ x, y }],
    });
    for (let i = 1; i <= 10; i++) {
      await session.send("Input.dispatchTouchEvent", {
        type: "touchMove",
        touchPoints: [{ x, y: y - i * 18 }],
      });
      await page.waitForTimeout(16);
    }
    await session.send("Input.dispatchTouchEvent", {
      type: "touchEnd",
      touchPoints: [],
    });
    await expect
      .poll(() => page.evaluate(() => scrollY))
      .toBeGreaterThan(before + 80);
    await page.setViewportSize({ width: 780, height: 844 });
    await page.evaluate(() => {
      document.documentElement.style.zoom = "2";
      window.scrollTo(0, 0);
    });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBeTruthy();
    await expect(
      page.getByRole("button", { name: "Zur klassischen Ansicht wechseln" }),
    ).toBeVisible();
  } finally {
    await context.close();
  }
});

test("mobile stock assessment precedes details and uses a native area selector", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.route("**/api/v1/**", (route) => {
    if (!["GET", "HEAD", "OPTIONS"].includes(route.request().method()))
      return route.fulfill({
        status: 409,
        json: { detail: "Read-only UI test" },
      });
    if (new URL(route.request().url()).pathname.endsWith("/workspace"))
      return route.fulfill({
        json: {
          source: "database",
          watchlist: [],
          recent_tickers: [],
          todos: "",
        },
      });
    return route.continue();
  });
  await page.goto("/stocks/AAPL");
  await expect(
    page.getByRole("heading", { name: "Aktienbewertung", exact: true }),
  ).toBeVisible();
  const select = page.getByRole("combobox", {
    name: "Aktienanalyse Bereich",
    exact: true,
  });
  await expect(select).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
  await select.selectOption("chart");
  await expect(page).toHaveURL(/tab=chart/);
  await expect(
    page.getByRole("heading", {
      name: "AAPL Kurs und Relative Stärke",
      exact: true,
    }),
  ).toBeVisible();
  await select.selectOption("overview");
  await expect(
    page.getByRole("heading", { name: "Aktienbewertung", exact: true }),
  ).toBeVisible();
  expect(errors).toEqual([]);
});

test("a desktop stop draft survives a fresh snapshot with a changed quote", async ({
  page,
}) => {
  await page.clock.install();
  await page.setViewportSize({ width: 1440, height: 1000 });
  await portfolio(page);
  let snapshots = 0;
  await page.route("**/api/v1/portfolio/snapshot", (route) => {
    snapshots++;
    return route.fulfill({
      json: {
        positions: [{ ...position, current_price: 15 + snapshots }],
        kpis: [],
        currency: "EUR",
        total_value: 1000,
        cash: 0,
      },
    });
  });
  await page.goto("/portfolio");
  const stop = page
    .getByRole("textbox", { name: "TEST Stopp EUR", exact: true })
    .filter({ visible: true });
  await stop.fill("13.25");
  const snapshotsBeforeRefresh = snapshots;
  await page.clock.runFor(60_000);
  await expect.poll(() => snapshots).toBeGreaterThan(snapshotsBeforeRefresh);
  await expect(stop).toHaveValue("13.25");
  await expect(
    page.getByRole("button", { name: "Zur klassischen Ansicht wechseln" }),
  ).toBeDisabled();
});
