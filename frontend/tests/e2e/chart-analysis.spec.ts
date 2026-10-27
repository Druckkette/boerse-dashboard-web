import { test, expect, type Page } from "@playwright/test";

test.use({
  baseURL: "http://127.0.0.1:18300",
  httpCredentials: {
    username: "owner",
    password: "test-only-private-password",
  },
});
test.beforeEach(async ({ request }) => {
  await request.post("http://127.0.0.1:18380/__fixture/chart-reset");
});

for (const mode of ["product", "classic"])
  for (const width of [1440, 390])
    test(`real cup opens with overlays and ticker search at ${width}px (${mode})`, async ({
      page,
    }) => {
      await page
        .context()
        .addCookies([
          { name: "dashboard-ui", value: mode, url: "http://127.0.0.1:18300" },
        ]);
      await page.setViewportSize({ width, height: 1000 });
      const errors: string[] = [];
      page.on("pageerror", (error) => errors.push(error.message));
      await page.goto("/chart-analysis");
      await expect(
        page.getByRole("heading", { name: "Chartanalyse", exact: true }),
      ).toBeVisible();
      await page
        .getByLabel("Muster filtern", { exact: true })
        .selectOption("cup_with_handle");
      await page.getByLabel("Treffer nach Aktie filtern").fill("IBKR");
      await page
        .getByRole("link", { name: "IBKR · Cup with Handle", exact: true })
        .click();
      await expect(page).toHaveURL(/chart-analysis\/IBKR\?pattern=/);
      await expect(
        page.getByTestId("pattern-overlays").locator("path"),
      ).toHaveCount(1);
      await expect(
        page.getByRole("heading", { name: /Cup with Handle ·/ }),
      ).toBeVisible();
      await page.getByLabel("Muster einzeichnen", { exact: true }).uncheck();
      await expect(
        page.getByTestId("pattern-overlays").locator("path"),
      ).toHaveCount(0);
      await page.getByLabel("Muster einzeichnen", { exact: true }).check();
      await page.screenshot({
        path: `/tmp/chart-analysis-${mode}-${width}.png`,
        fullPage: true,
      });
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= window.innerWidth,
        ),
      ).toBeTruthy();
      await page
        .getByLabel("Aktie im Chart öffnen", { exact: true })
        .fill("TBBK");
      await page
        .getByRole("button", { name: "Chart öffnen", exact: true })
        .click();
      await expect(page).toHaveURL(/chart-analysis\/TBBK\?refresh=1$/);
      await expect(
        page.getByLabel("Muster im Chart", { exact: true }),
      ).toContainText("Cup without Handle");
      expect(errors).toEqual([]);
    });

test("saved cup parameters survive reload and invalidate an old scan", async ({
  page,
}) => {
  await page.goto("/chart-analysis");
  await page.getByText("Musterparameter anpassen", { exact: true }).click();
  const asymmetry = page.getByLabel("Cup: Maximales Zeitverhältnis der Seiten", {
    exact: true,
  });
  await expect(asymmetry).toHaveValue("3");
  await expect(asymmetry).toHaveAccessibleDescription(
    /3 erlaubt eine bis zu dreimal längere Seite/,
  );
  await page.getByLabel("Cup: Maximale Tiefe (%)", { exact: true }).fill("40");
  await asymmetry.fill("2");
  await page
    .getByRole("button", { name: "Parameter speichern", exact: true })
    .click();
  await expect(page.getByText(/Die Parameter wurden geändert/)).toBeVisible();
  await page.reload();
  await page.getByText("Musterparameter anpassen", { exact: true }).click();
  await expect(
    page.getByLabel("Cup: Maximale Tiefe (%)", { exact: true }),
  ).toHaveValue("40");
  await expect(asymmetry).toHaveValue("2");
  await asymmetry.fill("3");
  const saved = page.waitForResponse(
    (response) =>
      response.url().endsWith("/chart-analysis/config") &&
      response.request().method() === "PUT" &&
      response.ok(),
  );
  await page
    .getByRole("button", { name: "Parameter speichern", exact: true })
    .click();
  await saved;
  await page.reload();
  await page.getByText("Musterparameter anpassen", { exact: true }).click();
  await expect(asymmetry).toHaveValue("3");
  await page
    .getByRole("button", { name: "Universum nach Mustern scannen" })
    .click();
  await expect(page.getByText(/Die Parameter wurden geändert/)).toHaveCount(0);
  await page
    .getByLabel("Muster filtern", { exact: true })
    .selectOption("cup_with_handle");
  await page.getByLabel("Treffer nach Aktie filtern").fill("IBKR");
  await expect(
    page.getByRole("link", { name: "IBKR · Cup with Handle", exact: true }),
  ).toHaveCount(0);
});

