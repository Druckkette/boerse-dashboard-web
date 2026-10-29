import { test, expect } from "@playwright/test";
import { defaultNotificationPreferences } from "../../src/features/settings/notification-preferences";

test.use({ baseURL: "http://127.0.0.1:18300", httpCredentials: { username: "owner", password: "test-only-private-password" } });

function settingsFixture() {
  return {
    atr_threshold: 1.5, risk_per_position_pct: 1, target_risk_contribution: 0.2,
    max_depot_loss_lower_pct: 4, max_depot_loss_upper_pct: 8,
    position_monitor_enabled: true, position_monitor_interval_minutes: 1,
    position_monitor_threshold_atr: 1.5, position_monitor_atr_period: 14,
    position_monitor_lookback_days: 420, position_monitor_cooldown_hours: 18,
    position_monitor_reference: "previous_close", position_monitor_ma_alerts_enabled: true,
    position_monitor_assessment_alerts_enabled: true, position_monitor_assessment_interval_minutes: 15,
    pushover_enabled: true, pushover_configured: true, rs_rating_source: "computed",
    data_jobs_enabled: true, market_ampel_logic: "current", sell_rule_setup: {},
    notification_preferences: defaultNotificationPreferences(),
    assessment_score_weights: {
      overall: { technical: 30, fundamental: 30, chart: 30, moving_average: 10 },
      technical: { k4_rs_leadership: 30, k13_rs_dynamics: 20, rs_rating: 20, high_position: 10, up_down_volume: 10, cmf: 10 },
      fundamental: { fundamental_core: 80, k9_eps_sales_alignment: 20 },
      chart: { price_action_core: 60, k35_down_week_quality: 20, k38_hh_hl_good_close: 20 },
      moving_average: { price_above_200_sma: 20, price_above_50_sma: 15, price_above_21_ema: 10, price_above_10_sma: 5, ma_order: 15, persistence: 15, slope: 20 },
    },
  };
}

