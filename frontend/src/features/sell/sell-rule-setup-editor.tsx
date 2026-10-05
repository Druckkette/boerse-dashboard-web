import { Minus, Plus } from "lucide-react";
import type { ReactNode } from "react";

const STRATEGY_OPTIONS = [
  { value: "rs_line", label: "RS-Linie täglich · 21/50-SMA" },
  { value: "custom", label: "Benutzerdefiniert" },
  { value: "ema21_risk_averse", label: "21-EMA risikoavers" },
  { value: "ema21_offensive", label: "21-EMA offensiv" },
  { value: "peak_drawdown", label: "Peak-Rückgang" },
  { value: "buy_day_low", label: "Kauftag-Tief" },
  { value: "ma_breaks", label: "MA-Brüche" }
] as const;

const CUSTOM_FEATURE_OPTIONS = [
  { value: "offensive_profit_target", label: "Gewinnschwelle" },
  { value: "offensive_ema21_break", label: "21-EMA-Bruch" },
  { value: "offensive_peak_drop", label: "20T-Peak-Rückgang" },
  { value: "offensive_ma_extension_sma10", label: "10-SMA Überdehnung" },
  { value: "offensive_ma_extension_ema21", label: "21-EMA Überdehnung" },
  { value: "offensive_ma_extension_sma50", label: "50-SMA Überdehnung" },
  { value: "offensive_ma_extension_sma200", label: "200-SMA Überdehnung" },
  { value: "offensive_low_closes", label: "Häufung tiefer Schlusskurse" },
  { value: "offensive_sharp_drop_no_reclaim", label: "Scharfer Einbruch ohne Rückeroberung" },
  { value: "offensive_loss_days_cluster", label: "Häufung von Verlusttagen" },
  { value: "offensive_buy_price_reached", label: "Rückfall auf Kaufpreis nach Gewinnpolster" },
  { value: "offensive_biggest_gain", label: "Größter Gewinn-Tag" },
  { value: "offensive_stall_days", label: "Stautage" },
  { value: "defensive_buy_day_low", label: "Kauftag-Tief" },
  { value: "defensive_previous_day_low", label: "Vortagestief vor Kauf" },
  { value: "defensive_ma_break_10", label: "10-SMA-Bruch" },
  { value: "defensive_ma_break_21", label: "21-EMA-Bruch defensiv" },
  { value: "defensive_ma_break_50", label: "50-SMA-Bruch" },
  { value: "defensive_ma_break_200", label: "200-SMA-Bruch" },
  { value: "defensive_loss_weeks", label: "Verlustwochen" },
  { value: "defensive_worst_daily_drop", label: "größter Tageseinbruch" },
  { value: "defensive_worst_weekly_drop", label: "größter Wocheneinbruch" },
  { value: "emergency_loss_limit", label: "Nothalt" }
] as const;

type CustomStrategyStep = {
  feature_id: string;
  tranche_percent: number;
};

