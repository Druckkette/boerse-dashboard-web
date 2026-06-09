"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Play, RotateCw, XCircle } from "lucide-react";
import { useState } from "react";
import { StatusChip } from "@/components/ui/status-chip";
import { api } from "@/lib/api/client";
import type { Job, JobStatus, JobType } from "@/lib/types/api";

const jobTypes: { type: JobType; label: string; description: string }[] = [
  { type: "refresh_prices", label: "Prices", description: "Inkrementelle OHLC-Aktualisierung" },
  { type: "refresh_breadth", label: "Breadth", description: "Marktbreite und Snapshots" },
  { type: "refresh_relative_strength", label: "RS Ratings", description: "Relative-Stärke-Ranking" },
  { type: "refresh_sec13f", label: "13F / SEC", description: "Institutionelle Artefakte, selten starten" },
  { type: "position_atr_monitor", label: "ATR Monitor", description: "Offene Positionen prüfen" }
];

const statusTone: Record<JobStatus, "good" | "neutral" | "warning" | "bad"> = {
  queued: "neutral",
  running: "warning",
  done: "good",
  failed: "bad",
  skipped: "neutral",
  cancelled: "neutral"
};

export default function JobsPage() {
  const queryClient = useQueryClient();
  const [selectedType, setSelectedType] = useState<JobType>("refresh_prices");
  const { data, isFetching, refetch } = useQuery({
    queryKey: ["jobs"],
    queryFn: api.jobs,
    refetchInterval: 5000
  });
  const jobs = data ?? [];
  const activeJob = jobs.find((job) => job.status === "queued" || job.status === "running");

  const startMutation = useMutation({
    mutationFn: () => api.startJob({ type: selectedType, payload: { mode: "manual" } }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["jobs"] })
  });

  const cancelMutation = useMutation({
    mutationFn: (jobId: string) => api.cancelJob(jobId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["jobs"] })
  });

  return (
    <div className="space-y-5">
      <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Jobs</h1>
          <p className="mt-1 text-sm text-[#a0a7b4]">
            Worker-Queue und Scheduler-Status; Polling ohne blockierende Oberfläche.
          </p>
        </div>
        <button
          className="inline-flex items-center gap-2 rounded border border-[#2d333d] bg-[#171a20] px-3 py-2 text-sm transition hover:border-emerald-300/60"
          type="button"
          onClick={() => refetch()}
        >
          <RotateCw size={15} className={isFetching ? "animate-spin text-emerald-300" : "text-[#a0a7b4]"} />
          Aktualisieren
        </button>
      </div>

      <section className="rounded border border-[#2d333d] bg-[#171a20] p-5">
        <div className="mb-4 flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <div>
            <h2 className="text-base font-semibold">Job manuell starten</h2>
            <div className="text-sm text-[#a0a7b4]">
              Auf NAS wird nur ein schwerer Job gleichzeitig angenommen.
            </div>
          </div>
          <StatusChip tone={activeJob ? "warning" : "good"}>
            {activeJob ? `aktiv: ${activeJob.job_type}` : "bereit"}
          </StatusChip>
        </div>
        <div className="grid gap-3 lg:grid-cols-[1fr_auto]">
          <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-5">
            {jobTypes.map((item) => (
              <button
                key={item.type}
                className={[
                  "rounded border px-3 py-3 text-left text-sm transition",
                  selectedType === item.type
                    ? "border-emerald-300/60 bg-emerald-300/10"
                    : "border-[#2d333d] bg-[#111419] hover:border-[#697386]"
                ].join(" ")}
                type="button"
                onClick={() => setSelectedType(item.type)}
              >
                <div className="font-medium">{item.label}</div>
                <div className="mt-1 text-xs text-[#a0a7b4]">{item.description}</div>
              </button>
            ))}
          </div>
          <button
            className="inline-flex items-center justify-center gap-2 rounded border border-emerald-300/40 bg-emerald-300/10 px-4 py-3 text-sm text-emerald-100 transition hover:border-emerald-200 disabled:cursor-not-allowed disabled:opacity-50"
            disabled={Boolean(activeJob) || startMutation.isPending}
            type="button"
            onClick={() => startMutation.mutate()}
          >
            <Play size={16} />
            {startMutation.isPending ? "Startet" : "Starten"}
          </button>
        </div>
        {startMutation.isError && (
          <div className="mt-3 text-sm text-rose-200">
            {startMutation.error instanceof Error ? startMutation.error.message : "Job konnte nicht gestartet werden."}
          </div>
        )}
      </section>

      <div className="space-y-3">
        {jobs.length === 0 && (
          <div className="rounded border border-[#2d333d] bg-[#171a20] p-5 text-sm text-[#a0a7b4]">
            Noch keine Jobs vorhanden. Das Frontend bleibt auch ohne laufenden Worker nutzbar.
          </div>
        )}
        {jobs.map((job) => (
          <JobRow key={job.job_id} job={job} onCancel={(jobId) => cancelMutation.mutate(jobId)} />
        ))}
      </div>
    </div>
  );
}

