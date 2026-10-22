import { test, expect } from "@playwright/test";
test.use({
  baseURL: "http://127.0.0.1:18300",
  httpCredentials: {
    username: "owner",
    password: "test-only-private-password",
  },
});

test.beforeEach(async ({ request }) => {
  await request.post("http://127.0.0.1:18380/__fixture/desk-reset");
});

for (const width of [390, 1440])
  test(`watchlists and a currency-aware plan persist across navigation at ${width}px`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: 900 });
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.goto("/workspace");
    await page
      .getByLabel("Neue Liste", { exact: true })
      .fill("Ausbruchskandidaten");
    await page
      .getByRole("button", { name: "Liste anlegen", exact: true })
      .click();
    await page
      .getByRole("button", { name: "Ausbruchskandidaten · 0", exact: true })
      .click();
    await page.getByPlaceholder("Ticker, z. B. NVDA").fill("NVDA");
    await page.getByRole("button", { name: "Hinzufügen", exact: true }).click();
    await expect(
      page.getByRole("button", {
        name: "Ausbruchskandidaten · 1",
        exact: true,
      }),
    ).toBeVisible();
    await page
      .getByRole("button", { name: "Notizen & Status bearbeiten", exact: true })
      .click();
    await page
      .getByLabel("Notiz zu NVDA", { exact: true })
      .fill("Ausbruch nach Konsolidierung");
    const tags = page.getByLabel("Kennzeichnungen, mit Komma getrennt", {
      exact: true,
    });
    await tags.fill("Wachstum, Halbleiter");
    await tags.press("Enter");
    await expect(
      page.getByRole("heading", { name: "Liste bearbeiten", exact: true }),
    ).toHaveCount(0);
    await expect(page.locator("#watchlists")).toContainText(
      "Wachstum · Halbleiter",
    );
    await page.getByLabel("NVDA auswählen", { exact: true }).check();
    await page.getByLabel("Zielliste", { exact: true }).selectOption("default");
    await page
      .getByRole("button", { name: "1 Aktien kopieren", exact: true })
      .click();
    await expect(
      page.getByRole("button", { name: "Meine Watchlist · 1", exact: true }),
    ).toBeVisible();
    await page
      .locator("#watchlists")
      .getByRole("link", { name: "Einstieg planen", exact: true })
      .click();
    const form = page.locator("#einstieg");
    await expect(form.getByLabel("Aktie", { exact: true })).toHaveValue("NVDA");
    await form.getByLabel("Einstieg", { exact: true }).fill("100");
    await form.getByLabel("Stopp", { exact: true }).fill("90");
    await form
      .getByLabel("Begründung des Einstiegs", { exact: true })
      .fill("Ausbruch mit bestätigter Stärke");
    await form
      .getByLabel("Wann ist die Annahme widerlegt?", { exact: true })
      .fill("Kurs unter 90 USD");
    await form
      .getByRole("button", { name: "Plan berechnen", exact: true })
      .click();
    await expect(form).toContainText("11");
    await expect(form).toContainText("0,909091 EUR");
    await form
      .getByRole("button", {
        name: "Plan mit damaliger Bewertung dokumentieren",
        exact: true,
      })
      .click();
    await expect(page.locator("#plaene")).toContainText("NVDA · 11 Stück");
    await page.reload();
    await expect(page.locator("#plaene")).toContainText(
      "Ausbruch mit bestätigter Stärke",
    );
    await page
      .locator("#plaene")
      .getByLabel("Prüfnotiz zu NVDA", { exact: true })
      .fill("Kauf im Broker geprüft");
    await page
      .getByRole("button", { name: "Kauf dokumentieren", exact: true })
      .click();
    await expect(page.locator("#plaene")).toContainText("Kauf dokumentiert");
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBeTruthy();
    expect(errors).toEqual([]);
    await page.evaluate(() => window.scrollTo({ top: 0, behavior: "instant" }));
    await page.screenshot({
      path: `/tmp/boerse-desk-workspace-${width}.png`,
      fullPage: true,
    });
  });

