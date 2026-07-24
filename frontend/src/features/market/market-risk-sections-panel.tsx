"use client";

import type { ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { ChevronDown, CircleAlert, CircleCheck, RotateCw } from "lucide-react";
import { LineChartCard } from "@/components/ui/line-chart-card";
import { StatusChip } from "@/components/ui/status-chip";
import { api } from "@/lib/api/client";
import type {
  MarketAmpel,
  MarketAmpelChartPoint,
  MarketAmpelDistanceTile,
  MarketAmpelWarningCheck,
  MarketIntermarketItem,
  MarketSectorRotationGroup,
  Tone
} from "@/lib/types/api";
import { labelForStatus, toneForStatus } from "./data-status";
import { MarketCategorySection } from "./market-category-section";
import { MARKET_REFETCH_INTERVAL_MS } from "./query-timing";

export function MarketRiskSectionsPanel({
  ticker = "^GSPC"
}: {
  ticker?: string;
}) {
  const ampelQuery = useQuery({
    queryKey: ["market-risk-sections-ampel", ticker],
    queryFn: () => api.marketAmpel(ticker, 90),
    placeholderData: (previous) => previous,
    staleTime: 60_000,
    refetchInterval: MARKET_REFETCH_INTERVAL_MS
  });
  const diagnosticsQuery = useQuery({
    queryKey: ["market-risk-sections-diagnostics", ticker],
    queryFn: () => api.marketDiagnostics(ticker),
    staleTime: 60_000,
    refetchInterval: MARKET_REFETCH_INTERVAL_MS
  });

  if (ampelQuery.isLoading || diagnosticsQuery.isLoading) {
    return <section className="rounded border border-[#2d333d] bg-[#171a20] p-5 text-sm text-[#a0a7b4]">Marktsignale laden...</section>;
  }

  if (ampelQuery.error || !ampelQuery.data) {
    return (
      <section className="rounded border border-rose-400/40 bg-rose-400/10 p-5 text-sm text-rose-100">
        Frühwarnzeichen und Warnzeichen sind aktuell nicht erreichbar.
      </section>
    );
  }

  const diagnostics = diagnosticsQuery.data;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-end gap-2">
        <button
          className="inline-flex h-8 items-center gap-2 rounded-[9px] border border-[#d8e1ea] bg-white px-3 text-xs font-semibold text-[#172033] transition hover:border-[#0f766e]"
          type="button"
          onClick={() => {
            void ampelQuery.refetch();
            void diagnosticsQuery.refetch();
          }}
        >
          <RotateCw
            size={15}
            className={ampelQuery.isFetching || diagnosticsQuery.isFetching ? "animate-spin text-emerald-300" : "text-[#a0a7b4]"}
          />
          Aktualisieren
        </button>
      </div>

      <RiskSection
        marker="01"
        tone="early"
        title="Frühwarnzeichen"
        description="Erste Hinweise auf nachlassende Marktqualität: Umkehrungen, defensive Rotation, schwache Schlussbereiche und MA-Abstände."
      >
        <EarlyWarnings
          data={ampelQuery.data}
          defensiveLead={diagnostics?.defensive_lead}
          defensiveSpread={diagnostics?.defensive_spread_pct}
          sectorRotation={diagnostics?.sector_rotation ?? []}
        />
      </RiskSection>

      <RiskSection
        marker="02"
        tone="warning"
        title="Warnzeichen"
        description="Kritischere Signale: Bruch wichtiger gleitender Durchschnitte, Distribution, Stau-Tage und Intermarket-Divergenzen."
      >
        <WarningSigns data={ampelQuery.data} intermarket={diagnostics?.intermarket ?? []} />
      </RiskSection>
    </div>
  );
}

