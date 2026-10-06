"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowRight, CircleAlert } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { KpiCard } from "@/components/ui/kpi-card";
import { StatusChip } from "@/components/ui/status-chip";
import { StockPricePanel } from "@/features/stocks/stock-price-panel";
import { api } from "@/lib/api/client";
import { SellSetupPanel } from "@/features/sell/sell-setup-panel";
import type { ChartMarker } from "@/components/ui/line-chart-card";
import type {
  PendingStatus,
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

export default function SellMonitorTickerPage() {
  const params = useParams<{ ticker: string }>();
  const ticker = params.ticker.toUpperCase();
  const metrics = useQuery({ queryKey: ["sell-metrics", ticker], queryFn: () => api.sellMetrics(ticker), retry: false });
  const evaluation = useQuery({ queryKey: ["sell-evaluation", ticker], queryFn: () => api.sellEvaluation(ticker), retry: false });

  const unavailableError = evaluation.error ?? metrics.error;
  if (unavailableError) {
    return <div className="space-y-4"><SellMonitorUnavailable ticker={ticker} detail={errorText(unavailableError)} /><SellSetupPanel key={ticker} ticker={ticker} /></div>;
  }

  const mainSignals = [
    ...(evaluation.data?.killer_signals ?? []),
    ...(evaluation.data?.tranche_signals ?? [])
  ].slice(0, 5);
  const warningSignals = [
    ...(evaluation.data?.warning_signals ?? []),
    ...(evaluation.data?.watch_signals ?? [])
  ].slice(0, 6);

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
              {evaluation.isLoading ? "Evaluation wird geladen…" : evaluation.data?.explanation_short ?? "Für diese Position liegt keine Evaluation vor."}
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <StatusChip tone={health ? toneByStatus[health.status] : "neutral"}>
              {health ? `Zustand: ${health.status}` : "lädt"}
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

      <SellSetupPanel key={ticker} ticker={ticker} />

      <SellStrategyPanel strategy={evaluation.data?.strategy} />

      <StockPricePanel
        levels={[]}
        markers={sellChartMarkers}
        ticker={ticker}
        title="Sell Context"
        sellRsHistory={metrics.data?.raw_payload.metrics.rs_chart_history ?? []}
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

    </div>
  );
}

function SellMonitorUnavailable({ ticker, detail }: { ticker: string; detail: string }) {
  return <div className="space-y-4">
    <div className="rounded-[14px] border border-[#e3e8ef] bg-white px-4 py-3 shadow-[0_5px_18px_rgba(15,23,42,0.05)]">
      <div className="text-[10px] font-semibold uppercase tracking-[0.1em] text-[#687386]">Verkaufsmonitor</div>
      <h1 className="mt-0.5 text-2xl font-semibold text-[#172033]">{ticker}</h1>
    </div>
    <section className="rounded-[14px] border border-[#f0c9c4] bg-[#fff8f7] p-5" role="alert">
      <div className="flex items-start gap-3">
        <CircleAlert className="mt-0.5 shrink-0 text-[#c2413b]" size={19} />
        <div>
          <h2 className="font-semibold text-[#172033]">Diese Position kann aktuell nicht bewertet werden.</h2>
          <p className="mt-1 text-sm leading-6 text-[#687386]">{detail}</p>
          <p className="mt-2 text-sm leading-6 text-[#687386]">Sobald genügend Kursdaten vorliegen, steht die Evaluation wieder zur Verfügung.</p>
          <Link className="mt-3 inline-flex items-center gap-1 text-sm font-semibold text-[#0f766e]" href="/jobs#data-quality">Datenqualität öffnen <ArrowRight size={14} /></Link>
        </div>
      </div>
    </section>
  </div>;
}

function errorText(error: unknown) {
  return error instanceof Error && error.message ? error.message : "Die Evaluation konnte nicht geladen werden.";
}

