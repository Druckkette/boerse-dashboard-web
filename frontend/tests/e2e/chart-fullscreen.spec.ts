import { test, expect } from "@playwright/test";

test.use({
  baseURL: "http://127.0.0.1:18300",
  httpCredentials: { username: "owner", password: "test-only-private-password" },
  viewport: { width: 390, height: 844 },
  hasTouch: true,
  isMobile: true,
});

test.beforeEach(async ({ page, request }) => {
  await request.post("http://127.0.0.1:18380/__fixture/chart-reset");
  // iPhone / embedded browsers may not offer fullscreen for chart elements.
  await page.addInitScript(() => {
    Object.defineProperty(Element.prototype, "requestFullscreen", { configurable: true, value: undefined });
    Object.defineProperty(document, "fullscreenEnabled", { configurable: true, value: false });
  });
});

test("mobile chart enlarges without browser fullscreen and preserves the selected pattern and zoom", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/chart-analysis/IBKR");
  const chart = page.locator("section").filter({ has: page.getByRole("heading", { name: "IBKR · Tageschart", exact: true }) });
  const overlay = chart.getByTestId("pattern-overlays").locator("path");
  await expect(overlay).toHaveCount(1);
  await chart.getByRole("button", { name: "In den Chart hineinzoomen", exact: true }).click();
  const selectedPattern = await page.getByLabel("Muster im Chart", { exact: true }).inputValue();
  const readoutBefore = (await chart.locator(".pointer-events-none").textContent())!;
  const opener = chart.getByRole("button", { name: "Chart im Vollbild öffnen", exact: true });
  const scrollBefore = await page.evaluate(() => window.scrollY);
  await opener.click();

  const dialog = page.getByRole("dialog", { name: "IBKR · Tageschart · Vollbild", exact: true });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByTestId("pattern-overlays").locator("path")).toHaveCount(1);
  await expect(dialog.getByRole("button", { name: "Chart zurücksetzen", exact: true })).toBeEnabled();
  await expect(dialog.locator(".pointer-events-none")).toHaveText(readoutBefore);
  await expect.poll(() => dialog.evaluate((node) => {
    const box = node.getBoundingClientRect();
    return Math.abs(box.top) + Math.abs(box.left) + Math.abs(box.width - innerWidth) + Math.abs(box.height - innerHeight);
  })).toBeLessThan(2);
  await expect.poll(() => page.evaluate(() => document.body.style.overflow)).toBe("hidden");
  const close = dialog.getByRole("button", { name: "Vollbild schließen", exact: true });
  await expect(close).toBeFocused();
  const closeBox = await close.boundingBox();
  expect(closeBox!.width).toBeGreaterThanOrEqual(44);
  expect(closeBox!.height).toBeGreaterThanOrEqual(44);
  await close.click();

  await expect(dialog).not.toBeVisible();
  await expect(opener).toBeFocused();
  await expect(page.getByLabel("Muster im Chart", { exact: true })).toHaveValue(selectedPattern);
  await expect(chart.getByRole("button", { name: "Chart zurücksetzen", exact: true })).toBeEnabled();
  await expect(overlay).toHaveCount(1);
  await expect(chart.locator(".pointer-events-none")).toHaveText(readoutBefore);
  await expect.poll(() => page.evaluate(() => document.body.style.overflow)).toBe("");
  await expect.poll(() => page.evaluate((position) => Math.abs(window.scrollY - position), scrollBefore)).toBeLessThan(2);
  expect(errors).toEqual([]);
});

test("enlarged chart adapts to phone rotation and closes with Escape repeatedly", async ({ page }) => {
  await page.goto("/chart-analysis/IBKR");
  await expect(page.getByTestId("pattern-overlays").locator("path")).toHaveCount(1);
  const open = page.getByRole("button", { name: "Chart im Vollbild öffnen", exact: true });
  const dialog = page.getByRole("dialog", { name: "IBKR · Tageschart · Vollbild", exact: true });
  await open.click();
  await expect(dialog).toBeVisible();
  await page.setViewportSize({ width: 844, height: 390 });
  await expect.poll(() => dialog.evaluate((node) => Math.abs(node.getBoundingClientRect().height - innerHeight))).toBeLessThan(2);
  const surface = dialog.locator("[data-chart-surface]");
  await expect.poll(async () => (await surface.boundingBox())?.height ?? 0).toBeGreaterThan(100);
  await expect(dialog.getByTestId("pattern-overlays").locator("path")).toHaveCount(1);
  await dialog.getByText("Chartwerkzeuge · Marken, Vorlagen & Export", { exact: true }).click();
  await expect.poll(async () => (await surface.boundingBox())?.height ?? 0).toBeGreaterThanOrEqual(159);
  const tools = dialog.locator("details[open]");
  await tools.getByLabel("Bezeichnung", { exact: true }).fill("Testmarke");
  const exportButton = tools.getByRole("button", { name: "Chart als SVG speichern", exact: true });
  await exportButton.scrollIntoViewIfNeeded();
  await expect(exportButton).toBeInViewport();
  await expect(dialog.getByRole("button", { name: "Vollbild schließen", exact: true })).toBeInViewport();
  await page.keyboard.press("Tab");
  expect(await dialog.evaluate((node) => node.contains(document.activeElement))).toBeTruthy();
  await page.keyboard.press("Escape");
  await expect(dialog).not.toBeVisible();
  await expect(open).toBeFocused();
  await open.click();
  await expect(dialog).toBeVisible();
  await dialog.getByRole("button", { name: "Vollbild schließen", exact: true }).click();
  await expect(dialog).not.toBeVisible();
  await expect.poll(() => page.evaluate(() => document.body.style.overflow)).toBe("");
});

test("browser back from an enlarged chart restores page scrolling", async ({ page }) => {
  await page.goto("/chart-analysis");
  await page.getByLabel("Muster filtern", { exact: true }).selectOption("cup_with_handle");
  await page.getByLabel("Treffer nach Aktie filtern").fill("IBKR");
  await page.getByRole("link", { name: "IBKR · Cup with Handle", exact: true }).click();
  await expect(page.getByTestId("pattern-overlays").locator("path")).toHaveCount(1);
  await page.getByRole("button", { name: "Chart im Vollbild öffnen", exact: true }).click();
  await expect(page.getByRole("dialog", { name: "IBKR · Tageschart · Vollbild", exact: true })).toBeVisible();
  await page.goBack();
  await expect(page).toHaveURL(/\/chart-analysis$/);
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect.poll(() => page.evaluate(() => document.body.style.overflow)).toBe("");
});
