"use client";
import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { RefreshCw } from "lucide-react";
import Link from "next/link";
import { api, type BetaRefresh } from "@/lib/api/client";
import { StatusChip } from "@/components/ui/status-chip";
import { betaRefreshQueryKeys, shouldAutoRefresh, refreshPollInterval } from "@/lib/beta/refresh-state";

export function BetaStockDetailActions({ ticker }: { ticker: string }) {
  const client = useQueryClient();
  const attempted = useRef(false);
  const handled = useRef<string | null>(null);
  const [started, setStarted] = useState<BetaRefresh | null>(null);
  const freshness = useQuery({ queryKey: ["beta-freshness", ticker], queryFn: () => api.betaFreshness(ticker), staleTime: 60_000 });
  const refresh = useMutation({ mutationFn: (mode: "auto" | "manual") => api.betaRefresh(ticker, mode), retry: false,
    onSuccess: (job) => { setStarted(job); handled.current = null; if (job.job_id) void client.invalidateQueries({ queryKey: ["beta-refresh-status", job.job_id] }); } });
  const status = useQuery({ queryKey: ["beta-refresh-status", started?.job_id], queryFn: () => api.betaRefreshStatus(started!),
    enabled: Boolean(started?.job_id), refetchInterval: (query) => query.state.error ? false : refreshPollInterval(query.state.data), retry: false });
  const job = status.data || started;
  const busy = refresh.isPending || Boolean(job && !job.finished && !status.error);
  useEffect(() => {
    if (!shouldAutoRefresh(freshness.data, attempted.current)) return;
    attempted.current = true;
    refresh.mutate("auto");
  }, [freshness.data, refresh]);
  useEffect(() => {
    if (!job?.finished || !job.job_id || handled.current === job.job_id) return;
    handled.current = job.job_id;
    for (const queryKey of betaRefreshQueryKeys(ticker)) void client.invalidateQueries({ queryKey });
  }, [client, job, ticker]);
  const error = refresh.error || status.error || freshness.error;
  return <section className="space-y-3 rounded-[14px] border border-[#e3e8ef] bg-white p-4">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div className="flex flex-wrap items-center gap-2"><b>{ticker}</b><StatusChip tone={freshness.data?.fresh ? "good" : "warning"}>{freshness.data?.fresh ? "Aktuell" : freshness.isLoading ? "Daten werden geprüft" : "Veraltet / unvollständig"}</StatusChip><span className="text-xs text-[#687386]">Datenstand: {freshness.data?.as_of || "fehlt"}</span></div>
      <button type="button" disabled={busy} onClick={() => refresh.mutate("manual")} className="inline-flex items-center gap-2 rounded-[9px] bg-[#0f766e] px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"><RefreshCw size={16} className={busy ? "animate-spin" : ""} />{busy ? "Aktualisierung läuft" : "Aktie aktualisieren"}</button>
    </div>
    {job?.job_id && <div role="status"><p className="text-sm">{job.joined || started?.joined ? "Diese Aktie wird bereits aktualisiert. " : ""}{job.finished ? job.status === "done" ? "Aktualisierung abgeschlossen." : "Aktualisierung beendet." : job.status === "queued" ? "Aktie wartet auf den Worker." : "Aktie wird aktualisiert."}</p><progress max={100} value={job.progress || 0} className="mt-2 h-2 w-full accent-teal-700" aria-label="Aktienrefresh-Fortschritt" /></div>}
    {(error || job?.error) && <p role="alert" className="text-sm text-[#c2413b]">{job?.error || (error instanceof Error ? error.message : "Bitte später erneut versuchen.")}</p>}
    <Link className="text-sm font-semibold text-[#0f766e]" href="/sell-check">Aktie frei auf Verkaufssignale prüfen →</Link>
  </section>;
}
