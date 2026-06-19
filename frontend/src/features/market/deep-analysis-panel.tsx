"use client";

import { useQuery } from "@tanstack/react-query";
import { CircleAlert, CircleCheck, RotateCw } from "lucide-react";
import { LineChartCard } from "@/components/ui/line-chart-card";
import { StatusChip } from "@/components/ui/status-chip";
import { api } from "@/lib/api/client";
import type { MarketDeepAnalysis, MarketDeepAnalysisCheck, MarketDeepAnalysisMetric, Tone } from "@/lib/types/api";
import { labelForSource, labelForStatus, toneForSource, toneForStatus } from "./data-status";
import { MARKET_REFETCH_INTERVAL_MS } from "./query-timing";

export function DeepAnalysisPanel({ ticker = "^GSPC" }: { ticker?: string }) {
  const query = useQuery({
    queryKey: ["market-deep-analysis", ticker],
    queryFn: () => api.marketDeepAnalysis(260, ticker),
    staleTime: 60_000,
    refetchInterval: MARKET_REFETCH_INTERVAL_MS
  });
  const data = query.data;

  if (query.isLoading) {
    return (
      <section className="rounded border border-[#2d333d] bg-[#171a20] p-5 text-sm text-[#a0a7b4]">
        Tiefenanalyse lädt...
      </section>
    );
  }

  if (query.error || !data) {
    return (
      <section className="rounded border border-rose-400/40 bg-rose-400/10 p-5 text-sm text-rose-100">
        Tiefenanalyse ist aktuell nicht erreichbar.
      </section>
    );
  }

  return (
    <section className="space-y-4">
      <div className="rounded border border-[#2d333d] bg-[#171a20] p-5">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <div className="mb-3 flex flex-wrap items-center gap-2">
              <StatusChip tone={toneForSource(data.source)}>{labelForSource(data.source)}</StatusChip>
              <StatusChip tone={toneForStatus(data.data_status)}>{labelForStatus(data.data_status)}</StatusChip>
              <StatusChip tone={coverageTone(data.coverage_ratio)}>
                Coverage {(data.coverage_ratio * 100).toFixed(0)}%
              </StatusChip>
              {data.requested_universe ? (
                <StatusChip tone="neutral">
                  {data.loaded_universe}/{data.requested_universe} Titel
                </StatusChip>
              ) : (
                <StatusChip tone="neutral">{data.loaded_universe} Titel</StatusChip>
              )}
            </div>
            <h2 className="text-xl font-semibold tracking-normal">Tiefenanalyse</h2>
            <p className="mt-2 max-w-4xl text-sm leading-6 text-[#a0a7b4]">{data.message}</p>
          </div>
          <button
            className="inline-flex w-fit items-center gap-2 rounded border border-[#2d333d] bg-[#111419] px-3 py-2 text-sm text-[#d8dde6] transition hover:border-emerald-300/60"
            type="button"
            onClick={() => query.refetch()}
          >
            <RotateCw size={15} className={query.isFetching ? "animate-spin text-emerald-300" : "text-[#a0a7b4]"} />
            Aktualisieren
          </button>
        </div>
        <DeepAnalysisMeta data={data} />
      </div>

      <MetricGrid metrics={data.metrics} />

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.15fr)_minmax(340px,0.85fr)]">
        <DeepCharts data={data} />
        <DeepChecks checks={data.checks} />
      </div>

      <details className="rounded border border-[#2d333d] bg-[#171a20]">
        <summary className="cursor-pointer list-none px-5 py-4">
          <span className="block text-base font-semibold">Kennzahlen der Tiefenanalyse erklärt</span>
          <span className="mt-1 block text-sm leading-6 text-[#a0a7b4]">
            McClellan, NH/NL, Prozentwerte über gleitenden Durchschnitten und Deemer Ratio entsprechen dem Streamlit-Bereich.
          </span>
        </summary>
        <div className="grid gap-3 border-t border-[#2d333d] p-5 md:grid-cols-2 xl:grid-cols-5">
          <GlossaryCard title="McClellan Osc." text="A/D-Momentum aus Advancern minus Decliners; über 0 ist konstruktiv." />
          <GlossaryCard title="NH/NL Ratio" text="Neue Hochs geteilt durch neue Tiefs; über 1 signalisiert mehr Stärke als Schwäche." />
          <GlossaryCard title="% > 50-SMA" text="Kurz- bis mittelfristige Marktteilnahme; Streamlit-Schwelle für Stärke ist 70%." />
          <GlossaryCard title="% > 200-SMA" text="Langfristige Marktteilnahme im Aktienuniversum." />
          <GlossaryCard title="Deemer Ratio" text="10-Tage-Advancer/Decliner-Proxy; 1,97 markiert einen Breakaway-Breitenschub." />
        </div>
      </details>
    </section>
  );
}

