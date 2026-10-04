export type CriterionResult = {
  label: string;
  outcome: "passed" | "failed" | "missing" | "neutral";
  detail: string;
  weight?: number;
  children?: CriterionResult[];
};
type Component = { score?: number | null; status?: string; base_weight?: number; raw?: Record<string, unknown> };
type Check = { category: string; label: string; passed: boolean; detail: string };
type Signal = { key?: string; label: string; category: string; detail: string; score_relevant?: boolean };
const object = (value: unknown): Record<string, unknown> => value && typeof value === "object" ? value as Record<string, unknown> : {};
const number = (value: unknown): number | undefined => typeof value === "number" && Number.isFinite(value) ? value : undefined;
const formatted = (value: unknown, suffix = ""): string => number(value) !== undefined ? `${(value as number).toFixed(1)}${suffix}` : "–";
function scored(label: string, component: Component, detail = ""): CriterionResult {
  const score = ["missing", "insufficient_history", "not_applicable"].includes(component.status ?? "") ? undefined : number(component.score);
  return { label, outcome: component.status === "neutral" ? "neutral" : score === undefined ? "missing" : score >= 70 ? "passed" : "failed", detail: `${score === undefined ? "Keine bewertbaren Daten" : `${score.toFixed(1)}/100 · erfüllt ab 70/100`}${detail ? ` · ${detail}` : ""}${component.status === "partial" ? " · eingeschränkte Historie" : ""}`, weight: component.base_weight };
}
function binary(label: string, value: unknown, detail = "", weight?: number): CriterionResult {
  return { label, outcome: typeof value !== "boolean" ? "missing" : value ? "passed" : "failed", detail, weight };
}
export function criterionResults(key: string, component: Component, checks: Check[] = [], signals: Signal[] = []): CriterionResult[] {
  const raw = component.raw ?? {};
  if (key === "k4_rs_leadership" || key === "k13_rs_dynamics") {
    const labels: Record<string, string> = { above_21_ema: "RS-Linie über 21-Tage-EMA", above_50_sma: "RS-Linie über 50-Tage-SMA", persistence: "Beständigkeit über 63 Handelstage", rs_52w_high: "Nähe zum 52-Wochen-Hoch der RS-Linie", white_space: "Stabiler Abstand zu den Durchschnitten", three_vs_six: "RS-Rating: 3 Monate gegenüber 6 Monaten", six_vs_twelve: "RS-Rating: 6 Monate gegenüber 12 Monaten", sequence: "Reihenfolge der 3-/6-/12-Monats-Ratings", acceleration: "Beschleunigung" };
    const parts = Object.entries(object(raw.components));
    if (!parts.length) return [scored("Unterkriterien", component)];
    return parts.map(([part, value]) => {
      const child = object(value) as Component;
      const data = child.raw ?? {};
      const row = scored(labels[part] ?? part, child);
      if (part === "above_21_ema" || part === "above_50_sma") return binary(labels[part], data[part], `RS-Linie ${formatted(data.rs_line)} · Durchschnitt ${formatted(data.rs_ema21 ?? data.rs_sma50)}`, child.base_weight);
      if (part === "persistence") row.children = [
        scored("Handelstage über 21-EMA", { score: number(data.persistence_21_pct), base_weight: .6 }, `${data.available_days_21 ?? 0}/63 Tage · ${formatted(data.persistence_21_pct, "%")} oberhalb`),
        scored("Handelstage über 50-SMA", { score: number(data.persistence_50_pct), base_weight: .4 }, `${data.available_days_50 ?? 0}/63 Tage · ${formatted(data.persistence_50_pct, "%")} oberhalb`),
      ];
      if (part === "rs_52w_high") row.detail += ` · Abstand ${formatted(data.distance_to_rs_52w_high_pct, "%")}`;
      if (part === "white_space") row.children = [
        scored("Aktueller Abstand", { score: number(data.current_separation), base_weight: .35 }, `21-EMA ${formatted(data.distance_rs_to_21_pct, "%")} · 50-SMA ${formatted(data.distance_rs_to_50_pct, "%")}`),
        scored("Stabilität über 20 Handelstage", { score: number(data.stability_score), base_weight: .65 }, `${data.available_days ?? 0}/20 Tage · Abstand mindestens 0,25 % zum 21-EMA und 0,50 % zum 50-SMA`),
      ];
      if (part === "white_space" && row.children) row.children[0].children = [
        scored("Abstand zum 21-EMA", { score: number(data.distance_rs_to_21_pct) === undefined ? undefined : Math.max(0, Math.min(100, (data.distance_rs_to_21_pct as number) / 1.5 * 100)), base_weight: .6 }, `${formatted(data.distance_rs_to_21_pct, "%")} · volle Punkte ab 1,5 %`),
        scored("Abstand zum 50-SMA", { score: number(data.distance_rs_to_50_pct) === undefined ? undefined : Math.max(0, Math.min(100, (data.distance_rs_to_50_pct as number) / 3 * 100)), base_weight: .4 }, `${formatted(data.distance_rs_to_50_pct, "%")} · volle Punkte ab 3 %`),
      ];
      if (part === "three_vs_six" || part === "six_vs_twelve") row.detail += ` · Unterschied ${formatted(data.delta, " Punkte")}`;
      if (part === "sequence") row.detail += ` · 3M ${formatted(data.rs_3m)} / 6M ${formatted(data.rs_6m)} / 12M ${formatted(data.rs_12m)}`;
      if (part === "acceleration") {
        row.detail += ` · Stärke ${formatted(data.acceleration_strength)}`;
        const components = object(raw.components);
        row.children = [["three_vs_six", "3M gegenüber 6M", .6], ["six_vs_twelve", "6M gegenüber 12M", .4]].map(([name, label, weight]) => {
          const source = object(components[String(name)]) as Component;
          return scored(String(label), { ...source, base_weight: Number(weight) }, `Unterschied ${formatted(source.raw?.delta, " Punkte")}`);
        });
      }
      return row;
    });
  }
  if (key === "fundamental_core") return checks.filter(c => c.category === "fundamental" && !["Fundamental-Datenquelle", "Institutionelle Unterstützung"].includes(c.label)).map(c => binary(c.label, c.detail.startsWith("Nicht verfügbar") || c.detail.toLowerCase().includes("nicht anwendbar") ? undefined : c.passed, c.detail));
  if (key === "price_action_core") {
    const keys = Array.isArray(raw.scored_signal_keys) ? raw.scored_signal_keys : [];
    const rows: CriterionResult[] = signals.filter(s => s.score_relevant && keys.includes(s.key || s.label)).map(s => ({ label: s.label, outcome: s.category === "positive" ? "passed" : s.category === "negative" ? "failed" : "neutral", detail: s.detail }));
    return rows.length ? rows : [{ label: "Scorewirksame Chartsignale", outcome: "neutral", detail: "Keine aktiven scorewirksamen Signale vorhanden." }];
  }
  if (key === "high_position") return ["Entfernung zum All-Time-High", "Entfernung zum 52-Wochen-Hoch"].map((label, i) => {
    const check = checks.find(c => c.label === label);
    return binary(label, check && check.detail !== "Nicht verfügbar" ? check.passed : undefined, check?.detail ?? "Nicht verfügbar", i === 0 ? 2 / 3 : 1 / 3);
  });
  if (key === "k9_eps_sales_alignment" || key === "k35_down_week_quality") {
    const rows = raw[key === "k9_eps_sales_alignment" ? "matched_quarters" : "down_weeks"];
    if (!Array.isArray(rows) || !rows.length) return [scored("Auswertbare Zeiträume", component)];
    return rows.map((value, i) => {
      const data = object(value);
      return scored(String(data.period), { score: number(data.score), status: key === "k9_eps_sales_alignment" && component.score == null ? "missing" : String(data.status ?? "available"), base_weight: [ .5, .3, .2 ][i] }, key === "k9_eps_sales_alignment" ? `EPS ${formatted(data.eps_growth_yoy_pct, "%")} · Umsatz ${formatted(data.revenue_growth_yoy_pct, "%")}${data.research_trigger ? " · Recherchehinweis" : ""}` : `Wochenrendite ${formatted(data.weekly_return_pct, "%")} · Schlusskursposition ${formatted(data.closing_range_pct, "%")}`);
    });
  }
  if (key === "k38_hh_hl_good_close") return [
    binary("Höheres Wochenhoch", raw.higher_high), binary("Höheres Wochentief", raw.higher_low),
    binary("Wochenrendite mindestens 2 %", number(raw.weekly_return_pct) === undefined ? undefined : (raw.weekly_return_pct as number) >= 2, formatted(raw.weekly_return_pct, "%")),
    binary("Schlusskurs im oberen Viertel", number(raw.closing_range_pct) === undefined ? undefined : (raw.closing_range_pct as number) >= 75, formatted(raw.closing_range_pct, "% der Wochenkursspanne")),
  ];
  if (key === "ma_order") return [binary("21-EMA über 50-SMA", number(raw.ema21) !== undefined && number(raw.sma50) !== undefined ? (raw.ema21 as number) > (raw.sma50 as number) : undefined), binary("50-SMA über 200-SMA", number(raw.sma50) !== undefined && number(raw.sma200) !== undefined ? (raw.sma50 as number) > (raw.sma200 as number) : undefined)];
  if (key === "persistence") return ["ema21", "sma50"].map((part, i) => { const data = object(raw[part]); return scored(i === 0 ? "Beständigkeit über 21-EMA" : "Beständigkeit über 50-SMA", { score: number(data.score), base_weight: i === 0 ? .4 : .6 }, `${data.above_streak_days ?? 0} Tage darüber · ${data.below_streak_days ?? 0} Tage darunter`); });
  if (key === "slope") return ["ema21", "sma50"].map(part => binary(part === "ema21" ? "21-EMA steigt" : "50-SMA steigt", raw[`${part}_direction`] == null ? undefined : raw[`${part}_direction`] === "up", `${formatted(raw[`${part}_change_pct`], "%")} über 10 Handelstage`));
  if (key.startsWith("price_above_")) return [binary("Kurs über dem Durchschnitt", raw.above, `Kurs ${formatted(raw.price)} · Durchschnitt ${formatted(raw.average)}`)];
  if (key === "up_down_volume") return [binary("Volumenverhältnis mindestens 1", number(raw.ratio) === undefined ? undefined : (raw.ratio as number) >= 1, `Verhältnis ${formatted(raw.ratio)}`)];
  return [scored(key === "rs_rating" ? "RS-Rating" : key === "cmf" ? "Chaikin Money Flow" : "Kriterium", component, key === "rs_rating" ? `Rating ${formatted(raw.rating)}` : key === "cmf" ? `CMF ${formatted(raw.cmf_20)} · Stufe ${raw.rating ?? "–"}` : "")];
}
