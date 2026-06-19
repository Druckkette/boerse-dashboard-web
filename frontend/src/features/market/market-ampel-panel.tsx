"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { ArrowDown, ArrowUp, CircleDot, RotateCw } from "lucide-react";
import { LineChartCard } from "@/components/ui/line-chart-card";
import { StatusChip } from "@/components/ui/status-chip";
import { api } from "@/lib/api/client";
import type { MarketAmpel, MarketAmpelChangeCard, MarketAmpelLight, Tone } from "@/lib/types/api";
import { labelForSource, labelForStatus, toneForSource, toneForStatus } from "./data-status";
import { MARKET_REFETCH_INTERVAL_MS } from "./query-timing";

const indexes = [
  { ticker: "^GSPC", label: "S&P 500" },
  { ticker: "^IXIC", label: "Nasdaq" },
  { ticker: "^RUT", label: "Russell 2000" }
] as const;

const dayOptions = [60, 90, 130, 200] as const;

export function MarketAmpelPanel() {
  const [ticker, setTicker] = useState<(typeof indexes)[number]["ticker"]>("^GSPC");
  const [days, setDays] = useState<(typeof dayOptions)[number]>(90);
  const query = useQuery({
    queryKey: ["market-ampel", ticker, days],
    queryFn: () => api.marketAmpel(ticker, days),
    placeholderData: (previous) => previous,
    staleTime: 60_000,
    refetchInterval: MARKET_REFETCH_INTERVAL_MS
  });

  if (query.isLoading) {
    return <section className="rounded border border-[#2d333d] bg-[#171a20] p-5 text-sm text-[#a0a7b4]">Marktampel lädt...</section>;
  }

  if (query.error || !query.data) {
    return (
      <section className="rounded border border-rose-400/40 bg-rose-400/10 p-5 text-sm text-rose-100">
        Marktampel ist aktuell nicht erreichbar.
      </section>
    );
  }

  const data = query.data;
  const heroReasons = data.hero.reasons.filter((reason) => reason.startsWith("Trendwende-Ampel"));
  const changeCards = data.change_cards.filter(
    (card) => !["Distribution", "EW-Breite", "Volatilität"].includes(card.title)
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
      <div className={clsx("rounded border p-5", heroToneClasses(data.hero.tone))}>
        <div className="flex flex-col gap-5 xl:flex-row xl:items-start xl:justify-between">
          <div className="min-w-0">
            <div className="mb-3 flex flex-wrap items-center gap-2">
              <StatusChip tone={data.hero.tone}>{data.hero.mode}</StatusChip>
              <StatusChip tone={data.phase_info.tone}>{data.phase_info.label}</StatusChip>
              <StatusChip tone={toneForSource(data.source)}>{labelForSource(data.source)}</StatusChip>
              <StatusChip tone={toneForStatus(data.data_status)}>{labelForStatus(data.data_status)}</StatusChip>
            </div>
            <h1 className="text-2xl font-semibold tracking-normal md:text-3xl">Marktampel</h1>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-[#d8dde6]">{data.hero.action}</p>
            <div className="mt-4 grid gap-2 md:grid-cols-2">
              {heroReasons.map((reason) => (
                <div key={reason} className="rounded border border-white/10 bg-black/15 px-3 py-2 text-sm text-[#c9d0da]">
                  {reason}
                </div>
              ))}
            </div>
          </div>
          <div className="flex shrink-0 flex-col gap-3">
            <div className="flex flex-wrap gap-2 xl:justify-end">
              {indexes.map((item) => (
                <button
                  key={item.ticker}
                  className={clsx(
                    "rounded border px-3 py-2 text-sm transition",
                    ticker === item.ticker
                      ? "border-emerald-300/60 bg-emerald-300/10 text-emerald-100"
                      : "border-[#2d333d] bg-[#111419] text-[#a0a7b4] hover:border-[#586071] hover:text-[#d8dde6]"
                  )}
                  type="button"
                  onClick={() => setTicker(item.ticker)}
                >
                  {item.label}
                </button>
              ))}
            </div>
            <div className="flex flex-wrap gap-2 xl:justify-end">
              {dayOptions.map((option) => (
                <button
                  key={option}
                  className={clsx(
                    "rounded border px-3 py-2 text-sm transition",
                    days === option
                      ? "border-sky-300/60 bg-sky-300/10 text-sky-100"
                      : "border-[#2d333d] bg-[#111419] text-[#a0a7b4] hover:border-[#586071] hover:text-[#d8dde6]"
                  )}
                  type="button"
                  onClick={() => setDays(option)}
                >
                  {option}T
                </button>
              ))}
              <button
                className="inline-flex items-center gap-2 rounded border border-[#2d333d] bg-[#111419] px-3 py-2 text-sm text-[#d8dde6] transition hover:border-emerald-300/60"
                type="button"
                onClick={() => query.refetch()}
              >
                <RotateCw size={15} className={query.isFetching ? "animate-spin text-emerald-300" : "text-[#a0a7b4]"} />
                Aktualisieren
              </button>
            </div>
          </div>
        </div>
      </div>

      <div className="grid gap-4 2xl:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
        <TrafficLightPanel data={data} />
        <div className="grid gap-3 sm:grid-cols-2">
          {changeCards.map((card) => (
            <ChangeCard key={card.title} card={card} />
          ))}
        </div>
      </div>

      <LineChartCard
        title={`${data.name} Trendwende-Ampel`}
        caption={`${data.phase_info.reason} Stand ${data.as_of}. ${data.message}`}
        points={chartPoints}
        chartMode="candlestick"
        volumeKey="volume"
        markers={data.chart_markers}
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

function TrafficLightPanel({ data }: { data: MarketAmpel }) {
  return (
    <div className="rounded border border-[#2d333d] bg-[#171a20] p-5">
      <div className="grid gap-6 2xl:grid-cols-[minmax(240px,0.42fr)_minmax(0,1fr)]">
        <div className="min-w-0">
          <div className="mb-4">
            <h2 className="text-lg font-semibold tracking-normal">Trendwende-Ampel</h2>
            <p className="mt-1 text-sm leading-6 text-[#a0a7b4]">Rot, Gelb, Grün und Aufwärtstrend wie im Streamlit-Dashboard.</p>
          </div>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 2xl:grid-cols-1">
            {data.lights.map((light) => (
              <Light key={light.key} light={light} />
            ))}
          </div>
        </div>
        <div className={clsx("min-w-0 rounded border p-5 sm:p-6", phaseCardClass(data.phase_info.tone))}>
          <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
            <div className="min-w-0">
              <div className="text-xs font-semibold uppercase tracking-normal text-[#a0a7b4]">Aktuelle Ampelphase</div>
              <div
                className={clsx(
                  "mt-2 break-words text-3xl font-semibold leading-tight tracking-normal sm:text-4xl",
                  toneText(data.phase_info.tone)
                )}
              >
                {data.phase_info.label}
              </div>
            </div>
            <StatusChip tone={data.phase_info.tone}>{data.phase_info.label}</StatusChip>
          </div>

          <div className="mt-6 grid gap-5 lg:grid-cols-2">
            <InfoBlock title="Definition" text={data.phase_info.reason} />
            <InfoBlock title="Handlung" text={data.phase_info.action} emphasis />
          </div>

          <div className="mt-6 border-t border-white/10 pt-5">
            <div className="mb-3 text-xs font-semibold uppercase tracking-normal text-[#77808f]">Letzter Startschuss und Zykluswerte</div>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
              <CycleMetric label="Ankertag" value={data.cycle.anchor_date ?? "-"} />
              <CycleMetric
                label="Bodenmarke"
                value={formatValueWithDistance(data.cycle.floor_mark, data.cycle.floor_distance_pct)}
                tone={distanceTone(data.cycle.floor_distance_pct)}
              />
              <CycleMetric
                label="Startschuss-Tief"
                value={formatValueWithDistance(data.cycle.startschuss_low, data.cycle.startschuss_distance_pct)}
                tone={distanceTone(data.cycle.startschuss_distance_pct)}
              />
              <CycleMetric
                label="MA-Ordnung"
                value={data.cycle.ma_order ? "Korrekt" : "Gestört"}
                tone={data.cycle.ma_order ? "good" : "bad"}
              />
            </div>
            {data.cycle.diagnostics.length > 0 ? (
              <div className="mt-3 text-xs leading-5 text-[#8e97a6]">{data.cycle.diagnostics.join(" · ")}</div>
            ) : null}
          </div>
        </div>
      </div>
      <RuleDefinitions lights={data.lights} />
    </div>
  );
}

function InfoBlock({ emphasis = false, text, title }: { emphasis?: boolean; text: string; title: string }) {
  return (
    <div className="min-w-0">
      <div className="text-xs font-semibold uppercase tracking-normal text-[#77808f]">{title}</div>
      <p className={clsx("mt-2 text-sm leading-7", emphasis ? "text-[#f2f5f8]" : "text-[#d8dde6]")}>{text}</p>
    </div>
  );
}

function Light({ light }: { light: MarketAmpelLight }) {
  return (
    <div
      className={clsx(
        "flex min-h-[88px] min-w-0 items-center gap-3 rounded border p-3",
        light.active ? tileBorder(light.tone) : "border-[#242a33] bg-[#111419]"
      )}
    >
      <span
        className={clsx(
          "grid size-11 shrink-0 place-items-center rounded-full border transition",
          light.active ? activeLightClass(light.tone, light.key) : "border-[#3b4350] bg-[#141820] text-[#586071]"
        )}
      >
        <CircleDot size={22} />
      </span>
      <span
        className={clsx(
          "min-w-0 break-words text-xs font-semibold leading-5 [overflow-wrap:anywhere] sm:text-sm",
          light.active ? toneText(light.tone) : "text-[#77808f]"
        )}
      >
        {light.key === "aufwaertstrend" ? (
          "AUFWÄRTSTREND"
        ) : (
          light.label
        )}
      </span>
    </div>
  );
}

function RuleDefinitions({ lights }: { lights: MarketAmpelLight[] }) {
  return (
    <details className="group mt-4 rounded border border-[#2d333d] bg-[#111419]">
      <summary className="flex cursor-pointer list-none items-start justify-between gap-4 px-4 py-3">
        <span>
          <span className="block text-base font-semibold">Regeldefinitionen</span>
          <span className="mt-1 block text-sm leading-6 text-[#a0a7b4]">Ampelphasen aus der Streamlit-Logik.</span>
        </span>
        <span className="mt-1 shrink-0 rounded border border-[#2d333d] bg-[#171a20] px-2 py-1 text-xs text-[#a0a7b4] group-open:text-emerald-200">
          Details
        </span>
      </summary>
      <div className="grid gap-3 border-t border-[#2d333d] p-4 md:grid-cols-2">
        {lights.map((light) => (
          <div key={light.key} className={clsx("rounded border bg-[#171a20] p-4", light.active ? tileBorder(light.tone) : "border-[#242a33]")}>
            <div className="mb-2 flex items-center gap-2">
              <span className={clsx("size-2 rounded-full", dotBg(light.tone))} />
              <div className={clsx("text-sm font-semibold", light.active ? toneText(light.tone) : "text-[#d8dde6]")}>
                {light.label}
              </div>
              {light.active && <StatusChip tone={light.tone}>aktiv</StatusChip>}
            </div>
            <p className="text-sm leading-6 text-[#c9d0da]">{light.rule}</p>
          </div>
        ))}
      </div>
    </details>
  );
}

function ChangeCard({ card }: { card: MarketAmpelChangeCard }) {
  return (
    <div className="rounded border border-[#2d333d] bg-[#171a20] p-4">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div className="text-sm text-[#a0a7b4]">{card.title}</div>
        <StatusChip tone={card.tone}>{card.quality ?? card.tone}</StatusChip>
      </div>
      <div className="flex items-center gap-2 text-2xl font-semibold tracking-normal">
        {card.arrow === "up" && <ArrowUp className="text-emerald-300" size={20} />}
        {card.arrow === "down" && <ArrowDown className="text-rose-300" size={20} />}
        {card.value}
      </div>
      <div className="mt-2 text-sm text-[#a0a7b4]">{card.detail}</div>
      {card.detail2 && <div className="mt-1 text-xs text-[#77808f]">{card.detail2}</div>}
      {card.detail3 && <div className="mt-1 text-xs text-[#77808f]">{card.detail3}</div>}
    </div>
  );
}

function CycleMetric({ label, value, tone = "neutral" }: { label: string; value: string; tone?: Tone }) {
  return (
    <div className="min-h-[104px] rounded border border-[#2d333d] bg-[#111419] p-4">
      <div className="text-xs font-semibold uppercase tracking-normal text-[#77808f]">{label}</div>
      <div className={clsx("mt-3 break-words text-lg font-semibold leading-7 tracking-normal tabular-nums", toneText(tone))}>{value}</div>
    </div>
  );
}

function heroToneClasses(tone: Tone) {
  if (tone === "good") return "border-emerald-300/30 bg-emerald-300/10";
  if (tone === "bad") return "border-rose-300/30 bg-rose-300/10";
  if (tone === "warning") return "border-amber-300/30 bg-amber-300/10";
  return "border-[#2d333d] bg-[#171a20]";
}

function phaseCardClass(tone: Tone) {
  if (tone === "good") return "border-emerald-300/35 bg-emerald-300/10";
  if (tone === "bad") return "border-rose-300/35 bg-rose-300/10";
  if (tone === "warning") return "border-amber-300/35 bg-amber-300/10";
  return "border-[#2d333d] bg-[#111419]";
}

function activeLightClass(tone: Tone, key?: MarketAmpelLight["key"]) {
  if (key === "aufwaertstrend") return "border-sky-100 bg-sky-400/90 text-[#03111d] shadow-[0_0_28px_rgba(56,189,248,0.35)]";
  if (tone === "good") return "border-emerald-200 bg-emerald-400/90 text-[#07130d] shadow-[0_0_28px_rgba(52,211,153,0.35)]";
  if (tone === "bad") return "border-rose-200 bg-rose-400/90 text-[#18070a] shadow-[0_0_28px_rgba(251,113,133,0.35)]";
  return "border-amber-100 bg-amber-300/90 text-[#1d1303] shadow-[0_0_28px_rgba(251,191,36,0.35)]";
}

function dotBg(tone: Tone) {
  if (tone === "good") return "bg-emerald-300";
  if (tone === "bad") return "bg-rose-300";
  if (tone === "warning") return "bg-amber-300";
  return "bg-sky-300";
}

function tileBorder(tone: Tone) {
  if (tone === "good") return "border-emerald-300/35";
  if (tone === "bad") return "border-rose-300/35";
  if (tone === "warning") return "border-amber-300/35";
  return "border-[#2d333d]";
}

function toneText(tone: Tone) {
  if (tone === "good") return "text-emerald-200";
  if (tone === "bad") return "text-rose-200";
  if (tone === "warning") return "text-amber-100";
  return "text-[#c9d0da]";
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