export function MarketSentimentPositioningPanel({ ticker = "^GSPC" }: { ticker?: string }) {
  const volatilityQuery = useQuery({
    queryKey: ["market-sentiment-volatility"],
    queryFn: api.marketVolatility,
    staleTime: 60_000,
    refetchInterval: MARKET_REFETCH_INTERVAL_MS
  });
  const overviewQuery = useQuery({
    queryKey: ["market-sentiment-overview", ticker],
    queryFn: () => api.marketOverview(ticker),
    staleTime: 60_000,
    refetchInterval: MARKET_REFETCH_INTERVAL_MS
  });
  const volatility = volatilityQuery.data;
  const marginDebt = overviewQuery.data?.kpis.find((item) => item.label === "Margin Debt");
  const chartPoints =
    volatility?.points.map((point) => ({
      date: point.date,
      vix_close: point.vix_close,
      vix_sma10: point.vix_sma10,
      vix_ema21: point.vix_ema21,
      vxx_close: point.vxx_close,
      vxx_ema21: point.vxx_ema21
    })) ?? [];

  if (volatilityQuery.isLoading || overviewQuery.isLoading) {
    return <section className="rounded border border-[#2d333d] bg-[#171a20] p-5 text-sm text-[#a0a7b4]">Stimmungsindikatoren laden...</section>;
  }

  return (
    <section className="space-y-4">
      <div className="rounded border border-[#2d333d] bg-[#171a20] p-5">
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <StatusChip tone={overviewQuery.data ? toneForStatus(overviewQuery.data.data_status) : "neutral"}>
            {overviewQuery.data ? labelForStatus(overviewQuery.data.data_status) : "lädt"}
          </StatusChip>
        </div>
        <h3 className="text-xl font-semibold tracking-normal">Signalübersicht</h3>
        <p className="mt-2 max-w-4xl text-sm leading-6 text-[#a0a7b4]">
          VIX, VXX und Margin Debt als ergänzende Stimmungs- und Positionierungsindikatoren.
        </p>
      </div>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.2fr)_minmax(340px,0.8fr)]">
        <LineChartCard
          caption={volatility ? `${volatility.regime}, Stand ${volatility.as_of}` : "VIX/VXX-Regime aus gecachten Price-Bars"}
          error={volatilityQuery.error}
          isLoading={volatilityQuery.isLoading}
          points={chartPoints}
          series={[
            { key: "vix_close", label: "VIX", color: "#fb7185", formatter: (value) => value.toFixed(1) },
            { key: "vix_sma10", label: "VIX 10-SMA", color: "#7dd3fc", formatter: (value) => value.toFixed(1) },
            { key: "vix_ema21", label: "VIX 21-EMA", color: "#c084fc", formatter: (value) => value.toFixed(1) },
            { key: "vxx_close", label: "VXX", color: "#fbbf24", formatter: (value) => value.toFixed(1) },
            { key: "vxx_ema21", label: "VXX 21-EMA", color: "#22c55e", formatter: (value) => value.toFixed(1) }
          ]}
          statusLabel={volatility?.regime ?? "Nicht berechnet"}
          statusTone={volatility ? volatilityTone(volatility.regime) : "neutral"}
          title="VIX / VXX"
        />
        <div className="grid gap-3">
          {(volatility?.status_cards ?? [])
            .filter((item) => item.title !== "VIX Regime")
            .filter((item) => item.title.includes("VIX") || item.title.includes("VXX"))
            .map((item) => (
            <SignalCard key={item.title} title={item.title} value={item.status} detail={item.detail} tone={item.tone} />
          ))}
          <SignalCard
            title="Margin Debt"
            value={marginDebt?.value ?? "-"}
            detail={marginDebt?.detail ?? "Kein Margin-Debt-Snapshot im Cache."}
            tone={marginDebt?.tone ?? "neutral"}
          />
        </div>
      </div>
    </section>
  );
}

