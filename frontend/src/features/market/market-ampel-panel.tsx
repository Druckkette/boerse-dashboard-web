"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { ArrowDown, ArrowUp, ChevronDown, CircleAlert, CircleDot, RotateCw, ShieldAlert } from "lucide-react";
import { LineChartCard } from "@/components/ui/line-chart-card";
import { StatusChip } from "@/components/ui/status-chip";
import { api } from "@/lib/api/client";
import type { MarketAmpel, MarketAmpelChangeCard, MarketAmpelDistanceTile, MarketAmpelLight, MarketAmpelWarningCheck, Tone } from "@/lib/types/api";
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
    staleTime: 60_000,
    refetchInterval: MARKET_REFETCH_INTERVAL_MS
  });

  if (query.isLoading || (query.data && query.data.ticker !== ticker)) {
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
      <CompactMarketAmpel
        data={data}
        days={days}
        heroReason={heroReasons[0]}
        indexes={indexes}
        isFetching={query.isFetching}
        onDaysChange={setDays}
        onRefresh={() => query.refetch()}
        onTickerChange={onTickerChange}
        ticker={ticker}
        todayCard={todayCard}
      />

      {changeCards.length > 0 ? (
        <div className="grid gap-3 sm:grid-cols-2">
          {changeCards.map((card) => (
            <ChangeCard key={card.title} card={card} />
          ))}
        </div>
      ) : null}

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

function CompactMarketAmpel({
  data,
  days,
  heroReason,
  indexes,
  isFetching,
  onDaysChange,
  onRefresh,
  onTickerChange,
  ticker,
  todayCard
}: {
  data: MarketAmpel;
  days: (typeof dayOptions)[number];
  heroReason?: string;
  indexes: readonly MarketIndexOption[];
  isFetching: boolean;
  onDaysChange: (days: (typeof dayOptions)[number]) => void;
  onRefresh: () => void;
  onTickerChange?: (ticker: MarketIndexTicker) => void;
  ticker: MarketIndexTicker;
  todayCard?: MarketAmpelChangeCard;
}) {
  return (
    <div className="overflow-hidden rounded-[22px] border border-[#dfe5ec] bg-white shadow-[0_12px_34px_rgba(15,23,42,0.065)]">
      <div className="flex flex-col gap-3 border-b border-[#e7ebf0] bg-[#fbfcfe] px-4 py-3.5 xl:flex-row xl:items-center xl:justify-between sm:px-5">
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <h1 className="mr-1 text-base font-semibold text-[#0f172a]">Marktampel</h1>
          <StatusChip tone={data.phase_info.tone}>{data.phase_info.label}</StatusChip>
          <StatusChip tone={toneForStatus(data.data_status)}>{labelForStatus(data.data_status)}</StatusChip>
        </div>

        <div className="flex min-w-0 flex-col gap-2.5 lg:flex-row lg:items-center">
          <div aria-label="Index auswählen" className="grid min-w-0 grid-cols-3 rounded-xl border border-[#dfe5ec] bg-white p-1">
            {indexes.map((item) => (
              <button
                key={item.ticker}
                aria-pressed={ticker === item.ticker}
                className={clsx(
                  "min-w-0 rounded-lg px-3 py-1.5 text-left transition duration-200 focus:outline-none focus:ring-2 focus:ring-[#0f766e]/25",
                  ticker === item.ticker
                    ? "bg-[#e8f4f2] text-[#0f766e]"
                    : "text-[#64748b] hover:bg-[#f4f7f9] hover:text-[#0f172a]"
                )}
                type="button"
                onClick={() => onTickerChange?.(item.ticker)}
              >
                <span className="block truncate text-xs font-semibold">{item.label}</span>
                <span className="mt-0.5 block text-[10px] font-medium opacity-70">{item.ticker}</span>
              </button>
            ))}
          </div>

          <div className="flex items-center gap-1 rounded-xl border border-[#dfe5ec] bg-white p-1">
            {dayOptions.map((option) => (
              <button
                key={option}
                aria-pressed={days === option}
                className={clsx(
                  "rounded-lg px-2.5 py-1.5 text-xs font-semibold transition focus:outline-none focus:ring-2 focus:ring-[#2563eb]/20",
                  days === option
                    ? "bg-[#eef5ff] text-[#1d4ed8]"
                    : "text-[#64748b] hover:bg-[#f4f7f9] hover:text-[#0f172a]"
                )}
                type="button"
                onClick={() => onDaysChange(option)}
              >
                {option}T
              </button>
            ))}
            <button
              aria-label="Marktampel aktualisieren"
              className="grid size-8 place-items-center rounded-lg text-[#64748b] transition hover:bg-[#e8f4f2] hover:text-[#0f766e] focus:outline-none focus:ring-2 focus:ring-[#0f766e]/25"
              title="Marktampel aktualisieren"
              type="button"
              onClick={onRefresh}
            >
              <RotateCw size={15} className={isFetching ? "animate-spin" : ""} />
            </button>
          </div>
        </div>
      </div>

      <div className="p-4 sm:p-5">
        <div className={clsx("grid gap-4", todayCard && "xl:grid-cols-[minmax(0,1fr)_310px]")}>
          <div className={clsx("relative overflow-hidden rounded-2xl border px-4 py-4", compactStatusClass(data.hero.tone))}>
            <div className={clsx("absolute inset-y-0 left-0 w-1", cycleAccentClass(data.hero.tone))} />
            <div className="flex min-w-0 items-start gap-3">
              <StatusEmblem tone={data.hero.tone} />
              <div className="min-w-0 flex-1">
                <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[#64748b]">Aktuelle Marktphase</div>
                <div className={clsx("mt-1 text-2xl font-semibold leading-tight sm:text-[28px]", toneText(data.hero.tone))}>
                  {data.hero.mode}
                </div>
                <div className="mt-2 flex items-start gap-2 text-sm font-medium leading-6 text-[#172033]">
                  <ShieldAlert className="mt-1 shrink-0 text-[#64748b]" size={14} />
                  <span>{data.hero.action}</span>
                </div>
              </div>
            </div>
            {heroReason ? <TrendReasonCard reason={heroReason} tone={data.phase_info.tone} /> : null}
            <ActiveWarningsDisclosure checks={data.warning_checks} warningCount={data.warning_count} />
          </div>

          {todayCard ? <TodayIndexCard card={todayCard} /> : null}
        </div>

        <div className="mt-4 border-t border-[#e7ebf0] pt-4">
          <PhaseStepper lights={data.lights} />
        </div>

        <div className="mt-4 grid gap-3 lg:grid-cols-2">
          <InfoBlock title="Definition" text={data.phase_info.reason} />
          <InfoBlock title="Handlung" text={data.phase_info.action} emphasis />
        </div>

        <div className="mt-4 grid grid-cols-2 gap-2.5 xl:grid-cols-4">
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
          <div className="mt-2.5 text-xs leading-5 text-[#64748b]">{data.cycle.diagnostics.join(" · ")}</div>
        ) : null}

        <RuleDefinitions lights={data.lights} />
        <MovingAverageDistanceSummary tiles={data.distance_tiles} />
      </div>
    </div>
  );
}