export function SellRuleSetupEditor({ setup, onChange }: {
  setup: Record<string, unknown>;
  onChange: (next: Record<string, unknown>) => void;
}) {
  function updateSellSetup(patch: Record<string, unknown>) {
    onChange({ ...setup, ...patch });
  }

  function setupNumber(key: string, fallback: number) {
    const raw = setup[key];
    const parsed = typeof raw === "number" ? raw : typeof raw === "string" ? Number(raw) : fallback;
    return Number.isFinite(parsed) ? parsed : fallback;
  }

  function setupString(key: string, fallback: string) {
    const raw = setup[key];
    return typeof raw === "string" && raw ? raw : fallback;
  }

  function setupBoolean(key: string, fallback: boolean) {
    const raw = setup[key];
    return typeof raw === "boolean" ? raw : fallback;
  }

  function customStrategySteps(): CustomStrategyStep[] {
    const raw = setup.custom_strategy_steps;
    if (!Array.isArray(raw)) return [
      { feature_id: "emergency_loss_limit", tranche_percent: 100 }
    ];
    return raw
      .filter((item): item is Record<string, unknown> => typeof item === "object" && item !== null)
      .map((item) => ({
        feature_id: typeof item.feature_id === "string" ? item.feature_id : "offensive_profit_target",
        tranche_percent: typeof item.tranche_percent === "number" ? item.tranche_percent : Number(item.tranche_percent ?? 25)
      }));
  }

  function updateCustomStrategyStep(index: number, patch: Partial<CustomStrategyStep>) {
    const steps = customStrategySteps().map((step, itemIndex) => itemIndex === index ? { ...step, ...patch } : step);
    updateSellSetup({ custom_strategy_steps: steps });
  }

  function addCustomStrategyStep() {
    updateSellSetup({
      custom_strategy_steps: [...customStrategySteps(), { feature_id: CUSTOM_FEATURE_OPTIONS.find((option) => !customStrategySteps().some((step) => step.feature_id === option.value))?.value ?? "offensive_profit_target", tranche_percent: 25 }]
    });
  }

  function removeCustomStrategyStep(index: number) {
    updateSellSetup({ custom_strategy_steps: customStrategySteps().filter((_, itemIndex) => itemIndex !== index) });
  }

  const selectedStrategy = setupString("strategy_key", "rs_line");
  return (
          <div className="grid gap-5 xl:grid-cols-[1fr_1fr_1fr]">
            <p className="text-sm text-[#687386] xl:col-span-3">Aktive Kriterien lösen nur dann Verkaufstranchen aus, wenn sie zur gewählten Strategie gehören. Der Nothalt gilt immer und setzt das Verkaufsziel auf 100 %. Bereits verkaufte Tranchen werden abgezogen. Im Baukasten summieren sich die ausgewählten aktiven Tranchen bis höchstens 100 %.</p>
            <label className="block text-sm xl:col-span-3">
              <span className="mb-1 block text-[#687386]">Aktive Verkaufsstrategie</span>
              <select
                className="w-full rounded border border-[#d8e1ea] bg-[#f9fbfd] px-3 py-2"
                value={selectedStrategy}
                onChange={(event) => updateSellSetup({ strategy_key: event.target.value })}
              >
                {STRATEGY_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>{option.label}</option>
                ))}
              </select>
            </label>

            <StrategySpecificSetup
              selectedStrategy={selectedStrategy}
              customSteps={customStrategySteps()}
              setupNumber={setupNumber}
              setupString={setupString}
              updateCustomStrategyStep={updateCustomStrategyStep}
              addCustomStrategyStep={addCustomStrategyStep}
              removeCustomStrategyStep={removeCustomStrategyStep}
              updateSellSetup={updateSellSetup}
            />

            <details className="xl:col-span-3 rounded border border-[#e3e8ef] p-3">
              <summary className="cursor-pointer text-sm font-semibold">Grenzwerte für Nothalt, offensive und defensive Kriterien</summary>
              <div className="mt-3 grid gap-4 xl:grid-cols-3">
            <RuleSetupGroup title="Nothalt">
              <UnitValueRow
                label="Verlusthöhe"
                unit={setupString("emergency_stop_unit", "pct")}
                value={setupNumber("emergency_stop_value", 7)}
                onUnitChange={(value) => updateSellSetup({ emergency_stop_unit: value })}
                onValueChange={(value) => updateSellSetup({ emergency_stop_value: value })}
              />
            </RuleSetupGroup>

            <RuleSetupGroup title="Offensives Verkaufen">
              <UnitValueRow
                label="Gewinnschwelle"
                unit={setupString("profit_target_unit", "pct")}
                value={setupNumber("profit_target_value", 20)}
                onUnitChange={(value) => updateSellSetup({ profit_target_unit: value })}
                onValueChange={(value) => updateSellSetup({ profit_target_value: value })}
              />
              <UnitValueRow
                label="21-EMA-Bruch"
                unit={setupString("ema21_break_unit", "pct")}
                value={setupNumber("ema21_break_value", 2)}
                onUnitChange={(value) => updateSellSetup({ ema21_break_unit: value })}
                onValueChange={(value) => updateSellSetup({ ema21_break_value: value })}
              />
              <UnitValueRow
                label="20T-Peak-Rückgang"
                unit={setupString("peak_drop_unit", "pct")}
                value={setupNumber("peak_drop_value", 8)}
                onUnitChange={(value) => updateSellSetup({ peak_drop_unit: value })}
                onValueChange={(value) => updateSellSetup({ peak_drop_value: value })}
              />
              <label className="block text-sm">Einheit der Überdehnungsabstände<select className="ml-2 rounded border px-2 py-1" value={setupString("ma_extension_unit", "pct")} onChange={(event) => updateSellSetup({ ma_extension_unit: event.target.value })}><option value="pct">%</option><option value="atr">ATR</option></select></label>
              <div className="grid gap-2 sm:grid-cols-2">
                <SetupNumber label={`10-SMA Abstand ${setupString("ma_extension_unit", "pct") === "atr" ? "ATR" : "%"}`} value={setupNumber("ma_extension_sma10_pct", 10)} onChange={(value) => updateSellSetup({ ma_extension_sma10_pct: value })} />
                <SetupNumber label={`21-EMA Abstand ${setupString("ma_extension_unit", "pct") === "atr" ? "ATR" : "%"}`} value={setupNumber("ma_extension_ema21_pct", 15)} onChange={(value) => updateSellSetup({ ma_extension_ema21_pct: value })} />
                <SetupNumber label={`50-SMA Abstand ${setupString("ma_extension_unit", "pct") === "atr" ? "ATR" : "%"}`} value={setupNumber("ma_extension_sma50_pct", 25)} onChange={(value) => updateSellSetup({ ma_extension_sma50_pct: value })} />
                <SetupNumber label={`200-SMA Abstand ${setupString("ma_extension_unit", "pct") === "atr" ? "ATR" : "%"}`} value={setupNumber("ma_extension_sma200_pct", 70)} onChange={(value) => updateSellSetup({ ma_extension_sma200_pct: value })} />
                <SetupNumber label="unteres Drittel Anzahl" value={setupNumber("low_closes_count", 4)} onChange={(value) => updateSellSetup({ low_closes_count: value })} />
                <SetupNumber label="unteres Drittel Fenster" value={setupNumber("low_closes_window", 10)} onChange={(value) => updateSellSetup({ low_closes_window: value })} />
                <UnitValueRow label="Scharfer Einbruch" unit={setupString("sharp_drop_unit", "pct")} value={setupNumber("sharp_drop_value", 6)} onUnitChange={(value) => updateSellSetup({ sharp_drop_unit: value })} onValueChange={(value) => updateSellSetup({ sharp_drop_value: value })} />
                <SetupNumber label="Reclaim Tage" value={setupNumber("sharp_drop_reclaim_days", 4)} onChange={(value) => updateSellSetup({ sharp_drop_reclaim_days: value })} />
                <SetupNumber label="Verlusttage Fenster" value={setupNumber("loss_days_window", 10)} onChange={(value) => updateSellSetup({ loss_days_window: value })} />
                <SetupNumber label="Stautage Anzahl" value={setupNumber("stall_days_count", 3)} onChange={(value) => updateSellSetup({ stall_days_count: value })} />
                <SetupNumber label="Stautage Fenster" value={setupNumber("stall_days_window", 10)} onChange={(value) => updateSellSetup({ stall_days_window: value })} />
                <UnitValueRow label="Größter Anstieg" unit={setupString("biggest_gain_unit", "pct")} value={setupNumber("biggest_gain_value", 10)} onUnitChange={(value) => updateSellSetup({ biggest_gain_unit: value })} onValueChange={(value) => updateSellSetup({ biggest_gain_value: value })} />
                <SetupNumber label="Anstieg relativ zum bisherigen Maximum" value={setupNumber("biggest_gain_multiplier", 1.5)} onChange={(value) => updateSellSetup({ biggest_gain_multiplier: value })} />
                <SetupNumber label="Anstieg Vergleichsfenster (Tage)" value={setupNumber("biggest_gain_lookback", 20)} onChange={(value) => updateSellSetup({ biggest_gain_lookback: value })} />
                <SetupNumber label="Stautag maximaler Kursfortschritt %" value={setupNumber("stall_days_max_change_pct", 1)} onChange={(value) => updateSellSetup({ stall_days_max_change_pct: value })} />
                <SetupNumber label="Stautag Volumenfaktor" value={setupNumber("stall_days_volume_ratio", 1.3)} onChange={(value) => updateSellSetup({ stall_days_volume_ratio: value })} />
              </div>
            </RuleSetupGroup>

            <RuleSetupGroup title="Defensives Verkaufen">
              <div className="grid gap-2 sm:grid-cols-2">
                <SetupNumber label="Kauftag-Reclaim Tage" value={setupNumber("buy_day_reclaim_days", 3)} onChange={(value) => updateSellSetup({ buy_day_reclaim_days: value })} />
                <SetupNumber label="MA-Reclaim Tage" value={setupNumber("ma_break_reclaim_days", 3)} onChange={(value) => updateSellSetup({ ma_break_reclaim_days: value })} />
                <SetupNumber label="Verlustwochen" value={setupNumber("loss_weeks_count", 3)} onChange={(value) => updateSellSetup({ loss_weeks_count: value })} />
                <SetupNumber label="Worst-Loss Tage" value={setupNumber("worst_drop_warmup_days", 20)} onChange={(value) => updateSellSetup({ worst_drop_warmup_days: value })} />
                <SetupNumber label="Worst-Loss Wochen" value={setupNumber("worst_drop_warmup_weeks", 4)} onChange={(value) => updateSellSetup({ worst_drop_warmup_weeks: value })} />
                <label className="flex items-center justify-between gap-3 rounded border border-[#d8e1ea] bg-[#f9fbfd] px-3 py-2 text-sm sm:col-span-2">
                  <span>Verlustwochen nur bei steigendem Volumen</span>
                  <input
                    checked={setupBoolean("loss_weeks_require_rising_volume", false)}
                    className="size-4 accent-emerald-300"
                    type="checkbox"
                    onChange={(event) => updateSellSetup({ loss_weeks_require_rising_volume: event.target.checked })}
                  />
                </label>
              </div>
            </RuleSetupGroup>

              </div>
            </details>
          </div>
  );
}

