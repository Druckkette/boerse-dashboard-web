"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { ArrowDown, ArrowUp, CircleDot, RotateCw, ShieldAlert } from "lucide-react";
import { LineChartCard } from "@/components/ui/line-chart-card";
import { StatusChip } from "@/components/ui/status-chip";
import { api } from "@/lib/api/client";
import type { MarketAmpel, MarketAmpelChangeCard, MarketAmpelDistanceTile, MarketAmpelLight, Tone } from "@/lib/types/api";
import { labelForStatus, toneForStatus } from "./data-status";
import { MARKET_REFETCH_INTERVAL_MS } from "./query-timing";

const defaultIndexes = [
  { ticker: "^GSPC", label: "S&P500" },
  { ticker: "^IXIC", label: "NASDAQ" },
  { ticker: "^RUT", label: "Russell 2000" }
] as const;
type MarketIndexOption = (typeof defaultIndexes)[number];
type MarketIndexTicker = MarketIndexOption["ticker"];

const dayOptions = [60, 90, 130, 200] as const;

export function MarketAmpelPanel({
  indexes = defaultIndexes,
  onTickerChange,
  ticker = "^GSPC"
}: {
  indexes?: readonly MarketIndexOption[];
  onTickerChange?: (ticker: MarketIndexTicker) => void;
  ticker?: MarketIndexTicker;
}) {
  const [days, setDays] = useState<(typeof dayOptions)[number]>(90);
  const query = useQuery({
    queryKey: ["market-ampel", ticker, days],
    queryFn: () => api.marketAmpel(ticker, days),
    placeholderData: (previous) => previous,
    staleTime: 60_000,
    refetchInterval: MARKET_REFETCH_INTERVAL_MS
  });

  if (query.isLoading) {
    return <section className="rounded-[24px] border border-[#e3e8ef] bg-white p-5 text-sm text-[#687386] shadow-[0_10px_28px_rgba(15,23,42,0.06)]">Marktampel lädt...</section>;
  }

  if (query.error || !query.data) {
    return (
      <section className="rounded-[24px] border border-[#f0b9b5] bg-[#fff0ef] p-5 text-sm font-medium text-[#c2413b] shadow-[0_10px_28px_rgba(15,23,42,0.06)]">
        Marktampel ist aktuell nicht erreichbar.
      </section>
    );
  }

  const data = query.data;
  const heroReasons = data.hero.reasons.filter((reason) => reason.startsWith("Trendwende-Ampel"));
  const todayCard = data.change_cards.find((card) => card.title.startsWith("Heute "));
  const changeCards = data.change_cards.filter(
    (card) =>
      !card.title.startsWith("Heute ") &&
      !["Distribution", "EW-Breite", "Volatilität", "Trendwende-Ampel"].includes(card.title)
  );
  const chartPoints = data.chart_points.map((point) => ({
    date: point.date,
    open: point.open,
    high: point.high,
    low: point.low,
    close: point.close,
    volume: point.volume,
    ema21: point.ema21,
    sma10: point.sma10,
    sma50: point.sma50,
    sma200: point.sma200,
    vol_sma50: point.vol_sma50,
    dist_52w_pct: point.dist_52w_pct
  }));

  return (
    <section className="space-y-4">
      <div
        className={clsx(
          "relative overflow-hidden rounded-[32px] border p-5 shadow-[0_24px_60px_rgba(15,23,42,0.09)] sm:p-6",
          heroToneClasses(data.hero.tone)
        )}
      >
        <div className={clsx("absolute inset-y-6 left-0 w-1 rounded-r-full", cycleAccentClass(data.hero.tone))} />
        <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(360px,0.48fr)]">
          <div className="min-w-0">
            <div className="mb-4 flex flex-wrap items-center gap-2">
              <StatusChip tone={data.hero.tone}>{data.hero.mode}</StatusChip>
              <StatusChip tone={data.phase_info.tone}>{data.phase_info.label}</StatusChip>
              <StatusChip tone={toneForStatus(data.data_status)}>{labelForStatus(data.data_status)}</StatusChip>
            </div>
            <div className="flex min-w-0 items-start gap-4">
              <StatusEmblem tone={data.hero.tone} />
              <div className="min-w-0">
                <div className="text-xs font-semibold uppercase tracking-[0.18em] text-[#64748b]">Marktampel</div>
                <h1 className={clsx("mt-2 break-words text-4xl font-semibold leading-tight tracking-normal md:text-5xl", toneText(data.hero.tone))}>
                  {data.hero.mode}
                </h1>
              </div>
            </div>

            <div className="mt-5 grid gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(280px,0.62fr)]">
              <div className="rounded-[24px] border border-white/75 bg-white/72 p-4 shadow-[0_10px_26px_rgba(15,23,42,0.05)]">
                <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.16em] text-[#64748b]">
                  <ShieldAlert size={14} />
                  Handlung
                </div>
                <p className="max-w-3xl text-sm font-semibold leading-7 text-[#0f172a]">{data.hero.action}</p>
              </div>
              <TrendReasonCard reason={heroReasons[0]} tone={data.phase_info.tone} />
            </div>
          </div>

          <div className="rounded-[28px] border border-white/75 bg-white/72 p-4 shadow-[0_16px_38px_rgba(15,23,42,0.06)] backdrop-blur">
            <div className="space-y-4">
              <div>
                <div className="mb-2 text-xs font-semibold uppercase tracking-[0.16em] text-[#64748b]">Index</div>
                <div className="grid grid-cols-3 gap-2">
                  {indexes.map((item) => (
                    <button
                      key={item.ticker}
                      aria-pressed={ticker === item.ticker}
                      className={clsx(
                        "min-h-[58px] rounded-2xl border px-3 py-2 text-left text-sm font-semibold transition duration-200 focus:outline-none focus:ring-2 focus:ring-[#0f766e]/30",
                        ticker === item.ticker
                          ? "border-[#0f766e] bg-[#0f766e] text-white shadow-[0_12px_28px_rgba(15,118,110,0.20)]"
                          : "border-[#e2e8f0] bg-[#f8fafc] text-[#0f172a] hover:-translate-y-0.5 hover:border-[#cbd5e1] hover:bg-white hover:shadow-[0_10px_24px_rgba(15,23,42,0.06)]"
                      )}
                      type="button"
                      onClick={() => onTickerChange?.(item.ticker)}
                    >
                      <span className="block leading-5">{item.label}</span>
                      <span className={clsx("mt-0.5 block text-xs font-medium", ticker === item.ticker ? "text-white/75" : "text-[#64748b]")}>
                        {item.ticker}
                      </span>
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <div className="mb-2 text-xs font-semibold uppercase tracking-[0.16em] text-[#64748b]">Zeitraum</div>
                <div className="flex flex-wrap gap-2">
                  {dayOptions.map((option) => (
                    <button
                      key={option}
                      aria-pressed={days === option}
                      className={clsx(
                        "rounded-full border px-3.5 py-2 text-sm font-semibold transition duration-200 focus:outline-none focus:ring-2 focus:ring-[#2563eb]/25",
                        days === option
                          ? "border-[#2563eb] bg-[#eff6ff] text-[#1d4ed8] shadow-[0_10px_22px_rgba(37,99,235,0.10)]"
                          : "border-[#e2e8f0] bg-[#f8fafc] text-[#64748b] hover:-translate-y-0.5 hover:border-[#cbd5e1] hover:bg-white"
                      )}
                      type="button"
                      onClick={() => setDays(option)}
                    >
                      {option}T
                    </button>
                  ))}
                  <button
                    aria-label="Marktampel aktualisieren"
                    className="inline-flex items-center gap-2 rounded-full border border-[#e2e8f0] bg-white px-3.5 py-2 text-sm font-semibold text-[#0f172a] shadow-sm transition duration-200 hover:-translate-y-0.5 hover:border-[#0f766e] hover:shadow-[0_10px_22px_rgba(15,23,42,0.07)] focus:outline-none focus:ring-2 focus:ring-[#0f766e]/25"
                    type="button"
                    onClick={() => query.refetch()}
                  >
                    <RotateCw size={15} className={query.isFetching ? "animate-spin text-[#0f766e]" : "text-[#64748b]"} />
                    Aktualisieren
                  </button>
                </div>
              </div>

              {todayCard ? <TodayIndexCard card={todayCard} /> : null}
            </div>
          </div>
        </div>
      </div>

      {changeCards.length > 0 ? (
        <div className="grid gap-3 sm:grid-cols-2">
          {changeCards.map((card) => (
            <ChangeCard key={card.title} card={card} />
          ))}
        </div>
      ) : null}

      <div>
        <TrafficLightPanel data={data} />
      </div>

      <LineChartCard
        title={`${data.name} Trendwende-Ampel`}
        caption={`${data.phase_info.reason} Stand ${data.as_of}. ${data.message}`}
        hideTextHeader
        points={chartPoints}
        chartMode="candlestick"
        volumeKey="volume"
        markers={data.chart_markers}
        showHorizontalGrid={false}
        levels={[
          ...(data.cycle.floor_mark ? [{ key: "floor", label: "Bodenmarke", value: data.cycle.floor_mark, color: "#f87171" }] : []),
          ...(data.cycle.startschuss_low
            ? [{ key: "startschuss", label: "Startschuss-Tief", value: data.cycle.startschuss_low, color: "#fbbf24" }]
            : [])
        ]}
        series={[
          { key: "ema21", label: "21-EMA", color: "#38bdf8" },
          { key: "sma50", label: "50-SMA", color: "#fb923c" },
          { key: "sma200", label: "200-SMA", color: "#a78bfa" }
        ]}
        statusLabel={data.phase_info.label}
        statusTone={data.phase_info.tone}
      />
    </section>
  );
}

function TrendReasonCard({ reason, tone }: { reason?: string; tone: Tone }) {
  if (!reason) return null;
  const parsed = parseTrendReason(reason);
  return (
    <div className={clsx("relative overflow-hidden rounded-[24px] border bg-white/72 p-4 shadow-[0_10px_26px_rgba(15,23,42,0.05)]", phasePillClass(tone))}>
      <div className={clsx("absolute inset-y-4 left-0 w-1 rounded-r-full", cycleAccentClass(tone))} />
      <div className="text-xs font-semibold uppercase tracking-[0.16em] text-[#64748b]">{parsed.label}</div>
      <div className={clsx("mt-2 text-lg font-semibold leading-6", toneText(tone))}>{parsed.value}</div>
      {parsed.detail ? <div className="mt-1 text-sm leading-6 text-[#475569]">{parsed.detail}</div> : null}
    </div>
  );
}

function TodayIndexCard({ card }: { card: MarketAmpelChangeCard }) {
  return (
    <div className="rounded-[24px] border border-[#e2e8f0] bg-white p-4 shadow-[0_12px_30px_rgba(15,23,42,0.06)]">
      <div className="mb-3 flex items-start justify-between gap-3">
        <div>
          <div className="text-xs font-semibold uppercase tracking-[0.16em] text-[#64748b]">{card.title}</div>
          <div className="mt-2 flex items-center gap-2 text-3xl font-semibold tracking-normal text-[#0f172a]">
            {card.arrow === "up" && <ArrowUp className="text-[#059669]" size={21} />}
            {card.arrow === "down" && <ArrowDown className="text-[#dc2626]" size={21} />}
            <span className={toneText(card.tone)}>{card.value}</span>
          </div>
        </div>
        <span className={clsx("rounded-full border px-2.5 py-1 text-xs font-semibold", phasePillClass(card.tone))}>
          {card.quality ?? card.tone}
        </span>
      </div>
      <div className="space-y-1 text-sm leading-6 text-[#475569]">
        <div>{card.detail}</div>
        {card.detail2 ? <div>{card.detail2}</div> : null}
        {card.detail3 ? <div>{card.detail3}</div> : null}
      </div>
    </div>
  );
}

function parseTrendReason(reason: string) {
  const [, rawContent] = reason.split(/:\s(.+)/);
  const content = rawContent || reason;
  const [value, ...rest] = content.split("·").map((part) => part.trim()).filter(Boolean);
  return {
    label: "Trendwende-Ampel",
    value: value || content,
    detail: rest.join(" · "),
  };
}

function TrafficLightPanel({ data }: { data: MarketAmpel }) {
  return (
    <div className="overflow-hidden rounded-[28px] border border-[#e2e8f0] bg-white p-5 shadow-[0_18px_42px_rgba(15,23,42,0.07)] sm:p-6">
      <div className="mb-5 flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <div className="text-xs font-semibold uppercase tracking-[0.16em] text-[#64748b]">Trendwende-Ampel</div>
          <h2 className="mt-1 text-xl font-semibold tracking-normal text-[#0f172a]">Marktphase</h2>
        </div>
        <StatusChip tone={data.phase_info.tone}>{data.phase_info.label}</StatusChip>
      </div>

      <PhaseStepper lights={data.lights} />

      <div className={clsx("mt-5 rounded-[28px] border p-5 shadow-[0_20px_52px_rgba(15,23,42,0.08)] sm:p-6", phaseCardClass(data.phase_info.tone))}>
        <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
          <div className="flex min-w-0 items-start gap-4">
            <StatusEmblem tone={data.phase_info.tone} />
            <div className="min-w-0">
              <div className="text-xs font-semibold uppercase tracking-[0.16em] text-[#64748b]">Aktuelle Ampelphase</div>
              <h3
                className={clsx(
                  "mt-2 break-words text-3xl font-semibold leading-tight tracking-normal sm:text-4xl",
                  toneText(data.phase_info.tone)
                )}
              >
                {data.phase_info.label}
              </h3>
            </div>
          </div>
          <span
            className={clsx(
              "inline-flex w-fit shrink-0 items-center rounded-full border px-3 py-1 text-xs font-semibold shadow-sm",
              phasePillClass(data.phase_info.tone)
            )}
          >
            {data.phase_info.label}
          </span>
        </div>

        <div className="mt-6 grid gap-4 lg:grid-cols-[minmax(0,0.92fr)_minmax(0,1.08fr)]">
          <InfoBlock title="Definition" text={data.phase_info.reason} />
          <InfoBlock title="Handlung" text={data.phase_info.action} emphasis />
        </div>

        <div className="mt-6 border-t border-white/65 pt-5">
          <div className="mb-3 text-xs font-semibold uppercase tracking-[0.16em] text-[#64748b]">Letzter Startschuss und Zykluswerte</div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <CycleMetric
              label="Ankertag"
              value={data.cycle.anchor_date ?? "-"}
              tone="neutral"
              freshness={cycleFreshness(data.cycle.anchor_date, data.cycle.anchor_current)}
            />
            <CycleMetric
              label="Bodenmarke"
              value={formatValueWithDistance(data.cycle.floor_mark, data.cycle.floor_distance_pct)}
              tone={distanceTone(data.cycle.floor_distance_pct)}
              freshness={cycleFreshness(data.cycle.floor_mark, data.cycle.floor_current)}
            />
            <CycleMetric
              label="Startschuss-Tief"
              value={formatValueWithDistance(data.cycle.startschuss_low, data.cycle.startschuss_distance_pct)}
              tone={distanceTone(data.cycle.startschuss_distance_pct)}
              freshness={cycleFreshness(data.cycle.startschuss_low, data.cycle.startschuss_current)}
            />
            <CycleMetric
              label="MA-Ordnung"
              value={data.cycle.ma_order ? "Korrekt" : "Gestört"}
              tone={data.cycle.ma_order ? "good" : "bad"}
            />
          </div>
          {data.cycle.diagnostics.length > 0 ? (
            <div className="mt-3 text-xs leading-5 text-[#64748b]">{data.cycle.diagnostics.join(" · ")}</div>
          ) : null}
        </div>
      </div>

      <RuleDefinitions lights={data.lights} />
      <MovingAverageDistanceSummary tiles={data.distance_tiles} />
    </div>
  );
}

function InfoBlock({ emphasis = false, text, title }: { emphasis?: boolean; text: string; title: string }) {
  return (
    <div
      className={clsx(
        "min-w-0 rounded-[22px] border bg-white/72 p-4 shadow-[0_8px_22px_rgba(15,23,42,0.04)]",
        emphasis ? "border-[#cbd5e1]" : "border-white/70"
      )}
    >
      <div className="text-xs font-semibold uppercase tracking-[0.16em] text-[#64748b]">{title}</div>
      <p className={clsx("mt-2 text-sm leading-7", emphasis ? "font-semibold text-[#0f172a]" : "text-[#475569]")}>{text}</p>
    </div>
  );
}

function PhaseStepper({ lights }: { lights: MarketAmpelLight[] }) {
  return (
    <div className="relative grid grid-cols-2 gap-3 md:grid-cols-4">
      <div className="pointer-events-none absolute left-10 right-10 top-[31px] hidden h-px bg-[#e2e8f0] md:block" />
      {lights.map((light) => (
        <PhaseStep key={light.key} light={light} />
      ))}
    </div>
  );
}

function PhaseStep({ light }: { light: MarketAmpelLight }) {
  return (
    <div
      aria-current={light.active ? "step" : undefined}
      className={clsx(
        "relative z-10 min-w-0 rounded-[22px] border p-3 transition duration-200",
        light.active
          ? clsx("scale-[1.01] shadow-[0_14px_34px_rgba(15,23,42,0.10)]", phaseStepClass(light.tone))
          : "border-[#e2e8f0] bg-[#f8fafc] text-[#64748b]"
      )}
    >
      <div className="flex items-center gap-3">
        <span
          className={clsx(
            "grid size-9 shrink-0 place-items-center rounded-full border transition duration-200",
            light.active ? activeLightClass(light.tone, light.key) : "border-[#cbd5e1] bg-white text-[#94a3b8]"
          )}
        >
          <CircleDot size={18} />
        </span>
        <span
          className={clsx(
            "min-w-0 break-words text-xs font-semibold uppercase leading-5 tracking-[0.08em] [overflow-wrap:anywhere]",
            light.active ? toneText(light.tone) : "text-[#64748b]"
          )}
        >
          {light.key === "aufwaertstrend" ? "AUFWÄRTSTREND" : light.label}
        </span>
      </div>
    </div>
  );
}

function StatusEmblem({ tone }: { tone: Tone }) {
  return (
    <span
      className={clsx(
        "grid size-12 shrink-0 place-items-center rounded-2xl border shadow-[0_12px_28px_rgba(15,23,42,0.08)]",
        activeLightClass(tone)
      )}
    >
      <CircleDot size={24} />
    </span>
  );
}

function RuleDefinitions({ lights }: { lights: MarketAmpelLight[] }) {
  return (
    <details className="group mt-4 overflow-hidden rounded-[20px] border border-[#e3e8ef] bg-[#f9fbfd]">
      <summary className="flex cursor-pointer list-none items-start justify-between gap-4 px-4 py-3">
        <span>
          <span className="block text-base font-semibold text-[#172033]">Regeldefinitionen</span>
          <span className="mt-1 block text-sm leading-6 text-[#687386]">Ampelphasen aus der Streamlit-Logik.</span>
        </span>
        <span className="mt-1 shrink-0 rounded-full border border-[#d8e1ea] bg-white px-3 py-1 text-xs font-semibold text-[#687386] group-open:text-[#0f766e]">
          Details
        </span>
      </summary>
      <div className="grid gap-3 border-t border-[#e3e8ef] p-4 md:grid-cols-2">
        {lights.map((light) => (
          <div key={light.key} className={clsx("rounded-2xl border bg-white p-4", light.active ? tileBorder(light.tone) : "border-[#e3e8ef]")}>
            <div className="mb-2 flex items-center gap-2">
              <span className={clsx("size-2 rounded-full", dotBg(light.tone))} />
              <div className={clsx("text-sm font-semibold", light.active ? toneText(light.tone) : "text-[#172033]")}>
                {light.label}
              </div>
              {light.active && <StatusChip tone={light.tone}>aktiv</StatusChip>}
            </div>
            <p className="text-sm leading-6 text-[#687386]">{light.rule}</p>
          </div>
        ))}
      </div>
    </details>
  );
}

function MovingAverageDistanceSummary({ tiles }: { tiles: MarketAmpelDistanceTile[] }) {
  if (!tiles.length) return null;
  return (
    <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      {tiles.map((tile) => (
        <div key={tile.label} className={clsx("rounded-2xl border bg-white p-4", tileBorder(tile.tone))}>
          <div className="text-xs font-semibold uppercase tracking-[0.12em] text-[#687386]">{tile.label}</div>
          <div className={clsx("mt-2 text-xl font-semibold tabular-nums", toneText(tile.tone))}>{tile.value}</div>
          <div className="mt-1 text-sm text-[#4b5565]">{tile.indicator}</div>
          <div className="mt-1 text-xs leading-5 text-[#687386]">{tile.detail}</div>
        </div>
      ))}
    </div>
  );
}

function ChangeCard({ card }: { card: MarketAmpelChangeCard }) {
  return (
    <div className="rounded-[24px] border border-[#e3e8ef] bg-white p-5 shadow-[0_10px_28px_rgba(15,23,42,0.06)]">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div className="text-sm font-medium text-[#687386]">{card.title}</div>
        <StatusChip tone={card.tone}>{card.quality ?? card.tone}</StatusChip>
      </div>
      <div className="flex items-center gap-2 text-2xl font-semibold tracking-normal text-[#172033]">
        {card.arrow === "up" && <ArrowUp className="text-[#138a57]" size={20} />}
        {card.arrow === "down" && <ArrowDown className="text-[#c2413b]" size={20} />}
        {card.value}
      </div>
      <div className="mt-2 text-sm leading-6 text-[#687386]">{card.detail}</div>
      {card.detail2 && <div className="mt-1 text-xs text-[#687386]">{card.detail2}</div>}
      {card.detail3 && <div className="mt-1 text-xs text-[#687386]">{card.detail3}</div>}
    </div>
  );
}

function CycleMetric({
  freshness,
  label,
  value,
  tone = "neutral"
}: {
  freshness?: "current" | "old" | "missing";
  label: string;
  value: string;
  tone?: Tone;
}) {
  return (
    <div className="relative min-h-[118px] overflow-hidden rounded-[22px] border border-white/70 bg-white/82 p-4 shadow-[0_10px_26px_rgba(15,23,42,0.05)]">
      <div className={clsx("absolute inset-x-0 top-0 h-1", cycleAccentClass(tone))} />
      <div className="flex items-start justify-between gap-2">
        <div className="text-xs font-semibold uppercase tracking-[0.16em] text-[#64748b]">{label}</div>
        {freshness ? (
          <span className={clsx("shrink-0 rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.08em]", cycleFreshnessClass(freshness))}>
            {cycleFreshnessLabel(freshness)}
          </span>
        ) : null}
      </div>
      <div className={clsx("mt-4 break-words text-xl font-semibold leading-7 tracking-normal tabular-nums", toneText(tone))}>{value}</div>
    </div>
  );
}

function cycleFreshness(value: string | number | null | undefined, current: boolean | null | undefined) {
  if (value === null || value === undefined || value === "") return "missing" as const;
  return current ? ("current" as const) : ("old" as const);
}

function cycleFreshnessLabel(value: "current" | "old" | "missing") {
  if (value === "current") return "aktuell";
  if (value === "old") return "alter Wert";
  return "fehlt";
}

function cycleFreshnessClass(value: "current" | "old" | "missing") {
  if (value === "current") return "border-[#bbf7d0] bg-[#ecfdf5] text-[#047857]";
  if (value === "old") return "border-[#fed7aa] bg-[#fffbeb] text-[#b45309]";
  return "border-[#e2e8f0] bg-[#f8fafc] text-[#64748b]";
}

function heroToneClasses(tone: Tone) {
  if (tone === "good") return "border-[#bbf7d0] bg-[linear-gradient(135deg,#ffffff_0%,#f0fdf4_55%,#ecfdf5_100%)]";
  if (tone === "bad") return "border-[#fecaca] bg-[linear-gradient(135deg,#ffffff_0%,#fff7f7_52%,#fef2f2_100%)]";
  if (tone === "warning") return "border-[#fed7aa] bg-[linear-gradient(135deg,#ffffff_0%,#fffaf0_54%,#fffbeb_100%)]";
  return "border-[#bfdbfe] bg-[linear-gradient(135deg,#ffffff_0%,#f8fbff_54%,#eff6ff_100%)]";
}

function phaseCardClass(tone: Tone) {
  if (tone === "good") return "border-[#bbf7d0] bg-[linear-gradient(135deg,#ffffff_0%,#ecfdf5_100%)]";
  if (tone === "bad") return "border-[#fecaca] bg-[linear-gradient(135deg,#ffffff_0%,#fff1f2_100%)]";
  if (tone === "warning") return "border-[#fed7aa] bg-[linear-gradient(135deg,#ffffff_0%,#fffbeb_100%)]";
  return "border-[#bfdbfe] bg-[linear-gradient(135deg,#ffffff_0%,#eff6ff_100%)]";
}

function activeLightClass(tone: Tone, key?: MarketAmpelLight["key"]) {
  if (key === "aufwaertstrend") return "border-[#bfdbfe] bg-[#2563eb] text-white shadow-[0_0_28px_rgba(37,99,235,0.24)]";
  if (tone === "good") return "border-[#bbf7d0] bg-[#059669] text-white shadow-[0_0_28px_rgba(5,150,105,0.22)]";
  if (tone === "bad") return "border-[#fecaca] bg-[#dc2626] text-white shadow-[0_0_28px_rgba(220,38,38,0.20)]";
  if (tone === "warning") return "border-[#fed7aa] bg-[#d97706] text-white shadow-[0_0_28px_rgba(217,119,6,0.22)]";
  return "border-[#bfdbfe] bg-[#2563eb] text-white shadow-[0_0_28px_rgba(37,99,235,0.20)]";
}

function dotBg(tone: Tone) {
  if (tone === "good") return "bg-emerald-300";
  if (tone === "bad") return "bg-rose-300";
  if (tone === "warning") return "bg-amber-300";
  return "bg-sky-300";
}

function tileBorder(tone: Tone) {
  if (tone === "good") return "border-[#bbf7d0] bg-[#ecfdf5]";
  if (tone === "bad") return "border-[#fecaca] bg-[#fff1f2]";
  if (tone === "warning") return "border-[#fed7aa] bg-[#fffbeb]";
  return "border-[#bfdbfe] bg-[#eff6ff]";
}

function toneText(tone: Tone) {
  if (tone === "good") return "text-[#059669]";
  if (tone === "bad") return "text-[#dc2626]";
  if (tone === "warning") return "text-[#d97706]";
  return "text-[#2563eb]";
}

function phaseStepClass(tone: Tone) {
  if (tone === "good") return "border-[#bbf7d0] bg-[#ecfdf5]";
  if (tone === "bad") return "border-[#fecaca] bg-[#fff1f2]";
  if (tone === "warning") return "border-[#fed7aa] bg-[#fffbeb]";
  return "border-[#bfdbfe] bg-[#eff6ff]";
}

function phasePillClass(tone: Tone) {
  if (tone === "good") return "border-[#bbf7d0] bg-[#ecfdf5] text-[#047857]";
  if (tone === "bad") return "border-[#fecaca] bg-[#fff1f2] text-[#b91c1c]";
  if (tone === "warning") return "border-[#fed7aa] bg-[#fffbeb] text-[#b45309]";
  return "border-[#bfdbfe] bg-[#eff6ff] text-[#1d4ed8]";
}

function cycleAccentClass(tone: Tone) {
  if (tone === "good") return "bg-[#059669]";
  if (tone === "bad") return "bg-[#dc2626]";
  if (tone === "warning") return "bg-[#d97706]";
  return "bg-[#2563eb]";
}

function distanceTone(value?: number | null): Tone {
  if (value === null || value === undefined) return "neutral";
  return value >= 0 ? "good" : "bad";
}

function formatValueWithDistance(value?: number | null, pct?: number | null) {
  if (value === null || value === undefined) return "-";
  const formattedValue = new Intl.NumberFormat("de-DE", { maximumFractionDigits: 2 }).format(value);
  if (pct === null || pct === undefined) return formattedValue;
  return `${formattedValue} (${pct >= 0 ? "+" : ""}${pct.toFixed(1)}%)`;
}
