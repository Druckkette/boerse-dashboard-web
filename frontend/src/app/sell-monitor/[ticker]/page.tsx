"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Minus, Plus, Save } from "lucide-react";
import { useParams } from "next/navigation";
import { useState, type ReactNode } from "react";
import { KpiCard } from "@/components/ui/kpi-card";
import { StatusChip } from "@/components/ui/status-chip";
import { StockPricePanel } from "@/features/stocks/stock-price-panel";
import { api } from "@/lib/api/client";
import type { ChartMarker } from "@/components/ui/line-chart-card";
import type {
  PendingStatus,
  SellManualInput,
  SellRuleFeature,
  SellSignal,
  SellStrategyResult,
  Tone
} from "@/lib/types/api";

const toneByStatus = {
  Halten: "good",
  Beobachten: "warning",
  Verkaufen: "bad"
} as const;

const toneByPending: Record<PendingStatus, "good" | "neutral" | "warning" | "bad"> = {
  halten: "good",
  in_bestaetigung: "warning",
  snoozed: "neutral",
  scharf: "bad"
};

const STRATEGY_OPTIONS = [
  { value: "rs_line", label: "RS-Linie 21/50" },
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

export default function SellMonitorTickerPage() {
  const params = useParams<{ ticker: string }>();
  const ticker = params.ticker.toUpperCase();
  const queryClient = useQueryClient();
  const metrics = useQuery({ queryKey: ["sell-metrics", ticker], queryFn: () => api.sellMetrics(ticker) });
  const evaluation = useQuery({ queryKey: ["sell-evaluation", ticker], queryFn: () => api.sellEvaluation(ticker) });
  const [manualDraft, setManualDraft] = useState<{ ticker: string; value: SellManualInput } | null>(null);

  const saveManual = useMutation({
    mutationFn: (nextManual: SellManualInput) => api.patchSellManual(ticker, nextManual),
    onSuccess: (updated) => {
      setManualDraft(null);
      queryClient.setQueryData(["sell-evaluation", ticker], evaluation.data ? { ...evaluation.data, manual: updated } : evaluation.data);
      queryClient.invalidateQueries({ queryKey: ["sell-evaluation", ticker] });
      queryClient.invalidateQueries({ queryKey: ["sell-metrics", ticker] });
      queryClient.invalidateQueries({ queryKey: ["sell-ranking"] });
    }
  });

  const currentManual =
    manualDraft?.ticker === ticker ? manualDraft.value : evaluation.data?.manual ?? null;
  const manualDirty = manualDraft?.ticker === ticker;

  const mainSignals = [
    ...(evaluation.data?.killer_signals ?? []),
    ...(evaluation.data?.tranche_signals ?? [])
  ].slice(0, 5);
  const warningSignals = [
    ...(evaluation.data?.warning_signals ?? []),
    ...(evaluation.data?.watch_signals ?? [])
  ].slice(0, 6);

  function updateManual(patch: Partial<SellManualInput>) {
    setManualDraft((previous) => {
      const base = previous?.ticker === ticker ? previous.value : evaluation.data?.manual;
      return base ? { ticker, value: { ...base, ...patch, ticker } } : previous;
    });
  }

  function updateSellSetup(patch: Record<string, unknown>) {
    updateManual({ sell_setup: { ...(currentManual?.sell_setup ?? {}), ...patch } });
  }

  function setupNumber(key: string, fallback: number) {
    const raw = currentManual?.sell_setup?.[key];
    const parsed = typeof raw === "number" ? raw : typeof raw === "string" ? Number(raw) : fallback;
    return Number.isFinite(parsed) ? parsed : fallback;
  }

  function setupString(key: string, fallback: string) {
    const raw = currentManual?.sell_setup?.[key];
    return typeof raw === "string" && raw ? raw : fallback;
  }

  function setupBoolean(key: string, fallback: boolean) {
    const raw = currentManual?.sell_setup?.[key];
    return typeof raw === "boolean" ? raw : fallback;
  }

  function customStrategySteps(): CustomStrategyStep[] {
    const raw = currentManual?.sell_setup?.custom_strategy_steps;
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
      custom_strategy_steps: [...customStrategySteps(), { feature_id: "offensive_profit_target", tranche_percent: 25 }]
    });
  }

  function removeCustomStrategyStep(index: number) {
    updateSellSetup({ custom_strategy_steps: customStrategySteps().filter((_, itemIndex) => itemIndex !== index) });
  }

  function persistManual() {
    if (!currentManual) return;
    saveManual.mutate({
      ...currentManual,
      ticker
    });
  }

  const health = evaluation.data?.health ?? metrics.data?.health;
  const recommendationTone =
    (evaluation.data?.recommendation_percent ?? 0) >= 75
      ? "bad"
      : (evaluation.data?.recommendation_percent ?? 0) > 0
        ? "warning"
        : "good";
  const sellChartMarkers = buildSellChartMarkers(
    [...mainSignals, ...warningSignals],
    metrics.data?.current_price
  );
  const selectedStrategy = setupString("strategy_key", "rs_line");
  const distributionDays = metrics.data?.distribution_days_25;
  const rsTrend = metrics.data?.rs_trend ?? health?.rs_trend;

  return (
    <div className="space-y-4">
      <div className="rounded-[14px] border border-[#e3e8ef] bg-white px-4 py-3 shadow-[0_5px_18px_rgba(15,23,42,0.05)]">
        <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <div>
            <div className="text-[10px] font-semibold uppercase tracking-[0.1em] text-[#687386]">Verkaufsmonitor</div>
            <h1 className="mt-0.5 text-2xl font-semibold text-[#172033]">{ticker}</h1>
            <div className="mt-1 text-xs leading-5 text-[#687386]">
              {evaluation.data?.explanation_short ?? "Evaluation wird geladen."}
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <StatusChip tone={health ? toneByStatus[health.status] : "neutral"}>
              {health?.status ?? "lädt"}
            </StatusChip>
            <StatusChip tone={evaluation.data ? toneByPending[evaluation.data.pending_status] : "neutral"}>
              {evaluation.data?.display_label ?? "loading"}
            </StatusChip>
          </div>
        </div>
      </div>

      <div className="grid gap-2.5 sm:grid-cols-2 xl:grid-cols-6">
        <KpiCard item={{ label: "Health Score", value: health ? health.health_score.toFixed(1) : "-", detail: health?.status ?? "Status", tone: health ? toneByStatus[health.status] : "neutral" }} />
        <KpiCard item={{ label: "Empfehlung", value: `${evaluation.data?.sell_now_percent ?? 0}%`, detail: evaluation.data?.regime ?? "Regime", tone: recommendationTone }} />
        <KpiCard item={{ label: "P&L", value: formatPct(metrics.data?.pnl_pct), detail: "seit Kauf", tone: (metrics.data?.pnl_pct ?? 0) >= 0 ? "good" : "bad" }} />
        <KpiCard item={{ label: "RS Trend", value: labelForRsTrend(rsTrend), detail: "Relative-Stärke-Linie", tone: toneForRsTrend(rsTrend) }} />
        <KpiCard item={{ label: "Distribution", value: distributionDays == null ? "-" : String(distributionDays), detail: "Tage in 25 Sessions", tone: distributionDays == null ? "neutral" : distributionDays >= 4 ? "warning" : "good" }} />
        <KpiCard item={{ label: "ATR14", value: formatNumber(metrics.data?.atr14), detail: "für ATR-basierte Regeln", tone: "neutral" }} />
      </div>

      <SellStrategyPanel strategy={evaluation.data?.strategy} />

      <StockPricePanel
        levels={[]}
        markers={sellChartMarkers}
        ticker={ticker}
        title="Sell Context"
      />

      <div className="grid gap-3 xl:grid-cols-3">
        <SellFeatureSection
          description="Harter Schutz gegen definierte Verlusthöhe. Dieses Merkmal übersteuert alle anderen Strategien."
          features={evaluation.data?.emergency_features ?? []}
          title="Nothalt"
        />

        <SellFeatureSection
          description="Gewinnsicherung, Überdehnung, Rückfall vom Peak und Auffälligkeiten im Tagesverhalten."
          features={evaluation.data?.offensive_features ?? []}
          title="Offensives Verkaufen"
        />

        <SellFeatureSection
          description="Schutz nach Kauf, Trendbrüche, Verlustwochen und neue Worst-Loss-Benchmarks."
          features={evaluation.data?.defensive_features ?? []}
          title="Defensives Verkaufen"
        />
      </div>

      {currentManual && (
        <section className="rounded border border-[#2d333d] bg-[#171a20] p-5">
          <div className="mb-5 flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
            <div>
              <h2 className="text-base font-semibold">Verkaufsregeln Setup</h2>
              <div className="mt-1 text-sm text-[#a0a7b4]">
                Pro Aktie gespeichert. Änderungen wirken nach dem Speichern auf Bewertung und Strategieanzeige.
              </div>
            </div>
            <button
              className="inline-flex items-center justify-center gap-2 rounded border border-emerald-300/35 bg-emerald-300/10 px-3 py-2 text-sm text-emerald-100 transition hover:border-emerald-200 disabled:cursor-not-allowed disabled:opacity-50"
              disabled={!currentManual || saveManual.isPending || !manualDirty}
              type="button"
              onClick={persistManual}
            >
              <Save size={15} />
              {saveManual.isPending ? "Speichert" : manualDirty ? "Setup speichern" : "Gespeichert"}
            </button>
          </div>

          <div className="grid gap-5 xl:grid-cols-[1fr_1fr_1fr]">
            <label className="block text-sm xl:col-span-3">
              <span className="mb-1 block text-[#a0a7b4]">Aktive Verkaufsstrategie</span>
              <select
                className="w-full rounded border border-[#2d333d] bg-[#111419] px-3 py-2"
                value={selectedStrategy}
                onChange={(event) => updateSellSetup({ strategy_key: event.target.value })}
              >
                {STRATEGY_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>{option.label}</option>
                ))}
              </select>
            </label>

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
              <div className="grid gap-2 sm:grid-cols-2">
                <SetupNumber label="10-SMA Abstand %" value={setupNumber("ma_extension_sma10_pct", 10)} onChange={(value) => updateSellSetup({ ma_extension_sma10_pct: value })} />
                <SetupNumber label="21-EMA Abstand %" value={setupNumber("ma_extension_ema21_pct", 15)} onChange={(value) => updateSellSetup({ ma_extension_ema21_pct: value })} />
                <SetupNumber label="50-SMA Abstand %" value={setupNumber("ma_extension_sma50_pct", 25)} onChange={(value) => updateSellSetup({ ma_extension_sma50_pct: value })} />
                <SetupNumber label="200-SMA Abstand %" value={setupNumber("ma_extension_sma200_pct", 70)} onChange={(value) => updateSellSetup({ ma_extension_sma200_pct: value })} />
                <SetupNumber label="unteres Drittel Anzahl" value={setupNumber("low_closes_count", 4)} onChange={(value) => updateSellSetup({ low_closes_count: value })} />
                <SetupNumber label="unteres Drittel Fenster" value={setupNumber("low_closes_window", 10)} onChange={(value) => updateSellSetup({ low_closes_window: value })} />
                <SetupNumber label="scharfer Einbruch %" value={setupNumber("sharp_drop_value", 6)} onChange={(value) => updateSellSetup({ sharp_drop_value: value })} />
                <SetupNumber label="Reclaim Tage" value={setupNumber("sharp_drop_reclaim_days", 4)} onChange={(value) => updateSellSetup({ sharp_drop_reclaim_days: value })} />
                <SetupNumber label="Verlusttage Fenster" value={setupNumber("loss_days_window", 10)} onChange={(value) => updateSellSetup({ loss_days_window: value })} />
                <SetupNumber label="Stautage Anzahl" value={setupNumber("stall_days_count", 3)} onChange={(value) => updateSellSetup({ stall_days_count: value })} />
                <SetupNumber label="Stautage Fenster" value={setupNumber("stall_days_window", 10)} onChange={(value) => updateSellSetup({ stall_days_window: value })} />
                <SetupNumber label="größter Anstieg %" value={setupNumber("biggest_gain_value", 10)} onChange={(value) => updateSellSetup({ biggest_gain_value: value })} />
              </div>
            </RuleSetupGroup>

            <RuleSetupGroup title="Defensives Verkaufen">
              <div className="grid gap-2 sm:grid-cols-2">
                <SetupNumber label="Kauftag-Reclaim Tage" value={setupNumber("buy_day_reclaim_days", 3)} onChange={(value) => updateSellSetup({ buy_day_reclaim_days: value })} />
                <SetupNumber label="MA-Reclaim Tage" value={setupNumber("ma_break_reclaim_days", 3)} onChange={(value) => updateSellSetup({ ma_break_reclaim_days: value })} />
                <SetupNumber label="Verlustwochen" value={setupNumber("loss_weeks_count", 3)} onChange={(value) => updateSellSetup({ loss_weeks_count: value })} />
                <SetupNumber label="Worst-Loss Tage" value={setupNumber("worst_drop_warmup_days", 20)} onChange={(value) => updateSellSetup({ worst_drop_warmup_days: value })} />
                <SetupNumber label="Worst-Loss Wochen" value={setupNumber("worst_drop_warmup_weeks", 4)} onChange={(value) => updateSellSetup({ worst_drop_warmup_weeks: value })} />
                <label className="flex items-center justify-between gap-3 rounded border border-[#2d333d] bg-[#111419] px-3 py-2 text-sm sm:col-span-2">
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
          </div>
        </section>
      )}
    </div>
  );
}