test("historical cutoff and a ticker with no data remain explicit", async ({
  page,
}) => {
  await page.goto("/chart-analysis/IBKR");
  await page
    .getByLabel("Historischer Prüfzeitpunkt", { exact: true })
    .fill("2025-05-01");
  await expect(
    page.getByLabel("Muster im Chart", { exact: true }),
  ).not.toContainText("Cup with Handle");
  await page.goto("/chart-analysis/NODATA");
  await expect(
    page.getByRole("status").filter({ hasText: /Keine abgeschlossenen Kursdaten|Zu wenig abgeschlossene Handelstage/ }),
  ).toBeVisible();
  await expect(page.getByTestId("pattern-overlays")).toHaveCount(0);
  await expect(
    page.getByText(/Kein Basismuster erfüllt die eingestellten Regeln/),
  ).toBeVisible();
});

test("all historical pattern types render their geometry", async ({ page }) => {
  for (const [ticker, kind] of [
    ["TBBK", "Cup without Handle"],
    ["NFLX", "Double Bottom"],
    ["RKLB", "High Tight Flag"],
    ["IBKR", "Box"],
  ]) {
    await page.goto(`/chart-analysis/${ticker}`);
    const option = page
      .getByLabel("Muster im Chart", { exact: true })
      .getByRole("option")
      .filter({ hasText: kind })
      .first();
    await expect(option).toBeAttached();
    await page
      .getByLabel("Muster im Chart", { exact: true })
      .selectOption((await option.getAttribute("value")) || "");
    await expect(
      page.getByTestId("pattern-overlays").locator("path"),
    ).toHaveCount(1);
    await page.screenshot({
      path: `/tmp/chart-analysis-example-${ticker}-${kind.replaceAll(" ", "-")}.png`,
      fullPage: true,
    });
  }
});

test("changing chart parameters never substitutes another pattern for the selected cup", async ({
  page,
}) => {
  await page.goto("/chart-analysis/IBKR");
  const picker = page.getByLabel("Muster im Chart", { exact: true });
  const cup = picker
    .getByRole("option")
    .filter({ hasText: "Cup with Handle" })
    .first();
  await expect(cup).toBeAttached();
  await picker.selectOption((await cup.getAttribute("value")) || "");
  await page.getByText("Musterparameter anpassen", { exact: true }).click();
  await page.getByLabel("Cup: Maximale Tiefe (%)", { exact: true }).fill("40");
  await page
    .getByRole("button", { name: "Parameter speichern", exact: true })
    .click();
  await expect(
    page.getByText(/Der ausgewählte Treffer ist mit diesem Datenstand/),
  ).toBeVisible();
  await expect(
    page.getByTestId("pattern-overlays").locator("path"),
  ).toHaveCount(0);
});

