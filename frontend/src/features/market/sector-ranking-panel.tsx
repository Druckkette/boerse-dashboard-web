"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowDownRight, ArrowUpRight, RotateCw } from "lucide-react";
import { useState } from "react";
import { StatusChip } from "@/components/ui/status-chip";
import { api } from "@/lib/api/client";
import type { SectorRankingPoint, SectorRankingRow } from "@/lib/types/api";
import { labelForSource, labelForStatus, toneForStatus } from "./data-status";

type Mode = "daily" | "weekly";

export function SectorRankingPanel() {
  const [mode, setMode] = useState<Mode>("daily");
  const query = useQuery({
    queryKey: ["market-sectors", mode],
    queryFn: () => api.marketSectors(mode, 15),
    staleTime: 60_000
  });
  const data = query.data;

  return (
    <div className="space-y-5">
      <section className="rounded border border-[#2d333d] bg-[#171a20] p-5">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <div className="mb-3 flex flex-wrap items-center gap-2">
              <StatusChip tone={data ? toneForStatus(data.data_status) : "neutral"}>
                {data ? labelForStatus(data.data_status) : "lädt"}
              </StatusChip>
              {data && <StatusChip tone="neutral">{labelForSource(data.source)}</StatusChip>}
            </div>
            <h1 className="text-2xl font-semibold tracking-normal md:text-3xl">Sektoranalyse</h1>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-[#a0a7b4]">
              S&P-500-Sektor-ETFs nach Performance und Rankingverlauf. Berechnet aus dem Price-Cache, ohne yfinance im Klickpfad.
            </p>
            {data?.message && <p className="mt-2 max-w-3xl text-xs leading-5 text-[#77808f]">{data.message}</p>}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <div className="inline-flex rounded border border-[#2d333d] bg-[#111419] p-1">
              {(["daily", "weekly"] as const).map((item) => (
                <button
                  key={item}
                  className={[
                    "rounded px-3 py-2 text-sm transition",
                    mode === item ? "bg-emerald-300/15 text-emerald-100" : "text-[#a0a7b4] hover:text-white"
                  ].join(" ")}
                  type="button"
                  onClick={() => setMode(item)}
                >
                  {item === "daily" ? "Tagesansicht" : "Wochenansicht"}
                </button>
              ))}
            </div>
            <button
              className="inline-flex items-center gap-2 rounded border border-[#2d333d] bg-[#111419] px-3 py-2 text-sm transition hover:border-emerald-300/60"
              type="button"
              onClick={() => query.refetch()}
            >
              <RotateCw size={15} className={query.isFetching ? "animate-spin text-emerald-300" : "text-[#a0a7b4]"} />
              Aktualisieren
            </button>
          </div>
        </div>
      </section>

      {query.isLoading && (
        <div className="rounded border border-[#2d333d] bg-[#171a20] p-5 text-sm text-[#a0a7b4]">
          Sektordaten werden geladen...
        </div>
      )}
      {query.error && (
        <div className="rounded border border-rose-400/40 bg-rose-400/10 p-5 text-sm text-rose-100">
          Sektor-API nicht erreichbar.
        </div>
      )}
      {!query.isLoading && !query.error && data && data.rows.length === 0 && (
        <div className="rounded border border-[#2d333d] bg-[#171a20] p-5 text-sm text-[#a0a7b4]">
          Keine Sektorpreise im Cache. Starte auf der Jobs-Seite den Price-Refresh mit Preset `sector` oder `all`.
        </div>
      )}
      {data && data.rows.length > 0 && (
        <>
          <div className="grid gap-4 xl:grid-cols-2">
            <SectorSummary title="Top 3 Sektoren" rows={data.top} direction="up" />
            <SectorSummary title="Bottom 3 Sektoren" rows={data.bottom} direction="down" />
          </div>
          <section className="rounded border border-[#2d333d] bg-[#171a20] p-4">
            <div className="mb-4 flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
              <div>
                <h2 className="text-base font-semibold">Ranking-Tabelle</h2>
                <p className="text-sm text-[#a0a7b4]">Stand {data.as_of}</p>
              </div>
              <StatusChip tone="neutral">{data.mode === "daily" ? "% Tagesgewinn" : "% Wochenschnitt"}</StatusChip>
            </div>
            <SectorTable rows={data.rows} />
          </section>
          <section className="rounded border border-[#2d333d] bg-[#171a20] p-4">
            <div className="mb-4">
              <h2 className="text-base font-semibold">Ranking-Verlauf</h2>
              <p className="text-sm text-[#a0a7b4]">Letzte Perioden, Platz 1 ist der stärkste Sektor.</p>
            </div>
            <RankingHistory points={data.history} />
          </section>
        </>
      )}
    </div>
  );
}

function SectorSummary({
  direction,
  rows,
  title
}: {
  direction: "up" | "down";
  rows: SectorRankingRow[];
  title: string;
}) {
  const Icon = direction === "up" ? ArrowUpRight : ArrowDownRight;
  const tone = direction === "up" ? "text-emerald-300" : "text-rose-300";
  return (
    <section className="rounded border border-[#2d333d] bg-[#171a20] p-4">
      <div className="mb-4 flex items-center justify-between gap-3">
        <h2 className="text-base font-semibold">{title}</h2>
        <Icon className={tone} size={19} />
      </div>
      <div className="space-y-3">
        {rows.map((row) => (
          <div key={row.ticker} className="flex items-center justify-between gap-3 border-b border-[#242a33] pb-3 last:border-0 last:pb-0">
            <div>
              <div className="font-medium">{row.name}</div>
              <div className="text-xs text-[#77808f]">{row.ticker} · Rang {row.rank}</div>
            </div>
            <div className={["text-right text-lg font-semibold tabular-nums", row.return_pct >= 0 ? "text-emerald-200" : "text-rose-200"].join(" ")}>
              {formatPct(row.return_pct)}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function SectorTable({ rows }: { rows: SectorRankingRow[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[760px] border-collapse text-sm">
        <thead>
          <tr className="border-b border-[#2d333d] text-left text-xs uppercase text-[#77808f]">
            <th className="py-3 pr-3">Rang</th>
            <th className="px-3 py-3">Sektor</th>
            <th className="px-3 py-3 text-right">Aktuell</th>
            <th className="px-3 py-3 text-right">1D</th>
            <th className="px-3 py-3 text-right">5D</th>
            <th className="px-3 py-3 text-right">20D</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.ticker} className="border-b border-[#242a33] last:border-0">
              <td className="py-3 pr-3 tabular-nums text-[#d8dde6]">#{row.rank}</td>
              <td className="px-3 py-3">
                <div className="font-medium">{row.name}</div>
                <div className="text-xs text-[#77808f]">{row.ticker}</div>
              </td>
              <PctCell value={row.return_pct} />
              <PctCell value={row.return_1d_pct} />
              <PctCell value={row.return_5d_pct} />
              <PctCell value={row.return_20d_pct} />
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function RankingHistory({ points }: { points: SectorRankingPoint[] }) {
  const dates = Array.from(new Set(points.map((point) => point.date))).slice(-15);
  const sectors = Array.from(new Set(points.map((point) => point.ticker))).sort();
  const lookup = new Map(points.map((point) => [`${point.date}:${point.ticker}`, point]));

  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[900px] border-collapse text-xs">
        <thead>
          <tr className="border-b border-[#2d333d] text-left uppercase text-[#77808f]">
            <th className="py-3 pr-3">Sektor</th>
            {dates.map((date) => (
              <th key={date} className="px-2 py-3 text-center tabular-nums">
                {date.slice(5)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sectors.map((ticker) => {
            const first = points.find((point) => point.ticker === ticker);
            return (
              <tr key={ticker} className="border-b border-[#242a33] last:border-0">
                <td className="py-3 pr-3">
                  <div className="font-medium text-[#d8dde6]">{ticker}</div>
                  <div className="text-[#77808f]">{first?.name ?? ticker}</div>
                </td>
                {dates.map((date) => {
                  const item = lookup.get(`${date}:${ticker}`);
                  return (
                    <td key={date} className="px-2 py-3 text-center">
                      <span className={rankClass(item?.rank)}>{item ? `#${item.rank}` : "-"}</span>
                    </td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function PctCell({ value }: { value?: number | null }) {
  return (
    <td className={["px-3 py-3 text-right tabular-nums", pctClass(value)].join(" ")}>
      {value === null || value === undefined ? "-" : formatPct(value)}
    </td>
  );
}

function pctClass(value?: number | null) {
  if (value === null || value === undefined) return "text-[#77808f]";
  return value >= 0 ? "text-emerald-200" : "text-rose-200";
}

function rankClass(rank?: number) {
  if (!rank) return "text-[#77808f]";
  if (rank <= 3) return "rounded bg-emerald-300/10 px-2 py-1 text-emerald-100";
  if (rank >= 9) return "rounded bg-rose-300/10 px-2 py-1 text-rose-100";
  return "rounded bg-[#242a33] px-2 py-1 text-[#d8dde6]";
}

function formatPct(value: number) {
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
}
