import { test, expect } from "@playwright/test";

test.use({
  baseURL: "http://127.0.0.1:18300",
  httpCredentials: {
    username: "owner",
    password: "test-only-private-password",
  },
});
const csv =
  "date,type,asset_class,name,symbol,shares,price,currency\n2026-01-02,BUY,STOCK,Costco,US22160K1051,2,100,USD\n";
const holding = {
  ticker: "COST",
  name: "Costco Wholesale Corporation",
  shares: 2,
  entry_price: 100,
  currency: "USD",
  buy_date: "2026-01-02",
  account: "Trade Republic",
  warnings: [],
};
const mapping = {
  isin: "US22160K1051",
  name: "Costco Wholesale Corporation",
  asset_class: "STOCK",
  ticker: "COST",
  source: "automatic",
  message: "Automatisch über die ISIN gefunden.",
  candidates: [],
};
const response = {
  ok: true,
  dry_run: true,
  rows_total: 1,
  rows_imported: 0,
  transactions_total: 1,
  cash_balance_estimate: 1234.56,
  positions: [holding],
  mappings: [mapping],
  skipped_positions: [],
  errors: [],
  warnings: ["Kurse werden im Hintergrund gesichert."],
};

for (const width of [320, 390, 1440])
  test(`TR file preview and save without overlapping controls at ${width}px`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: 844 });
    const writes: Record<string, unknown>[] = [],
      errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.route("**/api/v1/portfolio/isin-mappings", (route) =>
      route.fulfill({ json: { mappings: [{ ...mapping, source: "saved" }] } }),
    );
    await page.route(
      "**/api/v1/portfolio/imports/tr-transactions",
      async (route) => {
        const body = route.request().postDataJSON();
        writes.push(body);
        await route.fulfill({
          json: {
            ...response,
            dry_run: body.dry_run,
            rows_imported: body.dry_run ? 0 : 1,
          },
        });
      },
    );
    await page.goto("/portfolio/imports");
    const panel = page.getByRole("region", {
      name: "Trade-Republic-Import",
      exact: true,
    });
    await panel.getByLabel("TR-CSV auswählen", { exact: true }).setInputFiles({
      name: "Transaktionsexport-mit-einem-sehr-langen-Dateinamen.csv",
      mimeType: "text/csv",
      buffer: Buffer.from(csv),
    });
    await expect(
      panel.getByText("Alle zugeordnet", { exact: true }),
    ).toBeVisible();
    await panel
      .getByRole("button", {
        name: "Erkannte Zuordnungen anzeigen (1)",
        exact: true,
      })
      .click();
    await expect(
      panel.getByLabel("Ticker für US22160K1051", { exact: true }),
    ).toHaveValue("COST");
    expect(writes).toHaveLength(1);
    expect(writes[0].dry_run).toBe(true);
    await panel
      .locator("summary")
      .filter({ hasText: "offene Positionen ansehen" })
      .click();
    await expect(
      panel.getByText("COST · Costco Wholesale Corporation", { exact: true }),
    ).toBeVisible();
    const save = panel.getByRole("button", {
      name: "TR-Import speichern",
      exact: true,
    });
    await save.scrollIntoViewIfNeeded();
    expect(
      await save.evaluate((element) => {
        const rect = element.getBoundingClientRect();
        return element.contains(
          document.elementFromPoint(
            rect.x + rect.width / 2,
            rect.y + rect.height / 2,
          ),
        );
      }),
    ).toBe(true);
    await save.click();
    await expect(panel.getByText("Importiert", { exact: true })).toBeVisible();
    expect(writes).toHaveLength(2);
    expect(writes[1].isin_overrides).toEqual({ US22160K1051: "COST" });
    await expect(save).toBeDisabled();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    expect(
      await panel.evaluate(
        (element) =>
          Array.from(element.querySelectorAll("*")).filter(
            (item) =>
              item.getBoundingClientRect().width &&
              item.tagName !== "TEXTAREA" &&
              item.scrollWidth > item.clientWidth &&
              getComputedStyle(item).overflowX === "auto",
          ).length,
      ),
    ).toBe(0);
    expect(errors).toEqual([]);
    await page.screenshot({
      path: `/tmp/boerse-import-${width}.png`,
      fullPage: true,
    });
  });