test("explicit ticker search queues one background refresh for missing prices", async ({
  page,
}) => {
  let writes = 0;
  await page.route("**/api/v1/jobs", async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    writes++;
    expect(route.request().postDataJSON()).toEqual({
      type: "refresh_stock_detail",
      payload: { tickers: ["NODATA"] },
    });
    await route.fulfill({
      json: { job: { job_id: "test-automatic", status: "queued" } },
    });
  });
  await page.route("**/api/v1/jobs/test-automatic?*", (route) =>
    route.fulfill({
      json: {
        job: {
          job_id: "test-automatic",
          status: "failed",
          error_message: "Test: Kurse derzeit nicht verfügbar",
        },
      },
    }),
  );
  await page.goto("/chart-analysis");
  await page
    .getByLabel("Aktie im Chart öffnen", { exact: true })
    .fill("NODATA");
  await page.getByRole("button", { name: "Chart öffnen", exact: true }).click();
  await expect(
    page.getByText("Test: Kurse derzeit nicht verfügbar", { exact: true }),
  ).toBeVisible();
  expect(writes).toBe(1);
});

test("data quality separates partial histories, suspected jumps and unavailable tickers with bounded lists", async ({
  page,
}) => {
  const skipped = Array.from({ length: 80 }, (_, index) => ({
    ticker: `MISS${String(index).padStart(3, "0")}`,
    code: "missing_history",
    reason: "Keine gespeicherten Kurse vorhanden.",
  }));
  const partial = [
    { ticker: "IBKR", code: "extreme_jump", reason: "Auffälliger Kurssprung; Split oder echte Kursbewegung prüfen." },
    { ticker: "GAP", code: "gap", reason: "Datenlücke zwischen zwei Handelstagen." },
    ...Array.from({ length: 38 }, (_, index) => ({
      ticker: `PART${String(index).padStart(3, "0")}`,
      code: "invalid_ohlc",
      reason: "Ungültige Tageskurse; andere Abschnitte wurden geprüft.",
    })),
  ];
  await page.route("**/api/v1/chart-analysis/results?*", (route) => route.fulfill({
    json: {
      available: true, obsolete: false, generated_at: "2026-10-26T18:00:00Z",
      scanned_count: 121, analysed_count: 41, partial_count: 40, skipped_count: 80,
      skipped, quality_issues: [...skipped, ...partial],
      quality_counts: { missing_history: 80, extreme_jump: 1, gap: 1, invalid_ohlc: 38 },
      repair_summary: { attempted: 30, succeeded: 20, failed: 10, deferred: 90 },
      current_parameter_hash: "test", total: 0, offset: 0, limit: 100, rows: [],
    },
  }));
  await page.goto("/chart-analysis");
  const availability = page.getByLabel("Auswertbarkeit des Aktienuniversums");
  await expect(availability.getByText("Vollständig auswertbar").locator("..").getByRole("definition")).toHaveText("1");
  await expect(availability.getByText("Teilweise auswertbar").locator("..").getByRole("definition")).toHaveText("40");
  await expect(availability.getByText("Nicht auswertbar").locator("..").getByRole("definition")).toHaveText("80");
  await expect(page.getByText(/Kursdaten nachladen: 30 Versuche · 20 behoben · 10 nicht behoben · 90 aufgeschoben/)).toBeVisible();
  await page.getByText("Datenqualität und ausgeschlossene Aktien ansehen", { exact: true }).click();
  const issues = page.getByRole("list", { name: "Datenhinweise", exact: true });
  await expect(issues.getByRole("listitem")).toHaveCount(50);
  await page.getByRole("button", { name: "Weitere Hinweise", exact: true }).click();
  await expect(issues.getByRole("listitem")).toHaveCount(50);
  await page.getByLabel("Datenhinweise nach Aktie filtern").fill("MISS079");
  await expect(issues.getByRole("listitem")).toHaveCount(1);
  await expect(issues.getByRole("link", { name: "MISS079", exact: true })).toHaveAttribute("href", "/chart-analysis/MISS079");
  await page.getByLabel("Datenhinweise nach Aktie filtern").clear();
  await page.getByLabel("Datenhinweise nach Auswertbarkeit filtern").selectOption("partial");
  await expect(issues.getByRole("listitem")).toHaveCount(40);
  await page.getByLabel("Datenhinweise nach Grund filtern").selectOption("jumps");
  await expect(issues.getByRole("listitem")).toHaveCount(1);
  await expect(page.getByText(/Ein auffälliger Kurssprung ist ein Verdachtsfall/)).toBeVisible();
  await issues.getByRole("link", { name: "IBKR", exact: true }).click();
  await expect(page).toHaveURL(/chart-analysis\/IBKR$/);
});

