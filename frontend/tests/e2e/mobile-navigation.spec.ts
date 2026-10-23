import { test, expect } from "@playwright/test";

test.use({
  baseURL: "http://127.0.0.1:18300",
  httpCredentials: { username: "owner", password: "test-only-private-password" },
});

for (const width of [320, 390]) {
  test(`market sections and current mobile destination are recognizable at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 844 });
    await page.goto("/market");
    const nav = page.getByRole("navigation", { name: "Mobile Hauptnavigation" });
    const market = nav.getByRole("link", { name: "Markt", exact: true });
    await expect(market).toHaveAttribute("aria-current", "page");
    await expect(market).toHaveCSS("color", "rgb(17, 94, 89)");
    await expect(market.locator("span").first()).toHaveCSS("background-color", "rgb(217, 239, 234)");
    await expect(nav.locator('[aria-current="page"]')).toHaveCount(1);
    const jumps = page.getByRole("navigation", { name: "Marktübersicht Bereiche" });
    await expect(jumps.getByText("Direkt zum Bereich")).toBeVisible();
    for (const link of await jumps.getByRole("link").all()) {
      const box = await link.boundingBox();
      expect(box!.height).toBeGreaterThanOrEqual(44);
      await expect(link).toHaveCSS("border-top-style", "solid");
      const href = await link.getAttribute("href");
      await expect(page.locator(href!)).toHaveCount(1);
    }
    await jumps.getByRole("link", { name: "Marktbreite", exact: true }).click();
    await expect(page).toHaveURL(/#breadth$/);
    await expect(page.locator("#breadth")).toBeInViewport();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({ path: `/tmp/mobile-market-navigation-${width}.png` });
    await page.goto("/portfolio/performance");
    await expect(nav.getByRole("link", { name: "Depot", exact: true })).toHaveAttribute("aria-current", "page");
    await page.goto("/sectors");
    await expect(nav.getByRole("button", { name: "Mehr", exact: true })).toHaveAttribute("data-current", "true");
    await nav.getByRole("button", { name: "Mehr", exact: true }).click();
    await expect(page.getByRole("navigation", { name: "Weitere Navigation" }).getByRole("link", { name: "Sektoren", exact: true })).toHaveAttribute("aria-current", "page");
  });
}
