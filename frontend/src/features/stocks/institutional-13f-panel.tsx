"use client";

import { Building2, Loader2, RefreshCw, TrendingDown, TrendingUp } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { StatusChip } from "@/components/ui/status-chip";
import { api } from "@/lib/api/client";
import type { Institutional13FTrendItem, Job, Tone } from "@/lib/types/api";

export function Institutional13FPanel({ ticker }: { ticker: string }) {
  const clean = ticker.toUpperCase();
  const queryClient = useQueryClient();
  const [refreshJobId, setRefreshJobId] = useState<string | null>(null);
  const handledRefreshJobId = useRef<string | null>(null);
  const query = useQuery({
    queryKey: ["institutional-13f", clean],
    queryFn: () => api.stockInstitutional13F(clean),
    staleTime: 5 * 60_000
  });
  const refreshJobQuery = useQuery({
    queryKey: ["job", refreshJobId],
    queryFn: () => api.job(refreshJobId ?? ""),
    enabled: Boolean(refreshJobId),
    refetchInterval: (pollQuery) => {
      const job = pollQuery.state.data as Job | undefined;
      return job && isTerminalJob(job) ? false : 1500;
    }
  });
  const refreshMutation = useMutation({
    mutationFn: () =>
      api.startJob({
        type: "refresh_sec13f",
        payload: {
          mode: "stock_detail",
          source: "stock_detail",
          tickers: [clean],
          limit_universe: 1,
          dataset_count: 2
        }
      }),
    onSuccess: (job) => {
      setRefreshJobId(job.job_id);
      handledRefreshJobId.current = null;
      void queryClient.invalidateQueries({ queryKey: ["jobs"] });
    }
  });
  const item = query.data?.item;
  const refreshJob = refreshJobQuery.data;
  const refreshRunning = Boolean(refreshJob && !isTerminalJob(refreshJob));

  useEffect(() => {
    if (!refreshJob || !isTerminalJob(refreshJob) || handledRefreshJobId.current === refreshJob.job_id) return;
    handledRefreshJobId.current = refreshJob.job_id;
    void queryClient.invalidateQueries({ queryKey: ["institutional-13f", clean] });
    void queryClient.invalidateQueries({ queryKey: ["stock-assessment", clean] });
    void queryClient.invalidateQueries({ queryKey: ["stock-assessment-ranking"] });
    void queryClient.invalidateQueries({ queryKey: ["jobs"] });
  }, [clean, queryClient, refreshJob]);

  return (
    <section className="rounded border border-[#2d333d] bg-[#171a20] p-5">
      <div className="mb-4 flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <Building2 className="size-5 text-[#8ea4c8]" />
            <h2 className="text-lg font-semibold">Institutionelle 13F-Trends</h2>
          </div>
          <p className="mt-1 text-sm text-[#a0a7b4]">
            {item ? `${item.previous_period ?? "-"} bis ${item.report_period}` : "Noch keine gespeicherten 13F-Trends."}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <StatusChip tone={item ? toneForTrend(item.trend) : "warning"}>{item ? trendLabel(item.trend) : "Keine Daten"}</StatusChip>
          <button
            className="inline-flex h-9 items-center justify-center gap-2 rounded border border-sky-300/30 bg-sky-400/10 px-3 text-sm font-medium text-sky-100 transition hover:bg-sky-400/15 disabled:cursor-not-allowed disabled:opacity-50"
            disabled={refreshMutation.isPending || refreshRunning}
            type="button"
            onClick={() => refreshMutation.mutate()}
          >
            {refreshMutation.isPending || refreshRunning ? <Loader2 className="size-4 animate-spin" /> : <RefreshCw className="size-4" />}
            {refreshRunning ? "13F läuft" : "13F für Aktie laden"}
          </button>
        </div>
      </div>

      {query.isLoading && <div className="text-sm text-[#a0a7b4]">Lädt...</div>}
      {query.isError && <div className="text-sm text-rose-200">13F-Trend konnte nicht geladen werden.</div>}
      {refreshMutation.isError && (
        <div className="mb-4 rounded border border-rose-300/25 bg-rose-950/20 p-3 text-sm text-rose-100">
          13F-Refresh konnte nicht gestartet werden. Prüfe, ob bereits ein Worker-Job läuft.
        </div>
      )}
      {refreshJob?.status === "failed" && (
        <div className="mb-4 rounded border border-rose-300/25 bg-rose-950/20 p-3 text-sm text-rose-100">
          {refreshJob.error_message || "13F-Refresh ist fehlgeschlagen."}
        </div>
      )}
      {refreshJob && refreshJob.status !== "failed" ? (
        <div className="mb-4 rounded border border-emerald-300/20 bg-emerald-950/20 p-3 text-sm text-emerald-100">
          {refreshRunning
            ? `${refreshJob.current_step || "13F-Refresh läuft"} · ${refreshJob.progress}%`
            : "13F-Refresh wurde abgeschlossen. Die Detaildaten wurden neu geladen."}
        </div>
      ) : null}
      {!query.isLoading && !query.isError && !item && (
        <div className="rounded border border-dashed border-[#4b5563] bg-[#111419] p-5 text-sm text-[#a0a7b4]">
          Lade 13F direkt für {clean}. Der Worker nutzt die offiziellen SEC-Datensätze und speichert danach
          aggregierte Ticker-Trends, sofern der Ticker im aktuellen 13F-Universum gefunden wird. 13F-Trends brauchen
          ein passendes SEC-CUSIP-Mapping und mindestens zwei vergleichbare Berichtsperioden.
        </div>
      )}
      {item && (
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          <Metric label="Große Institutionen" value={number(item.large_holder_count)} detail={delta(item.large_holder_delta)} trend={item.large_holder_delta} />
          <Metric label="Alle 13F-Halter" value={number(item.holder_count)} detail={delta(item.holder_count_delta)} trend={item.holder_count_delta} />
          <Metric label="Marktwert" value={usd(item.total_value_usd)} detail={pct(item.total_value_delta_pct)} trend={item.total_value_delta_pct} />
          <Metric label="Aktien" value={compact(item.total_shares)} detail={pct(item.total_shares_delta_pct)} trend={item.total_shares_delta_pct} />
        </div>
      )}
    </section>
  );
}

function Metric({
  label,
  value,
  detail,
  trend
}: {
  label: string;
  value: string;
  detail: string;
  trend?: number | null;
}) {
  const positive = typeof trend === "number" && trend > 0;
  const negative = typeof trend === "number" && trend < 0;
  return (
    <div className="rounded border border-[#242a33] bg-[#111419] p-4">
      <div className="mb-2 flex items-center justify-between gap-2">
        <div className="text-xs uppercase text-[#a0a7b4]">{label}</div>
        {positive ? <TrendingUp className="size-4 text-emerald-300" /> : negative ? <TrendingDown className="size-4 text-rose-300" /> : null}
      </div>
      <div className="text-xl font-semibold tabular-nums">{value}</div>
      <div className={negative ? "mt-1 text-xs text-rose-200" : positive ? "mt-1 text-xs text-emerald-200" : "mt-1 text-xs text-[#7f8794]"}>
        {detail}
      </div>
    </div>
  );
}

function toneForTrend(trend: Institutional13FTrendItem["trend"]): Tone {
  if (trend === "positive" || trend === "new") return "good";
  if (trend === "negative") return "bad";
  if (trend === "neutral") return "neutral";
  return "warning";
}

function trendLabel(trend: Institutional13FTrendItem["trend"]) {
  return ({ positive: "Positiv", negative: "Negativ", neutral: "Neutral", new: "Neu", missing: "Keine Daten" } as Record<string, string>)[trend] ?? "Keine Daten";
}

function isTerminalJob(job: Job) {
  return ["done", "failed", "skipped", "cancelled"].includes(job.status);
}

function number(value?: number | null) {
  if (typeof value !== "number") return "-";
  return value.toLocaleString("de-DE");
}

function delta(value?: number | null) {
  if (typeof value !== "number") return "-";
  return `${value >= 0 ? "+" : ""}${value.toLocaleString("de-DE")} vs. Vorquartal`;
}

function pct(value?: number | null) {
  if (typeof value !== "number") return "-";
  return `${value >= 0 ? "+" : ""}${value.toFixed(1)}%`;
}

function usd(value?: number | null) {
  if (typeof value !== "number") return "-";
  if (value >= 1_000_000_000) return `$${(value / 1_000_000_000).toFixed(1)} Mrd.`;
  if (value >= 1_000_000) return `$${(value / 1_000_000).toFixed(1)} Mio.`;
  return `$${value.toLocaleString("de-DE", { maximumFractionDigits: 0 })}`;
}

function compact(value?: number | null) {
  if (typeof value !== "number") return "-";
  if (value >= 1_000_000_000) return `${(value / 1_000_000_000).toFixed(1)} Mrd.`;
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)} Mio.`;
  return value.toLocaleString("de-DE", { maximumFractionDigits: 0 });
}
