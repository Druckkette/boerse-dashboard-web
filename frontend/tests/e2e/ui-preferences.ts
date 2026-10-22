import type { Page } from "@playwright/test";
export async function showDisplaySettings(page: Page) {
  if (
    await page
      .getByRole("button", { name: /Zur (klassischen|neuen) Ansicht wechseln/ })
      .filter({ visible: true })
      .count()
  )
    return;
  await page
    .locator('main > header summary[aria-label="Darstellung ändern"]')
    .click();
}