function EarlyWarnings({
  data,
  defensiveLead,
  defensiveSpread,
  sectorRotation
}: {
  data: MarketAmpel;
  defensiveLead?: boolean | null;
  defensiveSpread?: number | null;
  sectorRotation: MarketSectorRotationGroup[];
}) {
  const intraday = findCheck(data.warning_checks, "Intraday-Umkehrungen");
  const closingRange = findCheck(data.warning_checks, "Closing Range");
  const upVolume = findCheck(data.warning_checks, "Volumen an Aufwärtstagen");
  const recovery = findCheck(data.warning_checks, "Erholungsquote");
  return (
    <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
      <CheckSignalCard title="Intraday-Umkehrungen" check={intraday} fallback="Keine Intraday-Umkehrdaten im Cache." />
      <SignalCard
        title="Rotation in defensive Sektoren"
        value={defensiveLead ? "Defensiv führt" : defensiveLead === false ? "Offensiv bestätigt" : "n/a"}
        detail={`Spread: ${formatPct(defensiveSpread)}`}
        tone={defensiveLead ? "warning" : defensiveLead === false ? "good" : "neutral"}
        comment={sectorRotationComment(sectorRotation)}
      />
      <CheckSignalCard title="Abschlüsse am Tagestief" check={closingRange} fallback="Keine Closing-Range-Daten im Cache." />
      <MovingAverageDistanceCard tiles={data.distance_tiles} />
      <CheckSignalCard title="Volumen an Aufwärtstagen" check={upVolume} fallback="Keine Up-Volume-Daten im Cache." />
      <CheckSignalCard title="Erholungsquote" check={recovery} fallback="Keine Erholungsquoten-Prüfung im Cache." />
    </div>
  );
}

function WarningSigns({ data, intermarket }: { data: MarketAmpel; intermarket: MarketIntermarketItem[] }) {
  const latest = data.chart_points[data.chart_points.length - 1];
  const movingAverageChecks = data.warning_checks.filter((check) =>
    ["Kurs über 200-SMA", "Kurs über 50-SMA", "Kurs unter 21-EMA"].includes(check.label)
  );
  const distribution = findCheck(data.warning_checks, "Distributionstage");
  const stalls = findCheck(data.warning_checks, "Stau-Tage");
  const lossGain = findCheck(data.warning_checks, "Verlusttage/Gewinntage");
  return (
    <div className="grid items-start gap-3 md:grid-cols-2 xl:grid-cols-4">
      <MovingAverageBreaksCard checks={movingAverageChecks} latest={latest} />
      <CheckSignalCard title="Verstärkte Distribution im Index" check={distribution} fallback="Keine Distributionstage im Cache." />
      <CheckSignalCard title="Stau-Tage" check={stalls} fallback="Keine Stau-Tage im Cache." />
      <IntermarketDirectionCard items={intermarket} />
      <CheckSignalCard title="Verlusttage/Gewinntage" check={lossGain} fallback="Keine Verlusttage/Gewinntage-Prüfung im Cache." />
    </div>
  );
}

function RiskSection({
  children,
  description,
  marker,
  title,
  tone
}: {
  children: ReactNode;
  description: string;
  marker: string;
  title: string;
  tone: "early" | "warning";
}) {
  return (
    <MarketCategorySection description={description} marker={marker} title={title} tone={tone}>
      {children}
    </MarketCategorySection>
  );
}

function CheckSignalCard({ check, fallback, title }: { check?: MarketAmpelWarningCheck; fallback: string; title: string }) {
  if (!check) {
    return <SignalCard title={title} value="n/a" detail={fallback} tone="neutral" />;
  }
  return (
    <SignalCard
      title={title}
      value={check.active_warning ? "Aktiv" : "OK"}
      detail={check.detail}
      tone={check.active_warning ? check.tone : "good"}
      passed={check.passed}
    />
  );
}

