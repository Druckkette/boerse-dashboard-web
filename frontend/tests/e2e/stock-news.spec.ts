import { test, expect } from "@playwright/test";

test.use({ baseURL: "http://127.0.0.1:18300", httpCredentials: { username: "owner", password: "test-only-private-password" } });

test.beforeEach(async ({ page }) => {
  // News tests do not need the unrelated industry-group database dependency.
  await page.route("**/api/v1/industry-groups/stock-context/*", route => route.fulfill({ status: 503, json: { detail: "Isolierte Nachrichtenprüfung" } }));
});

function reply(ticker: string) {
  const now = new Date();
  return { ticker, status: "ok", cached: false, message: null, updated_at: now.toISOString(), articles: [0, 1, 2].map(index => ({
    uuid: `${ticker}-${index}`, title: `${ticker}: Unternehmensnachricht ${index + 1}`,
    description: index === 1 ? null : `Originalbeschreibung zur Testmeldung für ${ticker}.`,
    url: `https://example.org/news/${ticker}/${index}`, source: "example.org",
    published_at: new Date(now.getTime() - (index + 1) * 3600_000).toISOString(),
    entities: [{ symbol: ticker, name: ticker, exchange: "NASDAQ", match_score: 25, sentiment_score: 0 }],
    match_score: 25, sentiment_score: 0,
  })) };
}