function ActiveWarningsDisclosure({
  checks,
  warningCount
}: {
  checks: MarketAmpelWarningCheck[];
  warningCount: number;
}) {
  const [isExpanded, setIsExpanded] = useState(false);
  const activeChecks = checks.filter((check) => check.active_warning);
  if (!activeChecks.length) {
    return (
      <div className="mt-3 border-t border-black/5 pt-3 text-xs font-medium text-[#138a57]">
        Keine aktiven Warnzeichen
      </div>
    );
  }

  return (
    <div className="mt-3 overflow-hidden rounded-xl border border-[#e2c98f] bg-white/75">
      <button
        aria-expanded={isExpanded}
        className="flex w-full items-center justify-between gap-3 px-3 py-2.5 text-left text-sm font-semibold text-[#7c5514] transition hover:bg-white focus:outline-none focus:ring-2 focus:ring-inset focus:ring-[#b7791f]/30"
        type="button"
        onClick={() => setIsExpanded((current) => !current)}
      >
        <span className="flex min-w-0 items-center gap-2">
          <CircleAlert className="shrink-0 text-[#b7791f]" size={16} />
          <span>{warningCount} aktive Warnzeichen</span>
        </span>
        <span className="flex shrink-0 items-center gap-1 text-xs">
          {isExpanded ? "Details ausblenden" : "Details anzeigen"}
          <ChevronDown className={clsx("transition-transform", isExpanded && "rotate-180")} size={16} />
        </span>
      </button>

      <div className="border-t border-[#ead9b2] px-3 py-2.5">
        <div className="flex flex-wrap gap-1.5">
          {activeChecks.map((check) => (
            <span
              key={check.label}
              className="rounded-full border border-[#ead9b2] bg-[#fffaf0] px-2 py-1 text-[11px] font-semibold leading-4 text-[#7c5514]"
            >
              {check.label}
            </span>
          ))}
        </div>
      </div>

      {isExpanded ? (
        <div className="space-y-2 border-t border-[#ead9b2] p-3">
          {activeChecks.map((check) => (
            <div key={check.label} className="rounded-lg border border-[#f0dfb9] bg-[#fffaf0] px-3 py-2">
              <div className="flex items-start gap-2">
                <CircleAlert className="mt-0.5 shrink-0 text-[#b7791f]" size={14} />
                <div className="min-w-0">
                  <div className="text-xs font-semibold text-[#172033]">{check.label}</div>
                  <div className="mt-0.5 text-xs leading-5 text-[#687386]">{check.detail}</div>
                </div>
              </div>
            </div>
          ))}
          <p className="text-[11px] leading-5 text-[#687386]">
            Defensiv wird der Modus bei mindestens vier aktiven Warnzeichen, roter Trend-Ampel,
            Schutzmodus der gleichgewichteten Indizes oder VIX-Stress.
          </p>
        </div>
      ) : null}
    </div>
  );
}