function MovingAverageDistanceCard({ tiles }: { tiles: MarketAmpelDistanceTile[] }) {
  return (
    <div className="rounded-[12px] border border-[#e3e8ef] bg-white p-3.5 shadow-[0_4px_14px_rgba(15,23,42,0.04)]">
      <div className="mb-2.5 flex items-start justify-between gap-3">
        <div>
          <div className="break-words text-xs font-semibold uppercase tracking-normal text-[#a0a7b4] [overflow-wrap:anywhere]">
            Abstand Index zu gleitenden Durchschnitten
          </div>
          <div className="mt-1.5 text-xs leading-5 text-[#4b5565]">21-EMA, 10-SMA, 50-SMA und 200-SMA.</div>
        </div>
        <StatusChip tone={worstTone(tiles.map((tile) => tile.tone))}>Abstand</StatusChip>
      </div>
      <div className="grid gap-2 sm:grid-cols-2">
        {tiles.length ? tiles.map((tile) => (
          <div key={tile.label} className="rounded border border-[#242a33] bg-[#111419] px-3 py-2">
            <div className="text-xs text-[#77808f]">{tile.label}</div>
            <div className={clsx("mt-1 text-sm font-semibold", toneText(tile.tone))}>{tile.value}</div>
            <div className="text-xs text-[#a0a7b4]">{tile.indicator}</div>
          </div>
        )) : <div className="text-sm text-[#a0a7b4]">Keine MA-Abstände im Cache.</div>}
      </div>
    </div>
  );
}