for (const width of [390, 1440]) {
  test(`stock news renders three source articles and safe original links at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    const requests: string[] = [];
    page.on("request", request => requests.push(request.url()));
    await page.route("**/api/v1/stocks/NVDA/news", route => route.fulfill({ json: reply("NVDA") }));
    await page.goto("/stocks/NVDA");
    const panel = page.getByRole("region", { name: "Aktuelle Nachrichten zu NVDA" });
    await expect(panel.getByRole("heading", { name: "Aktuelle Nachrichten", exact: true })).toBeVisible();
    await expect(panel.getByRole("article")).toHaveCount(3);
    await expect(panel).toContainText("Zuletzt aktualisiert:");
    await expect(panel).toContainText("vor 1 Stunde");
    for (const link of await panel.getByRole("link").all()) {
      await expect(link).toHaveAttribute("target", "_blank");
      await expect(link).toHaveAttribute("rel", "noopener noreferrer");
      await expect(link).toHaveAttribute("href", /^https:\/\/example.org\/news\/NVDA\//);
    }
    expect(requests.some(url => url.includes("api.marketaux.com") || url.includes("api_token") || url.includes("MARKETAUX_API_KEY"))).toBe(false);
    expect(await panel.evaluate(node => node.scrollWidth <= node.clientWidth + 1)).toBe(true);
  });
}

test("Beta displays company news when opening a stock without exposing private settings", async ({ browser }) => {
  const context = await browser.newContext({ httpCredentials: { username: "beta", password: "test-only-beta-password" } });
  const page = await context.newPage();
  await page.route("**/api/v1/stocks/NVDA/news", route => route.fulfill({ json: reply("NVDA") }));
  await page.route("**/api/v1/industry-groups/stock-context/*", route => route.fulfill({ status: 503, json: { detail: "Isolierte Nachrichtenprüfung" } }));
  const response = await page.goto("http://127.0.0.1:18301/stocks/NVDA");
  expect(response?.status()).toBe(200);
  const panel = page.getByRole("region", { name: "Aktuelle Nachrichten zu NVDA" });
  await expect(panel).toBeVisible();
  await expect(panel.getByRole("article")).toHaveCount(3);
  await expect(panel.getByRole("link").first()).toHaveAttribute("target", "_blank");
  await expect(page.getByLabel("Marketaux API-Schlüssel", { exact: true })).toHaveCount(0);
  await context.close();
});

test("stock change never displays the prior company's articles while the next response is loading", async ({ page }) => {
  const seen: string[] = [];
  let releaseApple!: () => void;
  const appleResponse = new Promise<void>(resolve => { releaseApple = resolve; });
  await page.route("**/api/v1/stocks/*/news", async route => {
    const ticker = new URL(route.request().url()).pathname.split("/").at(-2)!;
    seen.push(ticker);
    if (ticker === "AAPL") await appleResponse;
    await route.fulfill({ json: reply(ticker) });
  });
  await page.goto("/stocks/NVDA");
  await expect(page.getByRole("link", { name: /NVDA: Unternehmensnachricht 1/ })).toBeVisible();
  const search = page.getByRole("combobox", { name: "Aktie global suchen", exact: true });
  await search.fill("AAPL");
  await search.press("Enter");
  await expect(page).toHaveURL(/\/stocks\/AAPL$/);
  const panel = page.getByRole("region", { name: "Aktuelle Nachrichten zu AAPL" });
  await expect(panel).toHaveAttribute("aria-busy", "true");
  await expect(page.getByRole("link", { name: /NVDA: Unternehmensnachricht/ })).toHaveCount(0);
  releaseApple();
  await expect(panel.getByRole("article")).toHaveCount(3);
  await expect(panel).not.toContainText("NVDA:");
  await expect(panel).toContainText("AAPL: Unternehmensnachricht 1");
  expect(seen).toEqual(["NVDA", "AAPL"]);
});

test("empty, stale and unavailable news preserve the stock view and clearly identify their state", async ({ page }) => {
  await page.route("**/api/v1/stocks/NVDA/news", route => route.fulfill({ json: { ...reply("NVDA"), status: "empty", articles: [] } }));
  await page.goto("/stocks/NVDA");
  let panel = page.getByRole("region", { name: "Aktuelle Nachrichten zu NVDA" });
  await expect(panel).toContainText("Aktuell keine Unternehmensnachrichten verfügbar.");
  await page.unroute("**/api/v1/stocks/NVDA/news");
  await page.route("**/api/v1/stocks/NVDA/news", route => route.fulfill({ json: { ...reply("NVDA"), status: "stale", message: "Letzter verfügbarer Nachrichtenstand.", cached: true } }));
  await page.reload();
  panel = page.getByRole("region", { name: "Aktuelle Nachrichten zu NVDA" });
  await expect(panel.getByRole("article")).toHaveCount(3);
  await expect(panel.getByRole("status")).toHaveText("Letzter verfügbarer Nachrichtenstand.");
  await page.unroute("**/api/v1/stocks/NVDA/news");
  await page.route("**/api/v1/stocks/NVDA/news", route => route.fulfill({ status: 503, json: { detail: "Unavailable" } }));
  await page.reload();
  await expect(page.getByRole("heading", { name: "NVDA", exact: true, level: 1 })).toBeVisible();
  await expect(page.getByRole("region", { name: "Aktuelle Nachrichten zu NVDA" })).toContainText("Nachrichten sind derzeit nicht verfügbar.");
});

test("news does not fetch again when switching analysis tabs and does not render unsafe links", async ({ page }) => {
  let calls = 0;
  await page.route("**/api/v1/stocks/NVDA/news", route => {
    calls++;
    const data = reply("NVDA");
    data.articles[1].url = "javascript:alert(1)";
    return route.fulfill({ json: data });
  });
  await page.goto("/stocks/NVDA");
  const panel = page.getByRole("region", { name: "Aktuelle Nachrichten zu NVDA" });
  await expect(panel.getByRole("article")).toHaveCount(2);
  await page.getByRole("button", { name: "Technik", exact: true }).click();
  await expect(panel).toBeVisible();
  await expect(panel.getByRole("link")).toHaveCount(2);
  expect(calls).toBe(1);
});

test("a failed recheck of cached empty news shows one unavailable state", async ({ page }) => {
  let nvdaCalls = 0;
  await page.route("**/api/v1/stocks/*/news", route => {
    const ticker = new URL(route.request().url()).pathname.split("/").at(-2)!;
    if (ticker !== "NVDA") return route.fulfill({ json: reply(ticker) });
    nvdaCalls++;
    return nvdaCalls === 1
      ? route.fulfill({ json: { ...reply("NVDA"), status: "empty", articles: [] } })
      : route.fulfill({ status: 503, json: { detail: "Unavailable" } });
  });
  await page.goto("/stocks/NVDA");
  await expect(page.getByRole("region", { name: "Aktuelle Nachrichten zu NVDA" })).toContainText("Aktuell keine Unternehmensnachrichten verfügbar.");
  const search = page.getByRole("combobox", { name: "Aktie global suchen", exact: true });
  await search.fill("AAPL");
  await search.press("Enter");
  await expect(page.getByRole("region", { name: "Aktuelle Nachrichten zu AAPL" }).getByRole("article")).toHaveCount(3);
  await search.fill("NVDA");
  await search.press("Enter");
  const panel = page.getByRole("region", { name: "Aktuelle Nachrichten zu NVDA" });
  await expect(panel.getByRole("status")).toHaveCount(1);
  await expect(panel.getByRole("status")).toContainText("Nachrichten sind derzeit nicht verfügbar.");
  await expect(panel).not.toContainText("Aktuell keine Unternehmensnachrichten verfügbar.");
  expect(nvdaCalls).toBe(2);
});