function TrendReasonCard({ reason, tone }: { reason?: string; tone: Tone }) {
  if (!reason) return null;
  const parsed = parseTrendReason(reason);
  return (
    <div className="mt-3 flex flex-col gap-1 border-t border-black/5 pt-3 sm:flex-row sm:items-baseline sm:gap-3">
      <div className="shrink-0 text-[10px] font-semibold uppercase tracking-[0.13em] text-[#64748b]">{parsed.label}</div>
      <div className="min-w-0 text-sm leading-5 text-[#475569]">
        <span className={clsx("font-semibold", toneText(tone))}>{parsed.value}</span>
        {parsed.detail ? <span> · {parsed.detail}</span> : null}
      </div>
    </div>
  );
}

function TodayIndexCard({ card }: { card: MarketAmpelChangeCard }) {
  return (
    <div className="rounded-2xl border border-[#e2e8f0] bg-[#fbfcfe] px-4 py-3.5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[#64748b]">{card.title}</div>
          <div className="mt-1.5 flex items-center gap-1.5 text-2xl font-semibold tracking-normal text-[#0f172a]">
            {card.arrow === "up" && <ArrowUp className="text-[#059669]" size={18} />}
            {card.arrow === "down" && <ArrowDown className="text-[#dc2626]" size={18} />}
            <span className={toneText(card.tone)}>{card.value}</span>
          </div>
        </div>
        <span className={clsx("rounded-full border px-2 py-0.5 text-[10px] font-semibold", phasePillClass(card.tone))}>
          {card.quality ?? card.tone}
        </span>
      </div>
      <div className="mt-2 space-y-0.5 text-xs leading-5 text-[#475569]">
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

function InfoBlock({ emphasis = false, text, title }: { emphasis?: boolean; text: string; title: string }) {
  return (
    <div
      className={clsx(
        "min-w-0 rounded-xl border px-3.5 py-3",
        emphasis ? "border-[#c9dedb] bg-[#f3faf8]" : "border-[#e2e8f0] bg-[#fbfcfe]"
      )}
    >
      <div className="text-[10px] font-semibold uppercase tracking-[0.13em] text-[#64748b]">{title}</div>
      <p className={clsx("mt-1.5 text-sm leading-6", emphasis ? "font-semibold text-[#0f172a]" : "text-[#475569]")}>{text}</p>
    </div>
  );
}

function PhaseStepper({ lights }: { lights: MarketAmpelLight[] }) {
  return (
    <div className="relative grid grid-cols-2 gap-x-3 gap-y-2 md:grid-cols-4">
      <div className="pointer-events-none absolute left-[12.5%] right-[12.5%] top-3 hidden h-px bg-[#dfe5ec] md:block" />
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
        "relative z-10 min-w-0 rounded-xl px-2 py-1.5 transition duration-200",
        light.active
          ? clsx("bg-white shadow-[0_5px_16px_rgba(15,23,42,0.08)] ring-1", phaseStepRingClass(light.tone))
          : "text-[#64748b]"
      )}
    >
      <div className="flex items-center gap-2">
        <span
          className={clsx(
            "grid size-6 shrink-0 place-items-center rounded-full border-[3px] border-white transition duration-200",
            light.active
              ? activeLightClass(light.tone, light.key)
              : "bg-[#cbd5e1] text-white shadow-[0_0_0_1px_#cbd5e1]"
          )}
        >
          <span className="size-1.5 rounded-full bg-current" />
        </span>
        <span
          className={clsx(
            "min-w-0 break-words text-[11px] font-semibold uppercase leading-4 tracking-[0.06em] [overflow-wrap:anywhere]",
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
        "grid size-9 shrink-0 place-items-center rounded-xl border shadow-[0_8px_20px_rgba(15,23,42,0.08)]",
        activeLightClass(tone)
      )}
    >
      <CircleDot size={18} />
    </span>
  );
}