function MovingAverageBreaksCard({
  checks,
  latest
}: {
  checks: MarketAmpelWarningCheck[];
  latest?: MarketAmpelChartPoint;
}) {
  const active = checks.filter((check) => check.active_warning);
  const trendChecks = latest ? movingAverageTrendChecks(latest) : [];
  return (
    <div
      className={clsx(
        "self-start rounded-[12px] border bg-white p-3.5 shadow-[0_4px_14px_rgba(15,23,42,0.04)] md:col-span-2 xl:col-span-2",
        cardClass(active.length ? "warning" : "good")
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="break-words text-xs font-semibold uppercase tracking-[0.04em] text-[#687386] [overflow-wrap:anywhere]">
            Bruch wichtiger gleitender Durchschnitte
          </div>
          <div className="mt-1 text-[11px] leading-4 text-[#687386]">
            {checks.length} Bruchsignale · {trendChecks.length} ergänzende Trendprüfungen
          </div>
        </div>
        <StatusChip tone={active.length ? "warning" : "good"}>{active.length ? "Warnung" : "OK"}</StatusChip>
      </div>

      <div className="mt-3 grid gap-2 sm:grid-cols-3">
        {checks.length ? checks.map((check) => (
          <div
            key={check.label}
            className={clsx(
              "min-w-0 rounded-[9px] border px-2.5 py-2",
              check.active_warning
                ? "border-[#f0d18b] bg-[#fff8e7]"
                : "border-[#cce5da] bg-[#f2faf6]"
            )}
          >
            <div className="flex items-center gap-1.5">
              {check.active_warning ? (
                <CircleAlert className="shrink-0 text-[#b7791f]" size={14} />
              ) : (
                <CircleCheck className="shrink-0 text-[#138a57]" size={14} />
              )}
              <span className="truncate text-[11px] font-semibold text-[#172033]" title={check.label}>
                {check.label}
              </span>
            </div>
            <div className="mt-1 line-clamp-2 text-[11px] leading-4 text-[#687386]">{check.detail}</div>
          </div>
        )) : (
          <div className="text-xs text-[#687386]">Keine MA-Bruchdaten im Cache.</div>
        )}
      </div>

      {trendChecks.length > 0 && (
        <details className="group mt-2.5 rounded-[9px] border border-[#e3e8ef] bg-white/70">
          <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-3 py-2 text-xs font-semibold text-[#475569] transition hover:bg-white [&::-webkit-details-marker]:hidden">
            <span>Trendprüfung im Detail</span>
            <span className="flex items-center gap-1.5 text-[11px] font-medium text-[#687386]">
              {trendChecks.filter((check) => check.passed).length}/{trendChecks.length} erfüllt
              <ChevronDown className="transition-transform group-open:rotate-180" size={14} />
            </span>
          </summary>
          <div className="grid gap-1.5 border-t border-[#e3e8ef] p-2.5 sm:grid-cols-2 xl:grid-cols-3">
            {trendChecks.map((check) => (
              <div key={check.label} className="flex min-w-0 items-start gap-1.5 rounded-[8px] bg-[#f8fafc] px-2 py-1.5 text-[11px] leading-4 text-[#475569]">
                {check.passed ? (
                  <CircleCheck className="mt-0.5 shrink-0 text-[#138a57]" size={13} />
                ) : (
                  <CircleAlert className="mt-0.5 shrink-0 text-[#b7791f]" size={13} />
                )}
                <span className="min-w-0">
                  <span className="font-medium text-[#172033]">{check.label}</span>
                  <span className="text-[#687386]"> · {check.detail}</span>
                </span>
              </div>
            ))}
          </div>
        </details>
      )}
    </div>
  );
}

function movingAverageTrendChecks(point: MarketAmpelChartPoint) {
  return [
    maCheck("Schluss über 21-EMA", point.close, point.ema21),
    maCheck("Tief über 21-EMA", point.low, point.ema21),
    booleanCheck("21-EMA gehalten", point.ema21_held, point.ema21 ? "Schlusskurs darüber" : "n/a", "Darunter"),
    heldCheck("3T Tief > 21-EMA", point.consec_low_above_21),
    maCheck("Schluss über 50-SMA", point.close, point.sma50),
    maCheck("Tief über 50-SMA", point.low, point.sma50),
    booleanCheck("50-SMA gehalten", point.sma50_held, point.sma50 ? "Schlusskurs darüber" : "n/a", "Darunter"),
    heldCheck("3T Tief > 50-SMA", point.consec_low_above_50),
    maCheck("Schluss über 200-SMA", point.close, point.sma200),
    maCheck("Tief über 200-SMA", point.low, point.sma200),
    booleanCheck("200-SMA gehalten", point.sma200_held, point.sma200 ? "Schlusskurs darüber" : "n/a", "Darunter"),
    heldCheck("3T Tief > 200-SMA", point.consec_low_above_200)
  ];
}

function maCheck(label: string, value?: number | null, average?: number | null) {
  const hasData = value !== null && value !== undefined && average !== null && average !== undefined;
  return {
    label,
    passed: Boolean(hasData && value > average),
    detail: hasData ? `${formatNumber(value)} vs ${formatNumber(average)}` : "n/a"
  };
}

function booleanCheck(label: string, passed: boolean, okDetail: string, failDetail: string) {
  return {
    label,
    passed,
    detail: passed ? okDetail : failDetail
  };
}

function heldCheck(label: string, count: number) {
  return {
    label,
    passed: count >= 3,
    detail: `${count} Tage`
  };
}

function IntermarketDirectionCard({ items }: { items: MarketIntermarketItem[] }) {
  const valid = items.filter((item) => item.day_pct !== null && item.day_pct !== undefined);
  const positive = valid.filter((item) => (item.day_pct ?? 0) > 0).length;
  const negative = valid.filter((item) => (item.day_pct ?? 0) < 0).length;
  const mixed = positive > 0 && negative > 0;
  const value = !valid.length ? "n/a" : mixed ? "Divergenz" : "Gleichlauf";
  return (
    <div className={clsx("rounded-[12px] border bg-white p-3.5 shadow-[0_4px_14px_rgba(15,23,42,0.04)]", cardClass(!valid.length ? "neutral" : mixed ? "warning" : "good"))}>
      <div className="mb-2.5 flex items-start justify-between gap-3">
        <div>
          <div className="break-words text-xs font-semibold uppercase tracking-normal text-[#a0a7b4] [overflow-wrap:anywhere]">
            Intermarket-Divergenzen
          </div>
          <div className={clsx("mt-1.5 text-xl font-semibold", toneText(!valid.length ? "neutral" : mixed ? "warning" : "good"))}>{value}</div>
        </div>
        <StatusChip tone={!valid.length ? "neutral" : mixed ? "warning" : "good"}>{mixed ? "gemischt" : "Richtung"}</StatusChip>
      </div>
      <p className="text-xs leading-5 text-[#d8dde6]">
        Prüft, ob S&P 500, Nasdaq, Dow Jones und Russell 2000 am Tag in die gleiche Richtung laufen.
      </p>
      <div className="mt-3 grid gap-2 sm:grid-cols-2">
        {items.map((item) => (
          <div key={item.ticker} className="rounded border border-[#242a33] bg-[#111419] px-3 py-2 text-xs">
            <div className="font-medium text-[#d8dde6]">{item.name}</div>
            <div className={pctClass(item.day_pct)}>{formatPct(item.day_pct)}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

function SignalCard({
  comment,
  detail,
  passed,
  title,
  tone,
  value
}: {
  comment?: string;
  detail: string;
  passed?: boolean;
  title: string;
  tone: Tone;
  value: string;
}) {
  return (
    <div className={clsx("rounded-[12px] border bg-white p-3.5 shadow-[0_4px_14px_rgba(15,23,42,0.04)]", cardClass(tone))}>
      <div className="mb-2.5 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="break-words text-xs font-semibold uppercase tracking-normal text-[#a0a7b4] [overflow-wrap:anywhere]">{title}</div>
          <div className={clsx("mt-1.5 break-words text-xl font-semibold leading-tight", toneText(tone))}>{value}</div>
        </div>
        <StatusChip tone={tone}>{passed === false ? "aktiv" : toneLabel(tone)}</StatusChip>
      </div>
      <div className="text-xs leading-5 text-[#d8dde6]">{detail}</div>
      {comment && <div className="mt-1.5 text-[11px] leading-4 text-[#a0a7b4]">{comment}</div>}
    </div>
  );
}

function findCheck(checks: MarketAmpelWarningCheck[], needle: string) {
  return checks.find((check) => check.label.includes(needle));
}

function sectorRotationComment(groups: MarketSectorRotationGroup[]) {
  if (!groups.length) return "Keine Sektor-ETF-Daten im Cache.";
  return groups
    .map((group) => `${group.label}: ${formatPct(group.avg_return_10d_pct)}`)
    .join(" · ");
}

function worstTone(tones: Tone[]): Tone {
  if (tones.includes("bad")) return "bad";
  if (tones.includes("warning")) return "warning";
  if (tones.includes("good")) return "good";
  return "neutral";
}

function volatilityTone(regime: string): Tone {
  if (regime === "Risk Off bestätigt") return "bad";
  if (regime.includes("Stress") || regime.includes("Fragile") || regime.includes("Schock")) return "warning";
  if (regime.includes("Risk On")) return "good";
  return "neutral";
}

function cardClass(tone: Tone) {
  if (tone === "good") return "border-emerald-300/35 bg-emerald-300/10";
  if (tone === "bad") return "border-rose-300/35 bg-rose-300/10";
  if (tone === "warning") return "border-amber-300/35 bg-amber-300/10";
  return "border-[#2d333d]";
}

function toneText(tone: Tone) {
  if (tone === "good") return "text-emerald-200";
  if (tone === "bad") return "text-rose-200";
  if (tone === "warning") return "text-amber-100";
  return "text-[#c9d0da]";
}

function toneLabel(tone: Tone) {
  if (tone === "good") return "OK";
  if (tone === "bad") return "kritisch";
  if (tone === "warning") return "Warnung";
  return "neutral";
}

function pctClass(value?: number | null) {
  if (value === null || value === undefined) return "text-[#77808f]";
  return value >= 0 ? "text-emerald-200" : "text-rose-200";
}

function formatPct(value?: number | null) {
  if (value === null || value === undefined) return "-";
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
}

function formatNumber(value?: number | null) {
  if (value === null || value === undefined) return "-";
  return new Intl.NumberFormat("de-DE", { maximumFractionDigits: 2 }).format(value);
}
