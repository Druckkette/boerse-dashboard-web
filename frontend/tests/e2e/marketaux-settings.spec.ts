import { test, expect } from "@playwright/test";

test.use({ baseURL: "http://127.0.0.1:18300", httpCredentials: { username: "owner", password: "test-only-private-password" } });

const DUMMY_KEY = "test-only-marketaux-key-do-not-use";
const KEY = "MARKETAUX_API_KEY";
const MASK = "••••••••";
const appSettings = {
  atr_threshold: 1.5, risk_per_position_pct: 1, target_risk_contribution: 0.2,
  max_depot_loss_lower_pct: 4, max_depot_loss_upper_pct: 8,
  position_monitor_enabled: false, position_monitor_interval_minutes: 1,
  position_monitor_threshold_atr: 1.5, position_monitor_atr_period: 14,
  position_monitor_lookback_days: 420, position_monitor_cooldown_hours: 18,
  position_monitor_reference: "previous_close", position_monitor_ma_alerts_enabled: true,
  position_monitor_assessment_alerts_enabled: true, position_monitor_assessment_interval_minutes: 15,
  pushover_enabled: false, pushover_configured: false, rs_rating_source: "computed",
  data_jobs_enabled: true, market_ampel_logic: "current", sell_rule_setup: {},
  assessment_score_weights: {
    overall: { technical: 30, fundamental: 30, chart: 30, moving_average: 10 },
    technical: { k4_rs_leadership: 30, k13_rs_dynamics: 20, rs_rating: 20, high_position: 10, up_down_volume: 10, cmf: 10 },
    fundamental: { fundamental_core: 80, k9_eps_sales_alignment: 20 },
    chart: { price_action_core: 60, k35_down_week_quality: 20, k38_hh_hl_good_close: 20 },
    moving_average: { price_above_200_sma: 20, price_above_50_sma: 15, price_above_21_ema: 10, price_above_10_sma: 5, ma_order: 15, persistence: 15, slope: 20 },
  },
};

function runtimeConfig(configured: boolean) {
  return {
    items: [{ key: KEY, label: "Marketaux API-Schlüssel", category: "external_api", description: "Nachrichtenquelle", configured,
      source: configured ? "database" : "missing", secret: true, editable: true, restart_required: false,
      runtime_applied: configured, placeholder: "", value_preview: configured ? MASK : "" }],
    editable_keys: [KEY], bootstrap_keys: [], note: "Testkonfiguration ohne echte Zugangsdaten",
  };
}