async function mockPartialChart(page: Page, historical = false) {
  await page.route("**/api/v1/chart-analysis/IBKR", async (route) => {
    const response = await route.fetch();
    const chart = await response.json();
    await route.fulfill({
      json: {
        ...chart,
        quality: {
          partial: true, segment_count: 3, analysed_bar_count: 400,
          excluded_bar_count: 1, boundary_count: 2,
          issues: [
            { code: "invalid_ohlc", reason: "Ungültige OHLC-Daten am 2024-08-01.", date: "2024-08-01" },
            { code: "extreme_jump", reason: "Kurssprung am 2024-09-01 bleibt ein Verdachtsfall.", date: "2024-09-01" },
          ],
        },
        patterns: chart.patterns.map((pattern: { kind: string; warnings: string[] }) => ({
          ...pattern,
          continuity_limited: historical && pattern.kind === "cup_with_handle",
          segment_end: historical && pattern.kind === "cup_with_handle" ? "2025-06-30" : undefined,
          warnings: [...pattern.warnings, "Datenabschnitt endet; spätere Entwicklung ist nicht geprüft."],
        })),
      },
    });
  });
}

test("partial chart retains valid patterns and explains isolated data boundaries", async ({ page }) => {
  await mockPartialChart(page);
  await page.goto("/chart-analysis/IBKR");
  await expect(page.getByText("Teilweise auswertbar", { exact: true })).toBeVisible();
  await expect(page.getByText(/400 Handelstage in 3 getrennten Kursabschnitten geprüft · 1 Tageskurs ausgelassen/)).toBeVisible();
  await expect(page.getByTestId("pattern-overlays").locator("path")).toHaveCount(1);
  await expect(page.getByText("Datenabschnitt endet; spätere Entwicklung ist nicht geprüft.", { exact: true })).toBeVisible();
  await page.getByText("Datenhinweise zu diesem Chart (2)", { exact: true }).click();
  await expect(page.getByText(/Kurssprung am 2024-09-01 bleibt ein Verdachtsfall/)).toBeVisible();
  await expect(page.getByText(/Kurssprünge · Verdachtsfälle:/)).toBeVisible();
});

test("historical pattern status is dated above the chart and clears for another section", async ({ page }) => {
  await mockPartialChart(page, true);
  await page.goto("/chart-analysis/IBKR");
  const picker = page.getByLabel("Muster im Chart", { exact: true });
  const historical = picker.getByRole("option").filter({ hasText: "Historisch · Cup with Handle" }).first();
  await expect(historical).toBeAttached();
  await picker.selectOption((await historical.getAttribute("value")) || "");
  const banner = page.getByRole("status", { name: "Historischer Musterstatus", exact: true });
  await expect(banner).toContainText("geprüft bis 30.6.2025");
  await expect(banner).toContainText("die heutige Gültigkeit des Musters ist unbekannt");
  await expect(page.getByRole("heading", { name: /Cup with Handle · Historisch:/ })).toBeVisible();
  const chart = page.getByText("IBKR · Tageschart", { exact: true });
  expect((await banner.boundingBox())!.y).toBeLessThan((await chart.boundingBox())!.y);
  await expect(page.getByTestId("pattern-overlays").locator("path")).toHaveCount(1);
  const current = picker.locator("option:not([disabled])").filter({ hasNotText: "Historisch" }).first();
  await picker.selectOption((await current.getAttribute("value")) || "");
  await expect(banner).toHaveCount(0);
  await expect(page.getByRole("heading", { name: /Historisch:/ })).toHaveCount(0);
});