for (const width of [390, 1440]) test(`notification preferences preserve drafts, save changes and explicitly rearm at ${width}px`, async ({ page }) => {
  await page.setViewportSize({ width, height: 1000 });
  let saved = settingsFixture();
  let rejectSave = true;
  let rearmCount = 1;
  const writes: Array<Record<string, unknown>> = [];
  const rearmed: string[] = [];
  const unexpectedWrites: string[] = [];
  page.on("request", request => {
    if (request.method() !== "GET" && !/\/settings$|\/notifications\/(stops|atr)\/MRNA\/rearm$/.test(new URL(request.url()).pathname)) unexpectedWrites.push(request.url());
  });
  await page.route("**/api/v1/settings", route => {
    if (route.request().method() === "PATCH") {
      const body = route.request().postDataJSON(); writes.push(body);
      if (rejectSave) return route.fulfill({ status: 503, json: { detail: "Testfehler beim Speichern" } });
      saved = { ...saved, ...body };
    }
    return route.fulfill({ json: saved });
  });
  await page.route("**/api/v1/readiness", route => route.fulfill({ json: { status: "ready", checks: [] } }));
  await page.route("**/api/v1/settings/data-diagnostics", route => route.fulfill({ status: 503, json: { detail: "Isolierter Test" } }));
  await page.route("**/api/v1/insights/notifications", route => route.fulfill({ json: { entries: Array.from({ length: 120 }, (_, i) => ({
    timestamp: "2026-10-28T21:00:00Z", ticker: "MRNA", status: i % 2 ? "sent" : "suppressed", kind: "stop", alert_id: `entry-${i}`,
    title: `Stoppwarnung ${i}`, message: `Nachricht ${i}`, detail: i % 2 ? "Pushover bestätigt." : "Heute bereits gemeldet.", reference_label: "",
  })) } }));
  await page.route("**/api/v1/insights/notifications/*/MRNA/rearm", route => {
    expect(route.request().method()).toBe("POST"); rearmed.push(new URL(route.request().url()).pathname);
    return route.fulfill({ json: { ok: true, ticker: "MRNA", count: rearmCount } });
  });
  await page.goto("/settings#notifications");
  await expect(page.getByRole("heading", { name: "Welche Nachrichten möchtest du erhalten?" })).toBeVisible();
  const save = page.getByRole("button", { name: "Änderungen speichern", exact: true });
  await expect(save).toHaveCount(0);
  await page.getByLabel("10-SMA · Bruch", { exact: true }).selectOption("off");
  await page.getByText("Schwellen und Bestätigung für 21-EMA", { exact: true }).click();
  await page.getByLabel("21-EMA · Mindestabstand (ATR)", { exact: true }).fill("0.4");
  await expect(save).toBeEnabled();
  expect(writes).toEqual([]);
  await save.click();
  await expect(page.getByRole("alert").filter({ hasText: "Testfehler beim Speichern" })).toBeVisible();
  await expect(page.getByLabel("10-SMA · Bruch", { exact: true })).toHaveValue("off");
  await expect(page.getByLabel("21-EMA · Mindestabstand (ATR)", { exact: true })).toHaveValue("0.4");
  expect(writes).toHaveLength(1);
  expect(Object.keys(writes[0])).toEqual(["notification_preferences"]);
  await page.getByRole("button", { name: "Verwerfen", exact: true }).click();
  await expect(page.getByLabel("10-SMA · Bruch", { exact: true })).toHaveValue("digest");
  await expect(save).toHaveCount(0);
  await page.getByLabel("10-SMA · Bruch", { exact: true }).selectOption("off");
  await page.getByLabel("Stopp · Erneut warnen", { exact: true }).selectOption("manual");
  await page.getByLabel("ATR · Erneut warnen", { exact: true }).selectOption("manual");
  await page.getByText("Nachrichten bündeln", { exact: true }).click();
  await page.getByLabel("Sofortmeldungen je Aktie und Tag", { exact: true }).fill("2");
  const summary = page.locator("summary").filter({ hasText: /^Tagesübersicht$/ });
  await summary.click();
  await page.getByLabel("Tagesübersicht um", { exact: true }).fill("23:00");
  rejectSave = false;
  await save.click();
  await expect(page.getByText("Änderungen gespeichert.", { exact: true })).toBeVisible();
  expect(saved.notification_preferences.ma.sma10.break_mode).toBe("off");
  expect(saved.notification_preferences.ma.ema21.min_distance).toBe(0.2);
  expect(saved.notification_preferences.ma.sma50.break_mode).toBe("immediate");
  expect(saved.notification_preferences.grouping.max_immediate_per_ticker_day).toBe(2);
  expect(saved.notification_preferences.summary.time).toBe("23:00");
  expect(saved.notification_preferences.stop.repeat).toBe("manual");
  expect(saved.notification_preferences.atr.repeat).toBe("manual");
  await page.reload();
  await expect(page.getByLabel("10-SMA · Bruch", { exact: true })).toHaveValue("off");
  const log = page.getByRole("region", { name: "Benachrichtigungsprotokoll" });
  await expect(log.getByRole("listitem")).toHaveCount(10);
  await expect(log.getByText("Heute bereits gemeldet.", { exact: true }).first()).toBeVisible();
  await log.getByLabel("Protokoll filtern", { exact: true }).selectOption("sent");
  await expect(log.getByText("Heute bereits gemeldet.", { exact: true })).toHaveCount(0);
  await log.getByRole("button", { name: "Weitere Einträge anzeigen", exact: true }).click();
  await expect(log.getByRole("listitem")).toHaveCount(30);
  await log.getByLabel("Protokoll filtern", { exact: true }).selectOption("all");
  for (let i = 0; i < 5; i++) await log.getByRole("button", { name: "Weitere Einträge anzeigen", exact: true }).click();
  await expect(log.getByRole("listitem")).toHaveCount(100);
  await expect(log.getByRole("button", { name: "Weitere Einträge anzeigen", exact: true })).toHaveCount(0);
  await log.getByText("Stopp- oder ATR-Warnung manuell erneut scharfstellen", { exact: true }).click();
  await log.getByLabel("Ticker für erneute Warnung", { exact: true }).fill("mrna");
  expect(rearmed).toEqual([]);
  await log.getByRole("button", { name: "Stoppwarnung erneut scharfstellen", exact: true }).click();
  await expect(log.getByText("Warnung für MRNA erneut scharfgestellt.", { exact: true })).toBeVisible();
  await log.getByLabel("Warnung erneut scharfstellen", { exact: true }).selectOption("atr");
  await log.getByRole("button", { name: "ATR-Warnung erneut scharfstellen", exact: true }).click();
  await expect.poll(() => rearmed.length).toBe(2);
  expect(rearmed).toEqual(["/api/v1/insights/notifications/stops/MRNA/rearm", "/api/v1/insights/notifications/atr/MRNA/rearm"]);
  rearmCount = 0;
  await log.getByLabel("Warnung erneut scharfstellen", { exact: true }).selectOption("stop");
  await log.getByRole("button", { name: "Stoppwarnung erneut scharfstellen", exact: true }).click();
  await expect(log.getByText("Kein gespeicherter Stoppalarm für MRNA vorhanden.", { exact: true })).toBeVisible();
  expect(unexpectedWrites).toEqual([]);
  expect(writes).toHaveLength(2);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.getByRole("region", { name: "Benachrichtigungen einstellen" }).screenshot({ path: `/tmp/notification-settings-${width}.png` });
});