test("alarm rules can be checked, acknowledged and paused without sending push messages", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 900 });
  await page.goto("/alerts");
  await page.getByLabel("Name", { exact: true }).fill("NVDA beobachten");
  await page
    .getByLabel("Aktie (für Datenqualität optional)", { exact: true })
    .fill("NVDA");
  await page.getByLabel("Schwelle in Kurswährung", { exact: true }).fill("100");
  await page.getByLabel("Ruhezeit ab (Berlin)", { exact: true }).fill("00:00");
  await page.getByLabel("Ruhezeit bis (Berlin)", { exact: true }).fill("00:00");
  await page
    .getByRole("button", { name: "Regel speichern", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "NVDA beobachten", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Bearbeiten", exact: true }).click();
  await page.getByLabel("Schwelle in Kurswährung", { exact: true }).fill("105");
  await page
    .getByRole("button", { name: "Änderungen speichern", exact: true })
    .click();
  await expect(
    page.locator("article").filter({
      has: page.getByRole("heading", {
        name: "NVDA beobachten",
        exact: true,
      }),
    }),
  ).toContainText("105");
  await page.getByRole("button", { name: "Jetzt prüfen", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Quittieren", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Quittieren", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Quittieren", exact: true }),
  ).toHaveCount(0);
  await page
    .getByLabel("Nur unquittierte Meldungen", { exact: true })
    .uncheck();
  await expect(page.getByText(/Quittiert /)).toBeVisible();
  await page.getByRole("button", { name: "Pausieren", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Aktivieren", exact: true }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
  await page.evaluate(() => window.scrollTo({ top: 0, behavior: "instant" }));
  await page.screenshot({
    path: "/tmp/boerse-desk-alerts-390.png",
    fullPage: true,
  });
});

test("additional accounts require preview and preserve the selected account and deduplication", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 900 });
  await page.goto("/portfolio/accounts");
  await page.getByLabel("Neues Depot", { exact: true }).fill("Langfristdepot");
  await page
    .getByRole("button", { name: "Depot anlegen", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Langfristdepot · EUR", exact: true })
    .click();
  const csv =
    "date,type,currency,amount,external_id\n2026-01-02,deposit,EUR,1000,test-cash-1\n";
  await page.getByLabel("CSV-Inhalt", { exact: true }).fill(csv);
  await page
    .getByRole("button", { name: "Import prüfen", exact: true })
    .click();
  await expect(
    page.getByText("1 Zeilen · 1 neue Buchungen · 0 bereits vorhanden", {
      exact: true,
    }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Geprüfte Buchungen übernehmen", exact: true })
    .click();
  await expect(
    page.getByRole("status").filter({ hasText: "Buchungen übernommen" }),
  ).toBeVisible();
  await page.getByLabel("CSV-Inhalt", { exact: true }).fill(csv);
  await page
    .getByRole("button", { name: "Import prüfen", exact: true })
    .click();
  await expect(
    page.getByText("1 Zeilen · 0 neue Buchungen · 1 bereits vorhanden", {
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", {
      name: "Geprüfte Buchungen übernehmen",
      exact: true,
    }),
  ).toBeDisabled();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
  await page.evaluate(() => window.scrollTo({ top: 0, behavior: "instant" }));
  await page.screenshot({
    path: "/tmp/boerse-desk-accounts-390.png",
    fullPage: true,
  });
});

test("calculator converts EUR equity and refuses a missing FX rate instead of silently relabeling it", async ({
  page,
}) => {
  await page.route("**/api/v1/portfolio/**", (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/snapshot"))
      return route.fulfill({
        json: {
          currency: "EUR",
          total_value: 10000,
          cash: 5000,
          positions: [],
          kpis: [],
        },
      });
    return route.fulfill({
      json: {
        points: [],
        items: [],
        cash_flows: [],
        transactions: [],
        message: "Keine Historie",
        data_status: "missing",
      },
    });
  });
  await page.goto("/portfolio");
  const calculator = page.locator("details").filter({
    has: page.getByRole("heading", {
      name: "Stückzahl- und Positionsgrößen-Rechner",
      exact: true,
    }),
  });
  await calculator.locator("summary").click();
  await expect(
    calculator.getByLabel("Depotwert USD", { exact: true }),
  ).toHaveValue("11000");
  await expect(calculator).toContainText("Umrechnung 1,1 USD je EUR");
  await page.route("**/api/v1/desk/fx?**", (route) =>
    route.fulfill({ status: 503, json: { detail: "Wechselkurs fehlt" } }),
  );
  await calculator
    .getByLabel("Kurswährung", { exact: true })
    .selectOption("CHF");
  await expect(calculator).toContainText("Stückzahl nicht verfügbar");
  await expect(calculator.getByText("Stückzahl", { exact: true })).toHaveCount(
    0,
  );
});

test("chart levels and log preferences persist and exports include a rendered chart", async ({
  page,
}) => {
  await page.goto("/stocks/NVDA?tab=chart");
  await expect(page.locator("[data-chart-surface]")).toBeVisible();
  await page
    .getByText("Chartwerkzeuge · Marken, Vorlagen & Export", { exact: true })
    .click();
  await page.getByLabel("Bezeichnung", { exact: true }).fill("Einstiegsmarke");
  await page.getByLabel("Horizontale Kursmarke", { exact: true }).fill("125");
  await page
    .getByRole("button", { name: "Marke hinzufügen", exact: true })
    .click();
  await page.getByLabel("Logarithmische Preisskala", { exact: true }).check();
  const download = page.waitForEvent("download");
  await page
    .getByRole("button", { name: "Chart als PNG speichern", exact: true })
    .click();
  expect((await download).suggestedFilename()).toMatch(/\.png$/);
  await page.reload();
  await page
    .getByText("Chartwerkzeuge · Marken, Vorlagen & Export", { exact: true })
    .click();
  await expect(
    page.getByText("Einstiegsmarke · 125", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByLabel("Logarithmische Preisskala", { exact: true }),
  ).toBeChecked();
});

test("own calendar events persist and portfolio filtering excludes unassigned macro events", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 900 });
  await page.goto("/calendar");
  await page.getByLabel("Titel", { exact: true }).fill("Makrotermin prüfen");
  await page.getByLabel("Art", { exact: true }).selectOption("macro");
  await page
    .getByRole("button", { name: "Termin speichern", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Makrotermin prüfen", exact: true }),
  ).toBeVisible();
  await page.getByLabel("Auswahl", { exact: true }).selectOption("portfolio");
  await expect(
    page.getByRole("heading", { name: "Makrotermin prüfen", exact: true }),
  ).toHaveCount(0);
  await page.getByLabel("Auswahl", { exact: true }).selectOption("all");
  await expect(
    page.getByRole("heading", { name: "Makrotermin prüfen", exact: true }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
  await page.evaluate(() => window.scrollTo({ top: 0, behavior: "instant" }));
  await page.screenshot({
    path: "/tmp/boerse-desk-calendar-390.png",
    fullPage: true,
  });
});

test("performance keeps cashflow result, annual personal return and benchmark distinct", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 900 });
  await page.route("**/api/v1/desk/performance?**", (route) => {
    const benchmark = new URL(route.request().url()).searchParams.get(
      "benchmark",
    );
    return route.fulfill({
      json: {
        currency: "EUR",
        start: "2026-01-02",
        end: "2026-10-21",
        twr_pct: 5,
        mwr_annual_pct: 8,
        max_drawdown_pct: -12,
        period_result: 500,
        external_flow: 1000,
        benchmark,
        benchmark_return_pct: 4,
        benchmark_note: "Kursrendite in EUR",
        note: "Cashflows am Tagesende",
        covered_points: 2,
        total_points: 2,
        complete: true,
        points: [
          {
            date: "2026-01-02",
            portfolio_index: 100,
            benchmark_index: 100,
            depot_value: 10000,
          },
          {
            date: "2026-10-21",
            portfolio_index: 105,
            benchmark_index: 104,
            depot_value: 11500,
          },
        ],
      },
    });
  });
  await page.goto("/portfolio/performance");
  await expect(
    page.getByText("Zeitgewichtete Rendite (TWR)", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("Persönliche Rendite (XIRR, jährlich)", { exact: true }),
  ).toBeVisible();
  await page
    .getByLabel("Vergleichsmaßstab", { exact: true })
    .selectOption("QQQ");
  await expect(
    page.getByText("QQQ · Kursrendite", { exact: true }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
  await page.evaluate(() => window.scrollTo({ top: 0, behavior: "instant" }));
  await page.screenshot({
    path: "/tmp/boerse-desk-performance-390.png",
    fullPage: true,
  });
});

test("mobile screening preserves ticker, warnings and all existing score components", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 900 });
  const row = {
    ticker: "NVDA",
    name: "NVIDIA",
    as_of: "2026-10-21",
    overall_score: 88,
    overall_status: "available",
    technical_score: 85,
    fundamental_score: 90,
    moving_average_score: 86,
    chart_behavior_score: 89,
    rs_rating: 95,
    warnings_count: 1,
    top_warning: "Quartalszahlen stehen bevor",
    verdict_tone: "good",
    verdict_label: "Stark",
    fundamentals_available: true,
    rs_line_available: true,
    institutional_available: true,
    prices_stale: false,
  };
  await page.route("**/api/v1/stocks/screening?**", (route) =>
    route.fulfill({
      json: {
        rows: [row],
        total_count: 1,
        criteria: [],
        criterion_options: [],
        summary: { records_written: 1 },
      },
    }),
  );
  await page.goto("/stocks");
  await page.getByRole("button", { name: /Aktienbewertung Ranking/ }).click();
  const cards = page.locator(".stock-research-cards").first();
  await expect(
    cards.getByRole("link", { name: "NVDA", exact: true }),
  ).toBeVisible();
  await expect(cards).toContainText("Quartalszahlen stehen bevor");
  await cards
    .getByText("Alle Teilbewertungen & Daten", { exact: true })
    .click();
  await expect(cards).toContainText("85");
  await expect(cards).toContainText("90");
  await expect(cards).toContainText("86");
  await expect(cards).toContainText("89");
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
  await page.evaluate(() => window.scrollTo({ top: 0, behavior: "instant" }));
  await page.screenshot({
    path: "/tmp/boerse-desk-screening-390.png",
    fullPage: true,
  });
});