function RuleSetupGroup({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="rounded border border-[#e3e8ef] bg-[#f9fbfd] p-3">
      <h3 className="mb-3 text-sm font-semibold">{title}</h3>
      <div className="space-y-3">{children}</div>
    </div>
  );
}

function UnitValueRow({
  label,
  unit,
  value,
  onUnitChange,
  onValueChange
}: {
  label: string;
  unit: string;
  value: number;
  onUnitChange: (value: string) => void;
  onValueChange: (value: number) => void;
}) {
  return (
    <div className="grid gap-2 sm:grid-cols-[1fr_86px_92px]">
      <div className="rounded border border-[#d8e1ea] bg-white px-3 py-2 text-sm text-[#687386]">{label}</div>
      <select
        aria-label={`${label} Einheit`}
        className="rounded border border-[#d8e1ea] bg-white px-2 py-2 text-sm"
        value={unit}
        onChange={(event) => onUnitChange(event.target.value)}
      >
        <option value="pct">%</option>
        <option value="atr">ATR</option>
      </select>
      <input
        aria-label={label}
        className="rounded border border-[#d8e1ea] bg-white px-2 py-2 text-sm tabular-nums"
        min={label.includes("Tranche") ? 0 : /Tage|Wochen|Fenster|Anzahl/.test(label) ? 1 : 0.1}
        max={label.includes("Tranche") ? 100 : undefined}
        step={label.includes("Tranche") || /Tage|Wochen|Fenster|Anzahl/.test(label) ? 1 : 0.1}
        type="number"
        value={value}
        onChange={(event) => onValueChange(Number(event.target.value))}
      />
    </div>
  );
}