test("ambiguous ticker is selectable and requires a fresh preview; new file clears overrides", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const writes: Record<string, unknown>[] = [];
  await page.route("**/api/v1/portfolio/isin-mappings", (route) =>
    route.fulfill({ json: { mappings: [] } }),
  );
  await page.route(
    "**/api/v1/portfolio/imports/tr-transactions",
    async (route) => {
      const body = route.request().postDataJSON();
      writes.push(body);
      const ticker = body.isin_overrides.US22160K1051 || "";
      await route.fulfill({
        json: {
          ...response,
          mappings: [
            {
              ...mapping,
              ticker,
              source: ticker ? "manual" : "missing",
              candidates: [
                { ticker: "COST", name: "Costco", exchange: "NASDAQ" },
                { ticker: "CTO.DE", name: "Costco", exchange: "XETRA" },
              ],
            },
          ],
          positions: ticker ? [holding] : [],
        },
      });
    },
  );
  await page.goto("/portfolio/imports");
  const panel = page.getByRole("region", {
    name: "Trade-Republic-Import",
    exact: true,
  });
  const upload = panel.getByLabel("TR-CSV auswählen", { exact: true });
  const file = {
    name: "test.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(csv),
  };
  await upload.setInputFiles(file);
  const save = panel.getByRole("button", {
    name: "TR-Import speichern",
    exact: true,
  });
  await expect(save).toBeDisabled();
  await panel
    .getByLabel("Börsenplatz für US22160K1051", { exact: true })
    .selectOption("COST");
  await expect(save).toBeDisabled();
  await panel
    .getByRole("button", { name: "Vorschau erneut prüfen", exact: true })
    .click();
  await expect(save).toBeEnabled();
  await upload.setInputFiles(file);
  await expect(
    panel.getByText("1 Zuordnungen offen", { exact: true }),
  ).toBeVisible();
  expect(writes[2].isin_overrides).toEqual({});
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});

test("failed preview stays visible and allows retry", async ({ page }) => {
  await page.route("**/api/v1/portfolio/isin-mappings", (route) =>
    route.fulfill({ json: { mappings: [] } }),
  );
  let calls = 0;
  await page.route(
    "**/api/v1/portfolio/imports/tr-transactions",
    async (route) => {
      if (++calls === 1)
        await route.fulfill({
          status: 503,
          json: { detail: "Suche vorübergehend nicht erreichbar" },
        });
      else await route.fulfill({ json: response });
    },
  );
  await page.goto("/portfolio/imports");
  const panel = page.getByRole("region", {
    name: "Trade-Republic-Import",
    exact: true,
  });
  await panel.getByLabel("TR-CSV auswählen", { exact: true }).setInputFiles({
    name: "test.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(csv),
  });
  await expect(panel.getByRole("alert")).toContainText(
    "Suche vorübergehend nicht erreichbar",
  );
  await expect(
    panel.getByRole("button", { name: "TR-Import speichern", exact: true }),
  ).toBeDisabled();
  await panel
    .getByRole("button", { name: "Vorschau erneut prüfen", exact: true })
    .click();
  await expect(
    panel.getByRole("button", { name: "TR-Import speichern", exact: true }),
  ).toBeEnabled();
});

test("inline portfolio import also fits a narrow phone", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 844 });
  await page.route("**/api/v1/portfolio/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/snapshot"))
      return route.fulfill({
        json: {
          positions: [],
          kpis: [],
          total_value: 0,
          cash: 0,
          currency: "EUR",
        },
      });
    if (path.endsWith("/tr-transactions"))
      return route.fulfill({ json: response });
    if (path.endsWith("/isin-mappings"))
      return route.fulfill({ json: { mappings: [] } });
    if (path.endsWith("/cash-flows"))
      return route.fulfill({ json: { cash_flows: [], cash_balance: 0 } });
    return route.fulfill({
      json: {
        points: [],
        positions: [],
        kpis: [],
        data_status: "missing",
        source: "missing",
      },
    });
  });
  await page.goto("/portfolio");
  await page
    .locator("summary")
    .filter({ hasText: /^Trade-Republic-Import und ISIN-Zuordnungen/ })
    .click();
  const panel = page.getByRole("region", {
    name: "Trade-Republic-Import",
    exact: true,
  });
  await panel
    .getByLabel("TR-CSV auswählen", { exact: true })
    .setInputFiles({
      name: "test.csv",
      mimeType: "text/csv",
      buffer: Buffer.from(csv),
    });
  await expect(
    panel.getByText("Alle zugeordnet", { exact: true }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  const bounds = await panel.boundingBox();
  expect(bounds!.x).toBeGreaterThanOrEqual(0);
  expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(320);
});

test("new preview clears a previous save error", async ({ page }) => {
  await page.route("**/api/v1/portfolio/isin-mappings", (route) =>
    route.fulfill({ json: { mappings: [] } }),
  );
  await page.route("**/api/v1/portfolio/imports/tr-transactions", (route) =>
    route.request().postDataJSON().dry_run
      ? route.fulfill({ json: response })
      : route.fulfill({
          status: 503,
          json: { detail: "Speichern vorübergehend nicht möglich" },
        }),
  );
  await page.goto("/portfolio/imports");
  const panel = page.getByRole("region", {
    name: "Trade-Republic-Import",
    exact: true,
  });
  await panel
    .getByLabel("TR-CSV auswählen", { exact: true })
    .setInputFiles({
      name: "test.csv",
      mimeType: "text/csv",
      buffer: Buffer.from(csv),
    });
  const save = panel.getByRole("button", {
    name: "TR-Import speichern",
    exact: true,
  });
  await expect(save).toBeEnabled();
  await save.click();
  await expect(panel.getByRole("alert")).toContainText(
    "Speichern vorübergehend nicht möglich",
  );
  await panel
    .getByRole("button", { name: "Vorschau erneut prüfen", exact: true })
    .click();
  await expect(save).toBeEnabled();
  await expect(panel.getByRole("alert")).toHaveCount(0);
});