function RuleDefinitions({ lights }: { lights: MarketAmpelLight[] }) {
  return (
    <details className="group mt-3 overflow-hidden rounded-xl border border-[#e3e8ef] bg-[#fbfcfe]">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-4 px-3.5 py-2.5">
        <span>
          <span className="block text-sm font-semibold text-[#172033]">Regeldefinitionen</span>
          <span className="mt-0.5 block text-xs leading-5 text-[#687386]">Logik und Bedingungen der vier Ampelphasen.</span>
        </span>
        <span className="shrink-0 rounded-full border border-[#d8e1ea] bg-white px-2.5 py-1 text-[10px] font-semibold uppercase text-[#687386] group-open:text-[#0f766e]">
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
    <div className="mt-3 grid grid-cols-2 gap-2.5 xl:grid-cols-4">
      {tiles.map((tile) => (
        <div key={tile.label} className={clsx("rounded-xl border px-3 py-2.5", tileBorder(tile.tone))}>
          <div className="text-[10px] font-semibold uppercase tracking-[0.1em] text-[#687386]">{tile.label}</div>
          <div className={clsx("mt-1 text-lg font-semibold tabular-nums", toneText(tile.tone))}>{tile.value}</div>
          <div className="mt-0.5 text-xs font-medium text-[#4b5565]">{tile.indicator}</div>
          <div className="mt-0.5 text-[11px] leading-4 text-[#687386]">{tile.detail}</div>
        </div>
      ))}
    </div>
  );
}

function ChangeCard({ card }: { card: MarketAmpelChangeCard }) {
  return (
    <div className="rounded-[12px] border border-[#e3e8ef] bg-white px-3.5 py-3 shadow-[0_4px_14px_rgba(15,23,42,0.04)]">
      <div className="mb-2 flex items-center justify-between gap-3">
        <div className="text-xs font-semibold uppercase tracking-[0.06em] text-[#687386]">{card.title}</div>
        <StatusChip tone={card.tone}>{card.quality ?? card.tone}</StatusChip>
      </div>
      <div className="flex items-center gap-1.5 text-xl font-semibold text-[#172033]">
        {card.arrow === "up" && <ArrowUp className="text-[#138a57]" size={17} />}
        {card.arrow === "down" && <ArrowDown className="text-[#c2413b]" size={17} />}
        {card.value}
      </div>
      <div className="mt-1.5 text-xs leading-5 text-[#687386]">{card.detail}</div>
      {card.detail2 && <div className="mt-0.5 text-[11px] text-[#687386]">{card.detail2}</div>}
      {card.detail3 && <div className="mt-0.5 text-[11px] text-[#687386]">{card.detail3}</div>}
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
    <div className="relative min-h-[86px] overflow-hidden rounded-xl border border-[#e2e8f0] bg-[#fbfcfe] px-3 py-2.5">
      <div className={clsx("absolute inset-y-2.5 left-0 w-0.5 rounded-r-full", cycleAccentClass(tone))} />
      <div className="flex items-start justify-between gap-2">
        <div className="text-[10px] font-semibold uppercase tracking-[0.11em] text-[#64748b]">{label}</div>
        {freshness ? (
          <span className={clsx("shrink-0 rounded-full border px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-[0.05em]", cycleFreshnessClass(freshness))}>
            {cycleFreshnessLabel(freshness)}
          </span>
        ) : null}
      </div>
      <div className={clsx("mt-2 break-words text-base font-semibold leading-5 tracking-normal tabular-nums sm:text-lg", toneText(tone))}>{value}</div>
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

function compactStatusClass(tone: Tone) {
  if (tone === "good") return "border-[#cce9dc] bg-[#f4fbf7]";
  if (tone === "bad") return "border-[#f1d2d0] bg-[#fff8f7]";
  if (tone === "warning") return "border-[#f2dfb7] bg-[#fffbf3]";
  return "border-[#cdddf8] bg-[#f7faff]";
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

function phaseStepRingClass(tone: Tone) {
  if (tone === "good") return "ring-[#9bd7bd]";
  if (tone === "bad") return "ring-[#efb2ae]";
  if (tone === "warning") return "ring-[#e8c98d]";
  return "ring-[#a9c6f8]";
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