function SetupNumber({
  label,
  value,
  onChange
}: {
  label: string;
  value: number;
  onChange: (value: number) => void;
}) {
  return (
    <label className="block text-xs text-[#687386]">
      {label}
      <input
        className="mt-1 w-full rounded border border-[#d8e1ea] bg-white px-2 py-2 text-sm text-[#172033]"
        min={label.includes("Tranche") ? 0 : /Tage|Wochen|Fenster|Anzahl/.test(label) ? 1 : 0.1}
        max={label.includes("Tranche") ? 100 : undefined}
        step={label.includes("Tranche") || /Tage|Wochen|Fenster|Anzahl/.test(label) ? 1 : 0.1}
        type="number"
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
      />
    </label>
  );
}

const strategySetupCopy: Record<string, { title: string; detail: string }> = {
  custom: {
    title: "Benutzerdefinierte Strategie",
    detail: "Nur die hier ausgewählten Merkmale erzeugen Strategieempfehlungen. Andere aktive Merkmale bleiben als Status sichtbar, lösen aber keine Custom-Tranche aus."
  },
  rs_line: {
    title: "RS-Linie auf Tagesbasis",
    detail: "Es gelten die bestätigten Tagesschlusskurse der RS-Linie relativ zum S&P 500. Drei Stufen nutzen zwei Durchschnittslinien; Intraday-Kurse lösen diese Stufen nicht aus."
  },
  ema21_risk_averse: {
    title: "21-EMA risikoavers",
    detail: "Frühe Tranchen bei erstem deutlichen Schluss unter der 21-EMA und schwacher Bestätigung."
  },
  ema21_offensive: {
    title: "21-EMA offensiv",
    detail: "Erste Tranche erst nach drei bestätigten Schlüssen unter der 21-EMA."
  },
  peak_drawdown: {
    title: "Peak-Rückgang",
    detail: "Tranchen nach Rückgang vom 20-Tage-Hoch, danach Trendbruch- und Nothalt-Regeln."
  },
  buy_day_low: {
    title: "Kauftag-Tief",
    detail: "Überwacht Kauftagstief, Vortagestief und den Nothalt. Die Reclaim-Frist liegt im defensiven Setup."
  },
  ma_breaks: {
    title: "MA-Brüche",
    detail: "Erste Tranche nach bestätigtem 50-SMA-Bruch, finale Tranche direkt beim 200-SMA-Bruch."
  }
};