function JobRow({ job, onCancel }: { job: Job; onCancel: (jobId: string) => void }) {
  const canCancel = job.status === "queued" || job.status === "running";
  return (
    <section className="rounded border border-[#2d333d] bg-[#171a20] p-4">
      <div className="flex flex-col justify-between gap-3 md:flex-row md:items-start">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-base font-semibold">{job.job_type}</h2>
            <StatusChip tone={statusTone[job.status]}>{job.status}</StatusChip>
          </div>
          <div className="mt-1 text-sm text-[#a0a7b4]">{job.current_step || job.message}</div>
          <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-[#77808f]">
            <span>{job.job_id}</span>
            <span>requested by {job.requested_by}</span>
            <span>{formatDate(job.created_at)}</span>
          </div>
        </div>
        {canCancel && (
          <button
            className="inline-flex items-center justify-center gap-2 rounded border border-[#2d333d] bg-[#111419] px-3 py-2 text-sm transition hover:border-rose-300/60"
            type="button"
            onClick={() => onCancel(job.job_id)}
          >
            <XCircle size={15} />
            Cancel
          </button>
        )}
      </div>

      <div className="mt-4 h-2 overflow-hidden rounded bg-[#111419]">
        <div
          className={job.status === "failed" ? "h-2 rounded bg-rose-300" : "h-2 rounded bg-emerald-300"}
          style={{ width: `${job.progress}%` }}
        />
      </div>
      <div className="mt-2 text-right text-xs tabular-nums text-[#a0a7b4]">{job.progress}%</div>

      <details className="mt-3 rounded border border-[#242a33] bg-[#111419] p-3 text-sm">
        <summary className="cursor-pointer text-[#d8dde6]">Details</summary>
        <div className="mt-3 grid gap-3 lg:grid-cols-2">
          <JsonBlock title="Payload" value={job.payload} />
          <JsonBlock title="Result" value={job.result} />
        </div>
        {job.error_message && (
          <div className="mt-3 rounded border border-rose-300/30 bg-rose-300/10 p-3 text-rose-100">
            {job.error_message}
          </div>
        )}
      </details>
    </section>
  );
}

function JsonBlock({ title, value }: { title: string; value: Record<string, unknown> }) {
  return (
    <div>
      <div className="mb-1 text-xs uppercase text-[#a0a7b4]">{title}</div>
      <pre className="max-h-44 overflow-auto rounded border border-[#242a33] bg-[#0f1115] p-3 text-xs text-[#d8dde6]">
        {JSON.stringify(value, null, 2)}
      </pre>
    </div>
  );
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat("de-DE", {
    dateStyle: "short",
    timeStyle: "short"
  }).format(new Date(value));
}
