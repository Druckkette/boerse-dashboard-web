import assert from "node:assert/strict";
import test from "node:test";
import { defaultNotificationPreferences, updateNotificationMa } from "../src/features/settings/notification-preferences.ts";
import { settingsChanges } from "../src/features/settings/settings-draft.ts";

test("editing one MA keeps the other rows and saved settings intact in the save draft", () => {
  const saved = { pushover_enabled: true, notification_preferences: defaultNotificationPreferences() };
  const original = structuredClone(saved);
  const draft = { ...saved, notification_preferences: updateNotificationMa(saved.notification_preferences, "ema21", { break_mode: "immediate", min_distance: 0.4 }) };
  assert.deepEqual(saved, original);
  assert.deepEqual(draft.notification_preferences.ma.sma50, saved.notification_preferences.ma.sma50);
  assert.deepEqual(draft.notification_preferences.summary, saved.notification_preferences.summary);
  const changed = settingsChanges(saved, draft);
  assert.deepEqual(Object.keys(changed), ["notification_preferences"]);
  assert.equal(changed.notification_preferences.ma.ema21.break_mode, "immediate");
  assert.equal(changed.notification_preferences.ma.ema21.min_distance, 0.4);
});

test("recommended preferences are independent drafts, including nested rows and category lists", () => {
  const first = defaultNotificationPreferences();
  first.ma.sma10.break_mode = "off";
  first.summary.categories.splice(0);
  const second = defaultNotificationPreferences();
  assert.equal(second.ma.sma10.break_mode, "digest");
  assert.equal(first.ma.ema21.break_mode, "digest");
  assert.equal(second.ma.sma50.break_mode, "immediate");
  assert.equal(second.summary.categories.length, 5);
});