function SellStrategyPanel({ strategy }: { strategy?: SellStrategyResult }) {
  return (
    <section className="rounded border border-[#2d333d] bg-[#171a20] p-5">
      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h2 className="text-base font-semibold">Verkaufsstrategien</h2>
          <div className="mt-1 text-sm text-[#a0a7b4]">
            {strategy?.description ?? "Strategie wird geladen."}
          </div>
        </div>
        <StatusChip tone={(strategy?.recommendation_percent ?? 0) > 0 ? "warning" : "good"}>
          {strategy?.label ?? "lädt"}
        </StatusChip>
      </div>
      <div className="mb-4 grid gap-3 md:grid-cols-3">
        <MetricTile label="Aktive Strategie" value={strategy?.label ?? "-"} detail={strategy?.strategy_key ?? "strategy_key"} />
        <MetricTile label="Strategie-Ziel" value={`${strategy?.recommendation_percent ?? 0}%`} detail="vor Abzug bereits verkaufter Tranchen" />
        <MetricTile
          label="Aktive Empfehlungen"
          value={`${strategy?.recommendations.filter((item) => item.active).length ?? 0}`}
          detail={`${strategy?.recommendations.length ?? 0} definierte Strategiebedingungen`}
        />
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        {(strategy?.recommendations ?? []).length === 0 && (
          <div className="rounded border border-[#242a33] bg-[#111419] p-4 text-sm text-[#a0a7b4]">
            Keine Strategieempfehlungen vorhanden.
          </div>
        )}
        {(strategy?.recommendations ?? []).map((recommendation) => (
          <div
            key={recommendation.id}
            className={`rounded border p-3 ${recommendation.active ? "border-amber-300/45 bg-amber-300/10" : "border-[#242a33] bg-[#111419]"}`}
          >
            <div className="mb-2 flex items-start justify-between gap-3">
              <div className="font-medium">{recommendation.label}</div>
              <StatusChip tone={recommendation.active ? "warning" : "neutral"}>
                {recommendation.active ? `aktiv · ${recommendation.tranche_percent}%` : "inaktiv"}
              </StatusChip>
            </div>
            <div className="grid gap-2 text-sm">
              <StrategyStatusRow label="Aktueller Stand" value={recommendation.detail || "Noch kein Messwert für diese Bedingung."} />
              <StrategyStatusRow label="Kriterium" value={recommendation.trigger || "Regel ohne separate Schwelle."} />
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function StrategyStatusRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded border border-[#2d333d] bg-[#171a20] px-3 py-2">
      <div className="text-xs uppercase text-[#77808f]">{label}</div>
      <div className="mt-1 text-[#d8dde6]">{value}</div>
    </div>
  );
}

function SellFeatureSection({
  title,
  description,
  features
}: {
  title: string;
  description: string;
  features: SellRuleFeature[];
}) {
  const activeCount = features.filter((feature) => feature.active).length;
  return (
    <section className="rounded border border-[#2d333d] bg-[#171a20] p-5">
      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h2 className="text-base font-semibold">{title}</h2>
          <div className="mt-1 text-sm text-[#a0a7b4]">{description}</div>
        </div>
        <StatusChip tone={activeCount > 0 ? "warning" : "good"}>{activeCount} aktiv</StatusChip>
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        {features.map((feature) => (
          <SellFeatureCard key={feature.id} feature={feature} />
        ))}
      </div>
    </section>
  );
}

function SellFeatureCard({ feature }: { feature: SellRuleFeature }) {
  const tone = toneForFeature(feature);
  const border =
    feature.active && feature.severity === "killer"
      ? "border-rose-300/50 bg-rose-400/10"
      : feature.active
        ? "border-amber-300/45 bg-amber-300/10"
        : "border-[#242a33] bg-[#111419]";
  return (
    <div className={`rounded border p-3 ${border}`}>
      <div className="mb-2 flex items-start justify-between gap-3">
        <div>
          <div className="font-medium">{feature.label}</div>
          <div className="mt-1 text-xs text-[#77808f]">{feature.threshold}</div>
        </div>
        <StatusChip tone={tone}>{feature.active ? "aktiv" : "inaktiv"}</StatusChip>
      </div>
      <div className="text-sm text-[#d8dde6]">{feature.value || "-"}</div>
      <div className="mt-2 text-xs leading-5 text-[#a0a7b4]">{feature.detail}</div>
    </div>
  );
}

function toneForFeature(feature: SellRuleFeature): Tone {
  if (!feature.active) return "neutral";
  if (feature.severity === "killer") return "bad";
  if (feature.severity === "tranche" || feature.severity === "warning") return "warning";
  return "neutral";
}

function RuleSetupGroup({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="rounded border border-[#242a33] bg-[#111419] p-3">
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
      <div className="rounded border border-[#2d333d] bg-[#171a20] px-3 py-2 text-sm text-[#a0a7b4]">{label}</div>
      <select
        className="rounded border border-[#2d333d] bg-[#171a20] px-2 py-2 text-sm"
        value={unit}
        onChange={(event) => onUnitChange(event.target.value)}
      >
        <option value="pct">%</option>
        <option value="atr">ATR</option>
      </select>
      <input
        aria-label={label}
        className="rounded border border-[#2d333d] bg-[#171a20] px-2 py-2 text-sm tabular-nums"
        step="0.1"
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
    <label className="block text-xs text-[#a0a7b4]">
      {label}
      <input
        className="mt-1 w-full rounded border border-[#2d333d] bg-[#171a20] px-2 py-2 text-sm text-[#d8dde6]"
        step="0.1"
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
    title: "RS-Linie 21/50",
    detail: "Tranchen werden über Brüche der RS-Linie gegen ihre 21-EMA und 50-EMA gesteuert."
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
          <p className="text-sm leading-6 text-[#a0a7b4]">{copy.detail}</p>
          <div className="space-y-2">
            {customSteps.map((step, index) => (
              <div key={`${step.feature_id}-${index}`} className="grid gap-2 sm:grid-cols-[1fr_120px_40px]">
                <select
                  aria-label={`Custom Merkmal ${index + 1}`}
                  className="rounded border border-[#2d333d] bg-[#171a20] px-2 py-2 text-sm"
                  value={step.feature_id}
                  onChange={(event) => updateCustomStrategyStep(index, { feature_id: event.target.value })}
                >
                  {CUSTOM_FEATURE_OPTIONS.map((option) => (
                    <option key={option.value} value={option.value}>{option.label}</option>
                  ))}
                </select>
                <input
                  aria-label={`Tranche ${index + 1} Prozent`}
                  className="rounded border border-[#2d333d] bg-[#171a20] px-2 py-2 text-sm tabular-nums"
                  max={100}
                  min={0}
                  step={1}
                  type="number"
                  value={step.tranche_percent}
                  onChange={(event) => updateCustomStrategyStep(index, { tranche_percent: Number(event.target.value) })}
                />
                <button
                  aria-label={`Custom Merkmal ${index + 1} entfernen`}
                  className="flex size-10 items-center justify-center rounded border border-[#2d333d] bg-[#171a20] text-[#a0a7b4] transition hover:border-rose-300/60 hover:text-rose-100 disabled:cursor-not-allowed disabled:opacity-40"
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
            className="inline-flex items-center gap-2 rounded border border-[#2d333d] bg-[#171a20] px-3 py-2 text-sm text-[#d8dde6] transition hover:border-emerald-300/60"
            type="button"
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
          <p className="text-sm leading-6 text-[#a0a7b4]">{copy.detail}</p>
          <div className="grid gap-2 sm:grid-cols-3">
            <SetupNumber label="1. Tranche %" value={setupNumber("rs_tranche_1_pct", 25)} onChange={(value) => updateSellSetup({ rs_tranche_1_pct: value })} />
            <SetupNumber label="2. Tranche %" value={setupNumber("rs_tranche_2_pct", 25)} onChange={(value) => updateSellSetup({ rs_tranche_2_pct: value })} />
            <SetupNumber label="3. Tranche %" value={setupNumber("rs_tranche_3_pct", 50)} onChange={(value) => updateSellSetup({ rs_tranche_3_pct: value })} />
          </div>
        </RuleSetupGroup>
      </div>
    );
  }

  if (selectedStrategy === "ema21_risk_averse") {
    return (
      <div className="xl:col-span-3">
        <RuleSetupGroup title={copy.title}>
          <p className="text-sm leading-6 text-[#a0a7b4]">{copy.detail}</p>
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
          <p className="text-sm leading-6 text-[#a0a7b4]">{copy.detail}</p>
          <div className="grid gap-2 sm:grid-cols-3">
            <SetupNumber label="1. Tranche %" value={setupNumber("ema21_offensive_first_pct", 33)} onChange={(value) => updateSellSetup({ ema21_offensive_first_pct: value })} />
            <ReadOnlySetupTile label="Weitere Tranche" value="33%" detail="50-SMA-Bruch oder drei tiefere Tiefs" />
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
          <p className="text-sm leading-6 text-[#a0a7b4]">{copy.detail}</p>
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
        <p className="text-sm leading-6 text-[#a0a7b4]">{copy.detail}</p>
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
    <div className="rounded border border-[#2d333d] bg-[#171a20] p-3">
      <div className="text-xs uppercase text-[#a0a7b4]">{label}</div>
      <div className="mt-2 text-lg font-semibold tabular-nums">{value}</div>
      <div className="mt-1 text-xs leading-5 text-[#77808f]">{detail}</div>
    </div>
  );
}

function MetricTile({ label, value, detail }: { label: string; value: string; detail: string }) {
  return (
    <div className="rounded border border-[#2d333d] bg-[#111419] p-3">
      <div className="text-xs uppercase text-[#a0a7b4]">{label}</div>
      <div className="mt-2 text-xl font-semibold tabular-nums">{value}</div>
      <div className="mt-1 line-clamp-2 text-xs text-[#a0a7b4]">{detail}</div>
    </div>
  );
}

function formatNumber(value?: number | null) {
  return value == null ? "-" : value.toFixed(2);
}

function formatPct(value?: number | null) {
  return value == null ? "-" : `${value.toFixed(1)}%`;
}

function labelForRsTrend(value?: string | null) {
  if (value === "hoch") return "hoch";
  if (value === "runter") return "runter";
  if (value === "seitwärts" || value === "seitwaerts") return "seitwärts";
  return "-";
}

function toneForRsTrend(value?: string | null): Tone {
  if (value === "hoch") return "good";
  if (value === "runter") return "bad";
  if (value === "seitwärts" || value === "seitwaerts") return "neutral";
  return "neutral";
}

function buildSellChartMarkers(signals: SellSignal[], currentPrice?: number | null): ChartMarker[] {
  return signals
    .filter((signal) => signal.signal_date)
    .slice(0, 8)
    .map((signal) => ({
      key: `${signal.id}-${signal.signal_date}`,
      date: signal.signal_date,
      label: `${signal.contribution_percent}% ${signal.label}`,
      value: markerValueFromSignal(signal, currentPrice),
      color: colorForSignal(signal)
    }));
}

function markerValueFromSignal(signal: SellSignal, currentPrice?: number | null) {
  const match = signal.event_note.match(/Nächste Marke:\s*([0-9]+(?:[.,][0-9]+)?)/);
  if (!match) return currentPrice ?? null;
  const parsed = Number(match[1].replace(",", "."));
  return Number.isFinite(parsed) ? parsed : currentPrice ?? null;
}

function colorForSignal(signal: SellSignal) {
  if (signal.severity === "killer") return "#fb7185";
  if (signal.severity === "tranche") return "#fbbf24";
  if (signal.severity === "warning") return "#fdba74";
  return "#93c5fd";
}