function DeepAnalysisMeta({ data }: { data: MarketDeepAnalysis }) {
  const requested = data.requested_universe ?? 0;
  const loaded = data.loaded_universe ?? 0;
  const daily = data.daily_covered_count ?? 0;
  return (
    <div className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      <MetaTile
        label="Universe-Abdeckung"
        value={requested > 0 ? `${loaded}/${requested}` : loaded ? `${loaded}` : "-"}
        detail={daily > 0 && daily !== loaded ? `Letzter Tag: ${daily} Titel` : "Historisch geladene Titel"}
        tone={coverageTone(data.coverage_ratio)}
      />
      <MetaTile
        label="50-SMA Basis"
        value={data.valid_for_50sma > 0 ? data.valid_for_50sma.toLocaleString("de-DE") : "-"}
        detail="Titel mit ausreichender Historie"
        tone={data.valid_for_50sma > 0 ? "neutral" : "warning"}
      />
      <MetaTile
        label="200-SMA Basis"
        value={data.valid_for_200sma > 0 ? data.valid_for_200sma.toLocaleString("de-DE") : "-"}
        detail="Titel mit langfristiger Historie"
        tone={data.valid_for_200sma > 0 ? "neutral" : "warning"}
      />
      <MetaTile
        label="NH/NL Quelle"
        value={data.nhnl_uses_intraday ? "High/Low" : "Close"}
        detail={data.nhnl_uses_intraday ? "Wie Streamlit: Tageshoch/-tief" : "Fallback auf Schlusskurs"}
        tone={data.nhnl_uses_intraday ? "good" : "warning"}
      />
    </div>
  );
}

function MetaTile({
  detail,
  label,
  tone,
  value
}: {
  detail: string;
  label: string;
  tone: Tone;
  value: string;
}) {
  return (
    <div className={["rounded border bg-[#111419] p-3", cardClass(tone)].join(" ")}>
      <div className="text-xs uppercase text-[#a0a7b4]">{label}</div>
      <div className={["mt-2 text-xl font-semibold tracking-normal tabular-nums", toneText(tone)].join(" ")}>{value}</div>
      <div className="mt-1 text-xs leading-5 text-[#a0a7b4]">{detail}</div>
    </div>
  );
}

function MetricGrid({ metrics }: { metrics: MarketDeepAnalysisMetric[] }) {
  if (!metrics.length) {
    return (
      <div className="rounded border border-[#2d333d] bg-[#171a20] p-4 text-sm text-[#a0a7b4]">
        Keine Tiefenanalyse-Kennzahlen im Cache.
      </div>
    );
  }
  return (
    <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
      {metrics.map((metric) => (
        <div key={metric.label} className={["rounded border bg-[#171a20] p-4", cardClass(metric.tone)].join(" ")}>
          <div className="mb-3 flex items-start justify-between gap-3">
            <div className="text-xs uppercase text-[#a0a7b4]">{metric.label}</div>
            <StatusChip tone={metric.tone}>{toneLabel(metric.tone)}</StatusChip>
          </div>
          <div className={["text-2xl font-semibold tracking-normal tabular-nums", toneText(metric.tone)].join(" ")}>
            {metric.value}
          </div>
          <div className="mt-2 text-sm leading-5 text-[#d8dde6]">{metric.detail}</div>
        </div>
      ))}
    </div>
  );
}

