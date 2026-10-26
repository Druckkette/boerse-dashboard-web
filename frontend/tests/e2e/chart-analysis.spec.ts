import { test, expect } from "@playwright/test";

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
    page.getByText(/Zu wenig abgeschlossene Handelstage/),
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