for (const width of [390, 1440]) {
  test(`Setup exposes the Marketaux secret, saves it masked and applies it without restart at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 1000 });
    await page.route("**/api/v1/setup/status", route => route.fulfill({ json: { status: "ready", steps: [], next_step_key: null, summary: "Isolierte Setup-Prüfung" } }));
    await page.route("**/api/v1/settings/database-target", route => route.fulfill({ status: 503, json: { detail: "Isolierte Setup-Prüfung" } }));
    const writes: unknown[] = [];
    let configured = false;
    await page.route("**/api/v1/settings/runtime-config", route => {
      if (route.request().method() === "PATCH") {
        writes.push(route.request().postDataJSON());
        configured = true;
      } else expect(route.request().method()).toBe("GET");
      const response = runtimeConfig(configured);
      // Match the real backend metadata consumed by the existing Setup form.
      response.items[0].label = "Marketaux API Key";
      response.items[0].placeholder = "Marketaux API Key";
      response.items[0].value_preview = configured ? "********" : "";
      return route.fulfill({ json: response });
    });
    const requests: string[] = [];
    page.on("request", request => requests.push(request.url()));
    await page.goto("/setup");
    await expect(page.getByRole("heading", { name: "API-Zugänge im Setup pflegen", exact: true })).toBeVisible();
    const input = page.getByPlaceholder("Marketaux API Key", { exact: true });
    await expect(input).toHaveCount(1);
    await expect(input).toHaveAttribute("type", "password");
    await input.fill(DUMMY_KEY);
    const save = page.getByRole("button", { name: "Speichern", exact: true });
    await save.click();
    await expect(input).toHaveValue("");
    await expect(save).toBeDisabled();
    await expect(page.getByText("Aktuell: ********", { exact: true })).toBeVisible();
    await expect(page.locator("body")).not.toContainText(DUMMY_KEY);
    expect(writes).toEqual([{ values: { [KEY]: DUMMY_KEY }, clear_keys: [] }]);
    expect(requests.some(url => url.includes(DUMMY_KEY) || url.includes("api.marketaux.com") || url.includes("api_token") || url.includes("restart"))).toBe(false);
    await page.reload();
    await expect(input).toHaveValue("");
    await expect(page.getByText("Aktuell: ********", { exact: true })).toBeVisible();
    await expect(page.locator("body")).not.toContainText(DUMMY_KEY);
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
  });
}

for (const width of [390, 1440])
  test(`private Marketaux settings mask, save and clear the secret draft at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 1000 });
    await page.route("**/api/v1/settings", route => route.fulfill({ json: appSettings }));
    await page.route("**/api/v1/readiness", route => route.fulfill({ json: { status: "ready", checks: [] } }));
    await page.route("**/api/v1/settings/data-diagnostics", route => route.fulfill({ status: 503, json: { detail: "Isolierte Einstellungen-Prüfung" } }));
    await page.route("**/api/v1/industry-groups/stock-context/*", route => route.fulfill({ status: 503, json: { detail: "Isolierte Nachrichtenprüfung" } }));
    const transmissions: { method: string; path: string }[] = [];
    const urls: string[] = [];
    page.on("request", request => {
      urls.push(request.url());
      if (request.postData()?.includes(DUMMY_KEY)) transmissions.push({ method: request.method(), path: new URL(request.url()).pathname });
    });
    let configured = false;
    let writes = 0;
    await page.route("**/api/v1/settings/runtime-config", route => {
      if (route.request().method() === "PATCH") {
        writes++;
        expect(route.request().postDataJSON()).toEqual({ values: { [KEY]: DUMMY_KEY }, clear_keys: [] });
        if (writes === 1) return route.fulfill({ status: 503, json: { detail: `Synthetic failure ${DUMMY_KEY}` } });
        configured = true;
      } else expect(route.request().method()).toBe("GET");
      return route.fulfill({ json: runtimeConfig(configured) });
    });
    await page.goto("/settings");
    if (width < 1024) await page.getByRole("combobox", { name: "Einstellungsbereich", exact: true }).selectOption("system");
    else await page.getByRole("button", { name: "Daten & System", exact: true }).click();
    const panel = page.getByRole("region", { name: "Marketaux Nachrichten-Zugang" });
    const input = panel.getByLabel("Marketaux API-Schlüssel", { exact: true });
    const save = panel.getByRole("button", { name: "Nachrichten-Schlüssel speichern", exact: true });
    await expect(input).toHaveAttribute("type", "password");
    await expect(input).toHaveValue("");
    await expect(panel).toContainText("Noch kein Schlüssel hinterlegt.");
    await input.fill(DUMMY_KEY);
    await save.click();
    await expect(panel.getByRole("alert")).toHaveText("Der Nachrichten-Zugang konnte nicht gespeichert werden. Bitte erneut versuchen.");
    await expect(panel).not.toContainText(DUMMY_KEY);
    await expect(input).toHaveValue(DUMMY_KEY);
    await save.click();
    await expect(panel.getByRole("status")).toHaveText("Nachrichten-Zugang gespeichert.");
    await expect(input).toHaveValue("");
    await expect(panel).toContainText("Ein Schlüssel ist hinterlegt.");
    await expect(panel).not.toContainText(DUMMY_KEY);
    const read = page.waitForResponse(response => response.url().endsWith("/settings/runtime-config") && response.request().method() === "GET");
    await page.reload();
    if (width < 1024) await page.getByRole("combobox", { name: "Einstellungsbereich", exact: true }).selectOption("system");
    else await page.getByRole("button", { name: "Daten & System", exact: true }).click();
    const response = await read;
    const config = await response.json();
    expect(config.items[0].value_preview).toBe(MASK);
    expect(JSON.stringify(config)).not.toContain(DUMMY_KEY);
    await expect(input).toHaveValue("");
    await expect(panel).toContainText("Ein Schlüssel ist hinterlegt.");
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
    let newsReads = 0;
    await page.route("**/api/v1/stocks/NVDA/news", route => {
      newsReads++;
      expect(route.request().method()).toBe("GET");
      expect(JSON.stringify(route.request().headers())).not.toContain(DUMMY_KEY);
      expect(route.request().postData()).toBeNull();
      return route.fulfill({ json: { ticker: "NVDA", articles: [], status: "empty", updated_at: null, cached: true, message: null } });
    });
    const search = page.getByRole("combobox", { name: "Aktie global suchen", exact: true });
    await search.fill("NVDA");
    await search.press("Enter");
    await expect(page.getByRole("region", { name: "Aktuelle Nachrichten zu NVDA" })).toContainText("Aktuell keine Unternehmensnachrichten verfügbar.");
    expect(newsReads).toBe(1);
    expect(urls.some(url => url.includes(DUMMY_KEY) || url.includes("api_token") || url.includes("api.marketaux.com"))).toBe(false);
    expect(transmissions).toEqual([
      { method: "PATCH", path: "/api/v1/settings/runtime-config" },
      { method: "PATCH", path: "/api/v1/settings/runtime-config" },
    ]);
  });

test("beta cannot open Marketaux settings or access the private runtime endpoint", async ({ browser }) => {
  const context = await browser.newContext({ httpCredentials: { username: "beta", password: "test-only-beta-password" } });
  const page = await context.newPage();
  const response = await page.goto("http://127.0.0.1:18301/settings");
  expect(response?.status()).toBe(403);
  await expect(page.getByLabel("Marketaux API-Schlüssel", { exact: true })).toHaveCount(0);
  expect((await context.request.get("http://127.0.0.1:18301/api/v1/settings/runtime-config")).status()).toBe(403);
  expect((await context.request.patch("http://127.0.0.1:18301/api/v1/settings/runtime-config", { data: { values: { [KEY]: DUMMY_KEY } } })).status()).toBe(403);
  await context.close();
});
