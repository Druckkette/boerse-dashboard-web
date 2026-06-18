"use client";

import { useQuery } from "@tanstack/react-query";
import { LineChartCard } from "@/components/ui/line-chart-card";
import { StatusChip } from "@/components/ui/status-chip";
import { api } from "@/lib/api/client";

export function StockRsPanel({ ticker }: { ticker: string }) {
  const clean = ticker.toUpperCase();
  const query = useQuery({
    queryKey: ["stock-rs", clean],
    queryFn: () => api.stockRs(clean),
    staleTime: 60_000
  });
  const item = query.data?.item;

  return (
    <section className="rounded border border-[#2d333d] bg-[#171a20] p-5">
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">Relative Stärke</h2>
          <div className="mt-1 text-sm text-[#a0a7b4]">
            {item ? `Stand ${item.date}, Universe ${item.universe_size}` : "Noch kein gespeichertes RS-Rating."}
          </div>
        </div>
        <StatusChip tone={item ? toneForRating(item.rating) : "warning"}>{item?.rating ?? "fehlt"}</StatusChip>
      </div>

      {query.isLoading && <div className="text-sm text-[#a0a7b4]">Lädt...</div>}
      {query.isError && (
        <div className="text-sm text-rose-200">
          {query.error instanceof Error ? query.error.message : "RS-Rating konnte nicht geladen werden."}
        </div>
      )}
      {!query.isLoading && !query.isError && !item && (
        <div className="text-sm text-[#a0a7b4]">
          Nach Prices und RS Ratings erscheint hier das Rating aus dem Price Cache.
        </div>
      )}
      {item && (
        <div className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <Metric label="Percentile" value={formatPct(item.percentile)} />
            <Metric label="3M Return" value={formatPct(item.ret_3m)} tone={pctTone(item.ret_3m)} />
            <Metric label="6M vs SPY" value={formatPct(item.excess_return_6m)} tone={pctTone(item.excess_return_6m)} />
            <Metric label="RS High" value={item.new_high_52w ? "New High" : item.near_high_52w ? "Near High" : "Off High"} />
          </div>
          <LineChartCard
            caption={
              item.rs_history.length
                ? `${item.rs_history.length} RS-Punkte gegen SPY, Start = 100`
                : "RS-Historie wird beim nächsten RS-Refresh erzeugt."
            }
            points={item.rs_history.map((point) => ({
              date: point.date,
              rs: point.rs,
              rsEma21: point.rs_ema21,
              rsEma50: point.rs_ema50
            }))}
            series={[
              { key: "rs", label: "RS vs SPY", color: "#f472b6", formatter: (value) => value.toFixed(2) },
              { key: "rsEma21", label: "21-EMA RS", color: "#38bdf8", formatter: (value) => value.toFixed(2) },
              { key: "rsEma50", label: "50-EMA RS", color: "#fbbf24", formatter: (value) => value.toFixed(2) }
            ]}
            statusLabel={item.rs_history.length ? "RS Chart" : "Refresh nötig"}
            statusTone={item.rs_history.length ? "good" : "warning"}
            title={`${clean} Relative Stärke Chart`}
          />
        </div>
      )}
    </section>
  );
}

function Metric({
  label,
  value,
  tone = "neutral"
}: {
  label: string;
  value: string;
  tone?: "good" | "neutral" | "warning" | "bad";
}) {
  return (
    <div className="rounded border border-[#242a33] bg-[#111419] p-4">
      <div className="mb-2 flex items-center justify-between gap-2">
        <div className="text-xs uppercase text-[#a0a7b4]">{label}</div>
        <StatusChip tone={tone}>{tone}</StatusChip>
      </div>
      <div className="text-xl font-semibold">{value}</div>
    </div>
  );
}

function formatPct(value?: number | null) {
  if (typeof value !== "number" || Number.isNaN(value)) return "-";
  return `${value >= 0 ? "+" : ""}${value.toFixed(1)}%`;
}

function pctTone(value?: number | null): "good" | "neutral" | "warning" | "bad" {
  if (typeof value !== "number") return "neutral";
  if (value >= 10) return "good";
  if (value >= 0) return "neutral";
  if (value >= -10) return "warning";
  return "bad";
}

function toneForRating(value?: number | null): "good" | "neutral" | "warning" | "bad" {
  if (typeof value !== "number") return "neutral";
  if (value >= 80) return "good";
  if (value >= 60) return "neutral";
  if (value >= 40) return "warning";
  return "bad";
}