function StrategySpecificSetup({
  selectedStrategy,
  customSteps,
  setupNumber,
  setupString,
  updateCustomStrategyStep,
  addCustomStrategyStep,
  removeCustomStrategyStep,
  updateSellSetup
}: {
  selectedStrategy: string;
  customSteps: CustomStrategyStep[];
  setupNumber: (key: string, fallback: number) => number;
  setupString: (key: string, fallback: string) => string;
  updateCustomStrategyStep: (index: number, patch: Partial<CustomStrategyStep>) => void;
  addCustomStrategyStep: () => void;
  removeCustomStrategyStep: (index: number) => void;
  updateSellSetup: (patch: Record<string, unknown>) => void;
}) {
  const copy = strategySetupCopy[selectedStrategy] ?? strategySetupCopy.custom;

  if (selectedStrategy === "custom") {
    return (
      <div className="xl:col-span-3">
        <RuleSetupGroup title={copy.title}>
          <p className="text-sm leading-6 text-[#687386]">{copy.detail}</p>
          <div className="space-y-2">
            {customSteps.map((step, index) => (
              <div key={`${step.feature_id}-${index}`} className="grid gap-2 sm:grid-cols-[1fr_120px_40px]">
                <select
                  aria-label={`Custom Merkmal ${index + 1}`}
                  className="rounded border border-[#d8e1ea] bg-white px-2 py-2 text-sm"
                  value={step.feature_id}
                  onChange={(event) => updateCustomStrategyStep(index, { feature_id: event.target.value })}
                >
                  {CUSTOM_FEATURE_OPTIONS.map((option) => (
                    <option key={option.value} value={option.value} disabled={customSteps.some((item, itemIndex) => itemIndex !== index && item.feature_id === option.value)}>{option.label}</option>
                  ))}
                </select>
                <input
                  aria-label={`Tranche ${index + 1} Prozent`}
                  className="rounded border border-[#d8e1ea] bg-white px-2 py-2 text-sm tabular-nums"
                  max={100}
                  min={0}
                  step={1}
                  type="number"
                  value={step.tranche_percent}
                  onChange={(event) => updateCustomStrategyStep(index, { tranche_percent: Number(event.target.value) })}
                />
                <button
                  aria-label={`Custom Merkmal ${index + 1} entfernen`}
                  className="flex size-10 items-center justify-center rounded border border-[#d8e1ea] bg-white text-[#687386] transition hover:border-rose-300/60 hover:text-rose-700 disabled:cursor-not-allowed disabled:opacity-40"
                  disabled={customSteps.length <= 1}
                  type="button"
                  onClick={() => removeCustomStrategyStep(index)}
                >
                  <Minus size={15} />
                </button>
              </div>
            ))}
          </div>
          <button
            className="inline-flex items-center gap-2 rounded border border-[#d8e1ea] bg-white px-3 py-2 text-sm text-[#172033] transition hover:border-emerald-300/60"
            type="button"
            disabled={customSteps.length >= CUSTOM_FEATURE_OPTIONS.length}
            onClick={addCustomStrategyStep}
          >
            <Plus size={15} />
            Merkmal hinzufügen
          </button>
        </RuleSetupGroup>
      </div>
    );
  }

  if (selectedStrategy === "rs_line") {
    return (
      <div className="xl:col-span-3">
        <RuleSetupGroup title={copy.title}>
          <p className="text-sm leading-6 text-[#687386]">{copy.detail}</p>
          <div className="grid gap-2 sm:grid-cols-3">
            <div className="space-y-2">
              <SetupNumber label="1. Tranche %" value={setupNumber("rs_tranche_1_pct", 25)} onChange={(value) => updateSellSetup({ rs_tranche_1_pct: value, rs_tranche_3_pct: Math.max(0, 100 - value - setupNumber("rs_tranche_2_pct", 25)) })} />
              <p className="text-sm text-[#687386]">Erster Tagesschluss unter dem 21-Tage-SMA der RS-Linie.</p>
            </div>
            <div className="space-y-2">
              <SetupNumber label="2. Tranche %" value={setupNumber("rs_tranche_2_pct", 25)} onChange={(value) => updateSellSetup({ rs_tranche_2_pct: value, rs_tranche_3_pct: Math.max(0, 100 - setupNumber("rs_tranche_1_pct", 25) - value) })} />
              <p className="text-sm text-[#687386]">Drei Tagesschlüsse in Folge unter dem 21-Tage-SMA. Der erste Bruchtag zählt mit.</p>
            </div>
            <ReadOnlySetupTile label="3. Tranche · Restposition" value={`${Math.max(0, 100 - setupNumber("rs_tranche_1_pct", 25) - setupNumber("rs_tranche_2_pct", 25))} % geplant`} detail="Tagesschluss unter dem 50-Tage-SMA der RS-Linie: gesamte verbleibende Position verkaufen, auch wenn frühere Stufen übersprungen wurden." />
          </div>
          {setupNumber("rs_tranche_1_pct", 25) + setupNumber("rs_tranche_2_pct", 25) > 100 && <p role="alert" className="text-sm text-rose-700">Die ersten beiden RS-Tranchen dürfen zusammen höchstens 100 % ergeben.</p>}
        </RuleSetupGroup>
      </div>
    );
  }

  if (selectedStrategy === "ema21_risk_averse") {
    return (
      <div className="xl:col-span-3">
        <RuleSetupGroup title={copy.title}>
          <p className="text-sm leading-6 text-[#687386]">{copy.detail}</p>
          <div className="grid gap-2 sm:grid-cols-3">
            <SetupNumber label="1. Tranche %" value={setupNumber("ema21_risk_averse_first_pct", 25)} onChange={(value) => updateSellSetup({ ema21_risk_averse_first_pct: value })} />
            <SetupNumber label="2. Tranche %" value={setupNumber("ema21_risk_averse_second_pct", 25)} onChange={(value) => updateSellSetup({ ema21_risk_averse_second_pct: value })} />
            <SetupNumber label="3. Tranche %" value={setupNumber("ema21_risk_averse_third_pct", 25)} onChange={(value) => updateSellSetup({ ema21_risk_averse_third_pct: value })} />
          </div>
        </RuleSetupGroup>
      </div>
    );
  }

  if (selectedStrategy === "ema21_offensive") {
    return (
      <div className="xl:col-span-3">
        <RuleSetupGroup title={copy.title}>
          <p className="text-sm leading-6 text-[#687386]">{copy.detail}</p>
          <div className="grid gap-2 sm:grid-cols-3">
            <SetupNumber label="1. Tranche %" value={setupNumber("ema21_offensive_first_pct", 33)} onChange={(value) => updateSellSetup({ ema21_offensive_first_pct: value })} />
            <ReadOnlySetupTile label="Weitere Tranche" value="33 %" detail="50-SMA-Bruch oder drei tiefere Tiefs" />
            <ReadOnlySetupTile label="Finale Tranche" value="100%" detail="Nothalt erreicht" />
          </div>
        </RuleSetupGroup>
      </div>
    );
  }

  if (selectedStrategy === "peak_drawdown") {
    return (
      <div className="xl:col-span-3">
        <RuleSetupGroup title={copy.title}>
          <p className="text-sm leading-6 text-[#687386]">{copy.detail}</p>
          <div className="grid gap-3 lg:grid-cols-2">
            <UnitValueRow
              label="1. Rückgangsschwelle"
              unit={setupString("peak_drawdown_first_unit", "pct")}
              value={setupNumber("peak_drawdown_first_value", 8)}
              onUnitChange={(value) => updateSellSetup({ peak_drawdown_first_unit: value })}
              onValueChange={(value) => updateSellSetup({ peak_drawdown_first_value: value })}
            />
            <UnitValueRow
              label="2. Rückgangsschwelle"
              unit={setupString("peak_drawdown_second_unit", "pct")}
              value={setupNumber("peak_drawdown_second_value", 15)}
              onUnitChange={(value) => updateSellSetup({ peak_drawdown_second_unit: value })}
              onValueChange={(value) => updateSellSetup({ peak_drawdown_second_value: value })}
            />
            <SetupNumber label="1. Tranche %" value={setupNumber("peak_drawdown_first_pct", 25)} onChange={(value) => updateSellSetup({ peak_drawdown_first_pct: value })} />
            <SetupNumber label="2. Tranche %" value={setupNumber("peak_drawdown_second_pct", 25)} onChange={(value) => updateSellSetup({ peak_drawdown_second_pct: value })} />
          </div>
        </RuleSetupGroup>
      </div>
    );
  }

  return (
    <div className="xl:col-span-3">
      <RuleSetupGroup title={copy.title}>
        <p className="text-sm leading-6 text-[#687386]">{copy.detail}</p>
        <div className="grid gap-2 sm:grid-cols-2">
          <ReadOnlySetupTile label="Genutzte Merkmale" value={selectedStrategy === "buy_day_low" ? "Kauftag" : "50/200-SMA"} detail="Konkrete Schwellen liegen in Nothalt und defensivem Setup." />
          <ReadOnlySetupTile label="Speichern" value="erforderlich" detail="Strategiewechsel wird erst nach dem Speichern in Bewertung und Empfehlungen übernommen." />
        </div>
      </RuleSetupGroup>
    </div>
  );
}

function ReadOnlySetupTile({ label, value, detail }: { label: string; value: string; detail: string }) {
  return (
    <div className="rounded border border-[#d8e1ea] bg-white p-3">
      <div className="text-xs uppercase text-[#687386]">{label}</div>
      <div className="mt-2 text-lg font-semibold tabular-nums">{value}</div>
      <div className="mt-1 text-xs leading-5 text-[#687386]">{detail}</div>
    </div>
  );
}