function DeepCharts({ data }: { data: MarketDeepAnalysis }) {
  return (
    <div className="space-y-4">
      <LineChartCard
        caption={`A/D-Linie und McClellan Oscillator, Stand ${data.as_of}`}
        points={data.points}
        series={[
          {
            key: "ad_line",
            label: "A/D-Linie",
            color: "#38bdf8",
            formatter: (value) => value.toFixed(0)
          }
        ]}
        subSeries={[
          {
            key: "mcclellan",
            label: "McClellan",
            color: "#fbbf24",
            formatter: (value) => value.toFixed(1)
          }
        ]}
        subTitle="McClellan"
        statusLabel="A/D"
        statusTone="neutral"
        title="A/D-Linie und McClellan"
      />
      <LineChartCard
        caption="Neue Hochs/Tiefs, Marktbreite über MAs und Deemer Ratio"
        points={data.points.map((point) => ({
          ...point,
          negative_new_lows: -point.new_lows
        }))}
        series={[
          {
            key: "pct_above_50sma",
            label: "% > 50-SMA",
            color: "#fbbf24",
            formatter: (value) => `${value.toFixed(0)}%`
          },
          {
            key: "pct_above_200sma",
            label: "% > 200-SMA",
            color: "#a78bfa",
            formatter: (value) => `${value.toFixed(0)}%`
          }
        ]}
        subSeries={[
          {
            key: "deemer_ratio",
            label: "Deemer Ratio",
            color: "#34d399",
            formatter: (value) => value.toFixed(2)
          },
          {
            key: "new_highs",
            label: "Neue Hochs",
            color: "#22c55e",
            formatter: (value) => value.toFixed(0)
          },
          {
            key: "negative_new_lows",
            label: "Neue Tiefs",
            color: "#fb7185",
            formatter: (value) => Math.abs(value).toFixed(0)
          }
        ]}
        subTitle="Deemer und NH/NL"
        statusLabel="Breadth"
        statusTone="neutral"
        title="Breadth Deep Dive"
      />
    </div>
  );
}

function DeepChecks({ checks }: { checks: MarketDeepAnalysisCheck[] }) {
  return (
    <div className="rounded border border-[#2d333d] bg-[#171a20] p-4">
      <div className="mb-4 flex items-center justify-between gap-3">
        <div>
          <h3 className="text-base font-semibold">Divergenzen und Bestätigung</h3>
          <p className="text-sm text-[#a0a7b4]">Checks aus der Streamlit-Tiefenanalyse.</p>
        </div>
        <StatusChip tone={warningTone(checks)}>{checks.filter((check) => !check.passed).length} offen</StatusChip>
      </div>
      <div className="space-y-3">
        {checks.map((check) => (
          <div key={check.label} className={["rounded border bg-[#111419] p-3", cardClass(check.tone)].join(" ")}>
            <div className="flex items-start gap-3">
              {check.passed ? (
                <CircleCheck className="mt-0.5 shrink-0 text-emerald-300" size={18} />
              ) : (
                <CircleAlert className="mt-0.5 shrink-0 text-amber-300" size={18} />
              )}
              <div className="min-w-0">
                <div className="text-sm font-medium text-[#d8dde6]">{check.label}</div>
                <div className="mt-1 text-xs leading-5 text-[#a0a7b4]">{check.detail}</div>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function GlossaryCard({ text, title }: { text: string; title: string }) {
  return (
    <div className="rounded border border-[#242a33] bg-[#111419] p-4">
      <div className="text-sm font-semibold text-[#d8dde6]">{title}</div>
      <div className="mt-2 text-xs leading-5 text-[#a0a7b4]">{text}</div>
    </div>
  );
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
  if (tone === "good") return "grün";
  if (tone === "bad") return "rot";
  if (tone === "warning") return "gelb";
  return "n/a";
}

function coverageTone(value: number): Tone {
  if (value >= 0.8) return "good";
  if (value >= 0.5) return "warning";
  return "bad";
}

function warningTone(checks: MarketDeepAnalysisCheck[]): Tone {
  const open = checks.filter((check) => !check.passed).length;
  if (open === 0) return "good";
  if (open <= 2) return "warning";
  return "bad";
}