function SellStrategyPanel({ strategy }: { strategy?: SellStrategyResult }) {
  return (
    <section className="rounded border border-[#d8e1ea] bg-white p-5">
      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h2 className="text-base font-semibold">Verkaufsstrategie und Tranchen</h2>
          <div className="mt-1 text-sm text-[#687386]">
            {strategy?.description ?? "Strategie wird geladen."}
          </div>
        </div>
        <StatusChip tone={(strategy?.recommendation_percent ?? 0) > 0 ? "warning" : "good"}>
          {strategy?.label ?? "lädt"}
        </StatusChip>
      </div>
      <div className="mb-4 grid gap-3 md:grid-cols-3">
        <MetricTile label="Aktive Strategie" value={strategy?.label ?? "-"} detail="Gilt für die Bewertung dieser Aktie" />
        <MetricTile label="Strategie-Ziel" value={`${strategy?.recommendation_percent ?? 0}%`} detail="vor Abzug bereits verkaufter Tranchen" />
        <MetricTile
          label="Aktive Empfehlungen"
          value={`${strategy?.recommendations.filter((item) => item.active).length ?? 0}`}
          detail={`${strategy?.recommendations.length ?? 0} definierte Strategiebedingungen`}
        />
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        {(strategy?.recommendations ?? []).length === 0 && (
          <div className="rounded border border-[#e3e8ef] bg-[#f9fbfd] p-4 text-sm text-[#687386]">
            Keine Strategieempfehlungen vorhanden.
          </div>
        )}
        {(strategy?.recommendations ?? []).map((recommendation) => (
          <div
            key={recommendation.id}
            className={`rounded border p-3 ${recommendation.active ? "border-amber-300/45 bg-amber-300/10" : "border-[#e3e8ef] bg-[#f9fbfd]"}`}
          >
            <div className="mb-2 flex items-start justify-between gap-3">
              <div className="font-medium">{recommendation.label}</div>
              <StatusChip tone={recommendation.active ? "warning" : "neutral"}>
                {recommendation.active ? recommendation.id === "rs_line_tranche_3" ? "aktiv · Restverkauf" : `aktiv · ${recommendation.tranche_percent}%` : "inaktiv"}
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
    <div className="rounded border border-[#d8e1ea] bg-white px-3 py-2">
      <div className="text-xs uppercase text-[#687386]">{label}</div>
      <div className="mt-1 text-[#172033]">{value}</div>
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
    <section className="rounded border border-[#d8e1ea] bg-white p-5">
      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h2 className="text-base font-semibold">{title}</h2>
          <div className="mt-1 text-sm text-[#687386]">{description}</div>
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
        : "border-[#e3e8ef] bg-[#f9fbfd]";
  return (
    <div className={`rounded border p-3 ${border}`}>
      <div className="mb-2 flex items-start justify-between gap-3">
        <div>
          <div className="font-medium">{feature.label}</div>
          <div className="mt-1 text-xs text-[#687386]">{feature.threshold}</div>
        </div>
        <StatusChip tone={tone}>{feature.active ? "aktiv" : "inaktiv"}</StatusChip>
      </div>
      <div className="text-sm text-[#172033]">{feature.value || "-"}</div>
      <div className="mt-2 text-xs leading-5 text-[#687386]">{feature.detail}</div>
      <p className="mt-2 text-xs font-medium text-[#172033]">{feature.recommendation_effect}</p>
    </div>
  );
}

function toneForFeature(feature: SellRuleFeature): Tone {
  if (!feature.active) return "neutral";
  if (feature.severity === "killer") return "bad";
  if (feature.severity === "tranche" || feature.severity === "warning") return "warning";
  return "neutral";
}

function MetricTile({ label, value, detail }: { label: string; value: string; detail: string }) {
  return (
    <div className="rounded border border-[#d8e1ea] bg-[#f9fbfd] p-3">
      <div className="text-xs uppercase text-[#687386]">{label}</div>
      <div className="mt-2 text-xl font-semibold tabular-nums">{value}</div>
      <div className="mt-1 line-clamp-2 text-xs text-[#687386]">{detail}</div>
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
      color: colorForSignal(signal),
      code: "S",
      legendLabel: "Sell-Signal"
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
