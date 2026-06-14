"use client";

import { useQuery } from "@tanstack/react-query";
import { LineChartCard } from "@/components/ui/line-chart-card";
import { StatusChip } from "@/components/ui/status-chip";
import { api } from "@/lib/api/client";
import type { Breadth, Tone } from "@/lib/types/api";
import { labelForSource, labelForStatus, toneForStatus } from "./data-status";

export function BreadthChartPanel() {
  const query = useQuery({
    queryKey: ["market-breadth"],
    queryFn: api.marketBreadth,
    staleTime: 60_000
  });
  const breadth = query.data;

  return (
    <div className="space-y-4">
      <div className="grid gap-3 md:grid-cols-2 2xl:grid-cols-5">
        {breadthSignals(breadth).map((signal) => (
          <BreadthSignalCard key={signal.title} {...signal} />
        ))}
      </div>
      <LineChartCard
        caption={
          breadth
            ? `${breadth.universe}, ${coverageCaption(breadth)}, Stand ${breadth.as_of}. ${breadth.message}`
            : "A/D- und SMA-Breitenwerte aus dem Market-Backend"
        }
        error={query.error}
        isLoading={query.isLoading}
        points={breadth?.points ?? []}
        series={[
          {
            key: "pct_above_50sma",
            label: "% Aktien > 50-SMA",
            color: "#22d3ee",
            formatter: (value) => `${value.toFixed(1)}%`
          },
          {
            key: "pct_above_200sma",
            label: "% Aktien > 200-SMA",
            color: "#a78bfa",
            formatter: (value) => `${value.toFixed(1)}%`
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
        statusLabel={breadth ? `${labelForSource(breadth.source)} · ${labelForStatus(breadth.data_status)}` : "lädt"}
        statusTone={breadth ? toneForStatus(breadth.data_status) : "neutral"}
        title="Market Breadth"
      />
    </div>
  );
}

function breadthSignals(breadth?: Breadth) {
  const latest = breadth?.points.at(-1);
  return [
    {
      title: "Universum",
      status: breadth ? `${(breadth.coverage_ratio * 100).toFixed(0)}%` : "-",
      detail: breadth ? coverageCaption(breadth) : "Universe-Abdeckung fehlt.",
      tone: breadth ? coverageTone(breadth.coverage_ratio) : "neutral"
    },
    {
      title: "50-SMA Breite",
      status: latest ? formatPct(latest.pct_above_50sma) : "-",
      detail: latest
        ? `${validCountLabel(breadth?.valid_for_50sma, breadth?.daily_covered_count)} · ${latest.advancers}/${latest.decliners} A/D`
        : "Breadth-Daten fehlen.",
      tone: toneForPct(latest?.pct_above_50sma, 70, 50)
    },
    {
      title: "200-SMA Breite",
      status: latest ? formatPct(latest.pct_above_200sma) : "-",
      detail: latest ? `${validCountLabel(breadth?.valid_for_200sma, breadth?.daily_covered_count)} · langfristige Teilnahme` : "Nicht berechnet",
      tone: toneForPct(latest?.pct_above_200sma, 55, 40)
    },
    {
      title: "McClellan",
      status: latest ? formatNumber(latest.mcclellan, 1) : "-",
      detail: latest ? (latest.mcclellan > 0 ? "A/D-Momentum positiv" : "A/D-Momentum negativ") : "Nicht berechnet",
      tone: latest ? (latest.mcclellan > 0 ? "good" : latest.mcclellan > -50 ? "warning" : "bad") : "neutral"
    },
    {
      title: "NH/NL",
      status: latest ? `${latest.new_highs}/${latest.new_lows}` : "-",
      detail: breadth?.nhnl_uses_intraday ? "Neue Hochs/Tiefs auf Tageshoch/-tief" : "Neue Hochs/Tiefs per Schlusskurs",
      tone: latest ? toneForRatio(latest.new_highs, latest.new_lows) : "neutral"
    }
  ] as const;
}

function coverageCaption(breadth: Breadth) {
  const requested = breadth.requested_universe ?? 0;
  const loaded = breadth.loaded_universe ?? 0;
  const daily = breadth.daily_covered_count ?? 0;
  const base = requested > 0 ? `Coverage ${(breadth.coverage_ratio * 100).toFixed(0)}% (${loaded}/${requested} geladen)` : `Coverage ${(breadth.coverage_ratio * 100).toFixed(0)}%`;
  if (daily > 0 && loaded > 0 && daily !== loaded) {
    return `${base}, letzter Tag ${daily}`;
  }
  return base;
}

function validCountLabel(value?: number, fallback?: number) {
  const count = value && value > 0 ? value : fallback;
  return count && count > 0 ? `${count} gültige Titel` : "gültige Titel n/a";
}

function coverageTone(value: number): Tone {
  if (value >= 0.8) return "good";
  if (value >= 0.5) return "warning";
  return "bad";
}

function BreadthSignalCard({
  detail,
  status,
  title,
  tone
}: {
  detail: string;
  status: string;
  title: string;
  tone: Tone;
}) {
  return (
    <div className={["rounded border bg-[#171a20] p-4", cardClass(tone)].join(" ")}>
      <div className="mb-3 flex items-center justify-between gap-3">
        <div className="text-xs uppercase text-[#a0a7b4]">{title}</div>
        <StatusChip tone={tone}>{toneLabel(tone)}</StatusChip>
      </div>
      <div className={["text-2xl font-semibold tracking-normal tabular-nums", toneText(tone)].join(" ")}>{status}</div>
      <div className="mt-2 text-sm leading-5 text-[#d8dde6]">{detail}</div>
    </div>
  );
}

function toneForPct(value: number | undefined, good: number, warning: number): Tone {
  if (value === undefined) return "neutral";
  if (value >= good) return "good";
  if (value >= warning) return "warning";
  return "bad";
}

function toneForRatio(highs: number, lows: number): Tone {
  if (highs > lows) return "good";
  if (highs === lows) return "warning";
  return "bad";
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

function formatPct(value: number) {
  return `${value.toFixed(0)}%`;
}

function formatNumber(value: number, digits = 2) {
  return new Intl.NumberFormat("de-DE", { maximumFractionDigits: digits, minimumFractionDigits: digits }).format(value);
}
