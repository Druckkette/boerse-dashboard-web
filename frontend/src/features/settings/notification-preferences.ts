import type { NotificationMaKey, NotificationMaPreferences, NotificationPreferences, PushoverDeliveryLogItem } from "../../lib/types/api.ts";

export const notificationMaLabels: Record<NotificationMaKey, string> = {
  sma10: "10-SMA", ema21: "21-EMA", sma50: "50-SMA", sma200: "200-SMA",
};

export function defaultNotificationPreferences(): NotificationPreferences {
  const ma = (immediate = false): NotificationMaPreferences => ({
    break_mode: immediate ? "immediate" : "digest", recovery_mode: "digest", worsening_mode: "digest",
    confirmation: "intraday", confirmation_minutes: 10, distance_unit: "atr", min_distance: 0.2,
    worsening_atr: 1, max_per_day: 1, session: "regular", priority: 0,
  });
  return {
    version: 1, timezone: "Europe/Berlin",
    ma: { sma10: ma(), ema21: ma(), sma50: ma(true), sma200: ma(true) },
    stop: { mode: "immediate", repeat: "daily", repeat_minutes: 60, recovery_pct: 1, recovery_minutes: 10, priority: 1, session: "all" },
    atr: { mode: "immediate", escalation_enabled: true, escalation_atr: 3, repeat: "daily", repeat_minutes: 60, recovery_atr: 1, recovery_minutes: 10, priority: 1, session: "all" },
    assessment: { score_mode: "digest", verdict_mode: "digest", score_min_change: 10, notify_improvements: true, notify_deteriorations: true, priority: 0, session: "regular" },
    grouping: { enabled: true, window_minutes: 30, max_immediate_per_ticker_day: 3, stop_bypass: true, atr_escalation_bypass: true },
    summary: { enabled: true, time: "22:45", categories: ["ma", "score", "verdict", "stop", "atr"], include_sent: false, only_changes: true, max_tickers: 5, priority: 0 },
    quiet: { enabled: false, start: "22:00", end: "07:00", stop_bypass: true, atr_escalation_bypass: true },
    custom_session: { start: "08:00", end: "22:00" },
  };
}

export function updateNotificationMa(
  preferences: NotificationPreferences,
  key: NotificationMaKey,
  patch: Partial<NotificationMaPreferences>,
): NotificationPreferences {
  return { ...preferences, ma: { ...preferences.ma, [key]: { ...preferences.ma[key], ...patch } } };
}

export const notificationDeliveryLabels: Record<PushoverDeliveryLogItem["status"], string> = {
  sent: "Gesendet", failed: "Fehlgeschlagen", skipped: "Übersprungen", queued: "Wird gebündelt",
  digest: "Für Tagesübersicht", suppressed: "Zurückgehalten", disabled: "Ausgeschaltet",
};
