"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  CheckCircle2,
  CircleAlert,
  CircleDashed,
  DatabaseZap,
  Play,
  RefreshCw,
  Rocket,
  ServerCog,
  Upload,
  XCircle
} from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";
import { useState } from "react";
import { StatusChip } from "@/components/ui/status-chip";
import { RuntimeConfigPanel } from "@/features/setup/runtime-config-panel";
import { api } from "@/lib/api/client";
import type { Job, ServiceFreshness, SetupStep } from "@/lib/types/api";

export default function SetupPage() {
  const queryClient = useQueryClient();
  const [freshnessOpen, setFreshnessOpen] = useState(false);
  const setup = useQuery({
    queryKey: ["setup-status"],
    queryFn: api.setupStatus,
    refetchInterval: 5000,
    staleTime: 3000
  });
  const freshness = useQuery({
    queryKey: ["freshness"],
    queryFn: api.freshness,
    enabled: freshnessOpen,
    refetchInterval: freshnessOpen ? 15000 : false,
    staleTime: 5000
  });
  const activeJob = setup.data?.steps
    .map((step) => step.latest_job)
    .find((job): job is Job => Boolean(job && (job.status === "queued" || job.status === "running")));
  const nextStep = setup.data?.steps.find((step) => step.key === setup.data?.next_step_key);

  const startMutation = useMutation({
    mutationFn: (step: SetupStep) => {
      if (!step.job_type) throw new Error("Dieser Setup-Schritt hat keinen Job.");
      return api.startJob({
        type: step.job_type,
        payload: { ...step.job_payload, source: "setup" }
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["setup-status"] });
      queryClient.invalidateQueries({ queryKey: ["jobs"] });
      queryClient.invalidateQueries({ queryKey: ["freshness"] });
      queryClient.invalidateQueries({ queryKey: ["settings-data-diagnostics"] });
    }
  });

  const cancelMutation = useMutation({
    mutationFn: (jobId: string) => api.cancelJob(jobId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["setup-status"] });
      queryClient.invalidateQueries({ queryKey: ["jobs"] });
      queryClient.invalidateQueries({ queryKey: ["freshness"] });
      queryClient.invalidateQueries({ queryKey: ["settings-data-diagnostics"] });
    }
  });

  function refresh() {
    setup.refetch();
  }

  return (
    <div className="space-y-5">
      <section className="rounded border border-[#2d333d] bg-[#171a20] p-5">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <div className="mb-2 flex items-center gap-2 text-sm text-emerald-200">
              <Rocket size={18} />
              First Run
            </div>
            <h1 className="text-2xl font-semibold">Setup</h1>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-[#a0a7b4]">
              Erststart ohne Shell-Befehle: Depot importieren, Kursdaten laden, Marktanalyse vorbereiten,
              RS-Ratings berechnen und den ATR-Monitor anstoßen.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <StatusChip tone={setup.data ? toneForOverall(setup.data.status) : "neutral"}>
              {setup.data?.status ?? "lädt"}
            </StatusChip>
            <button
              className="inline-flex items-center gap-2 rounded border border-[#2d333d] bg-[#111419] px-3 py-2 text-sm transition hover:border-emerald-300/60"
              type="button"
              onClick={refresh}
            >
              <RefreshCw size={15} className={setup.isFetching ? "animate-spin text-emerald-300" : "text-[#a0a7b4]"} />
              Status
            </button>
          </div>
        </div>
      </section>

      <RuntimeConfigPanel />

      <div className="grid gap-4 xl:grid-cols-[1fr_380px]">
        <section className="space-y-4">
          {setup.isLoading && (
            <div className="rounded border border-[#2d333d] bg-[#171a20] p-5 text-sm text-[#a0a7b4]">
              Setup-Status lädt...
            </div>
          )}
          {setup.error && (
            <div className="rounded border border-rose-300/30 bg-rose-300/10 p-5 text-sm text-rose-100">
              {setup.error instanceof Error ? setup.error.message : "Setup-Status ist nicht erreichbar."}
            </div>
          )}
          {setup.data?.steps.map((step, index) => (
            <SetupStepCard
              activeJob={activeJob}
              cancellingJobId={cancelMutation.isPending ? cancelMutation.variables : null}
              index={index}
              key={step.key}
              onCancel={(jobId) => cancelMutation.mutate(jobId)}
              onStart={() => startMutation.mutate(step)}
              starting={startMutation.isPending && startMutation.variables?.key === step.key}
              step={step}
            />
          ))}
        </section>

        <aside className="space-y-4">
          <section className="rounded border border-[#2d333d] bg-[#171a20] p-5">
            <div className="mb-4 flex items-center justify-between gap-3">
              <div>
                <h2 className="text-base font-semibold">Nächste Aktion</h2>
                <div className="mt-1 text-sm text-[#a0a7b4]">{setup.data?.summary ?? "Status wird geprüft."}</div>
              </div>
              <Activity className="text-emerald-300" size={20} />
            </div>
            {nextStep ? (
              <NextStepAction
                activeJob={activeJob}
                onStart={() => startMutation.mutate(nextStep)}
                starting={startMutation.isPending && startMutation.variables?.key === nextStep.key}
                step={nextStep}
              />
            ) : (
              <div className="rounded border border-emerald-300/30 bg-emerald-300/10 p-3 text-sm text-emerald-100">
                Setup ist vollständig genug für den laufenden Betrieb.
              </div>
            )}
            {startMutation.error && (
              <div className="mt-3 rounded border border-rose-300/30 bg-rose-300/10 p-3 text-sm text-rose-100">
                {startMutation.error instanceof Error ? startMutation.error.message : "Job konnte nicht gestartet werden."}
              </div>
            )}
            {activeJob && (
              <div className="mt-3 rounded border border-amber-300/35 bg-amber-300/10 p-3 text-sm text-amber-100">
                <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                  <div className="min-w-0">
                    <div className="font-medium">Aktiver Worker-Job: {activeJob.job_type}</div>
                    <div className="mt-1 text-xs leading-5 text-amber-100/80">
                      {activeJob.current_step || activeJob.message || "Der Worker hat noch keinen Detailstatus gemeldet."}
                    </div>
                    <div className="mt-1 truncate text-xs text-amber-100/60">{activeJob.job_id}</div>
                  </div>
                  <button
                    className="inline-flex shrink-0 items-center justify-center gap-2 rounded border border-amber-200/50 bg-[#111419] px-3 py-2 text-xs text-amber-100 transition hover:border-rose-200/70 disabled:cursor-not-allowed disabled:opacity-50"
                    disabled={cancelMutation.isPending}
                    type="button"
                    onClick={() => cancelMutation.mutate(activeJob.job_id)}
                  >
                    <XCircle size={14} />
                    {cancelMutation.isPending && cancelMutation.variables === activeJob.job_id ? "Bricht ab" : "Job abbrechen"}
                  </button>
                </div>
              </div>
            )}
            {cancelMutation.error && (
              <div className="mt-3 rounded border border-rose-300/30 bg-rose-300/10 p-3 text-sm text-rose-100">
                {cancelMutation.error instanceof Error ? cancelMutation.error.message : "Job konnte nicht abgebrochen werden."}
              </div>
            )}
          </section>

          <section className="rounded border border-[#2d333d] bg-[#171a20] p-5">
            <h2 className="text-base font-semibold">Persistenz</h2>
            <div className="mt-4 space-y-3 text-sm">
              <InfoRow label="Import" value="Website" tone="good" />
              <InfoRow label="Marktdaten" value="Postgres" tone="good" />
              <InfoRow label="Refreshes" value="Worker" tone="neutral" />
              <InfoRow label="Wiederholung" value="nur bei Bedarf" tone="neutral" />
            </div>
            <p className="mt-4 text-sm leading-6 text-[#a0a7b4]">
              Der Bootstrap muss nicht nach jedem Container-Neustart wiederholt werden. Die Daten liegen im
              Postgres-Volume; erneutes Laden ist nur nach leerer Datenbank, Reset oder bewusst geänderter Historie nötig.
            </p>
          </section>

          <section className="rounded border border-[#2d333d] bg-[#171a20] p-5">
            <h2 className="text-base font-semibold">Direkte Ziele</h2>
            <div className="mt-4 grid gap-2">
              <QuickLink href="/portfolio/imports" icon={<Upload size={16} />} label="Depot importieren" />
              <QuickLink href="/jobs" icon={<DatabaseZap size={16} />} label="Jobs öffnen" />
              <QuickLink href="/settings" icon={<ServerCog size={16} />} label="Systemstatus prüfen" />
            </div>
          </section>

          <JobFreshnessPanel
            isFetching={freshness.isFetching}
            isLoading={freshness.isLoading}
            isOpen={freshnessOpen}
            onRefresh={() => freshness.refetch()}
            onToggle={() => setFreshnessOpen((value) => !value)}
            services={freshness.data?.services ?? []}
          />
        </aside>
      </div>
    </div>
  );
}

function SetupStepCard({
  activeJob,
  cancellingJobId,
  index,
  onCancel,
  onStart,
  starting,
  step
}: {
  activeJob?: Job;
  cancellingJobId: string | null;
  index: number;
  onCancel: (jobId: string) => void;
  onStart: () => void;
  starting: boolean;
  step: SetupStep;
}) {
  const latestJobIsActive = step.latest_job?.status === "running" || step.latest_job?.status === "queued";
  return (
    <section className="rounded border border-[#2d333d] bg-[#171a20] p-5">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="flex size-8 items-center justify-center rounded border border-[#2d333d] bg-[#111419] text-sm tabular-nums text-[#a0a7b4]">
              {index + 1}
            </span>
            {renderStepIcon(step)}
            <h2 className="text-base font-semibold">{step.label}</h2>
            <StatusChip tone={toneForStep(step.status)}>{labelForStepStatus(step.status)}</StatusChip>
          </div>
          <p className="mt-3 text-sm leading-6 text-[#a0a7b4]">{step.detail}</p>
          {step.latest_job && (
            <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-[#77808f]">
              <span>letzter Job: {step.latest_job.status}</span>
              <span>{step.latest_job.finished_at ? formatDate(step.latest_job.finished_at) : formatDate(step.latest_job.created_at)}</span>
            </div>
          )}
        </div>
        <StepAction activeJob={activeJob} onStart={onStart} starting={starting} step={step} />
      </div>
      {step.latest_job && latestJobIsActive && (
        <div className="mt-4">
          <div className="h-2 overflow-hidden rounded bg-[#111419]">
            <div className="h-2 rounded bg-emerald-300" style={{ width: `${step.latest_job.progress}%` }} />
          </div>
          <div className="mt-2 flex flex-col gap-2 text-xs text-[#77808f] sm:flex-row sm:items-center sm:justify-between">
            <div className="min-w-0">
              <div>{step.latest_job.current_step || step.latest_job.message}</div>
              <div className="mt-1 truncate text-[#697386]">{step.latest_job.job_id}</div>
            </div>
            <div className="flex shrink-0 items-center gap-3">
              <span className="tabular-nums">{step.latest_job.progress}%</span>
              <button
                className="inline-flex items-center gap-1 rounded border border-[#2d333d] bg-[#111419] px-2 py-1 text-xs text-[#d8dde6] transition hover:border-rose-300/60 disabled:cursor-not-allowed disabled:opacity-50"
                disabled={cancellingJobId === step.latest_job.job_id}
                type="button"
                onClick={() => onCancel(step.latest_job!.job_id)}
              >
                <XCircle size={13} />
                {cancellingJobId === step.latest_job.job_id ? "Abbruch" : "Abbrechen"}
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}

function NextStepAction({
  activeJob,
  onStart,
  starting,
  step
}: {
  activeJob?: Job;
  onStart: () => void;
  starting: boolean;
  step: SetupStep;
}) {
  return (
    <div className="rounded border border-[#242a33] bg-[#111419] p-3">
      <div className="mb-3 flex items-start justify-between gap-3">
        <div>
          <div className="font-medium">{step.label}</div>
          <div className="mt-1 text-xs leading-5 text-[#77808f]">{step.detail}</div>
        </div>
        <StatusChip tone={toneForStep(step.status)}>{labelForStepStatus(step.status)}</StatusChip>
      </div>
      <StepAction activeJob={activeJob} compact onStart={onStart} starting={starting} step={step} />
    </div>
  );
}

function StepAction({
  activeJob,
  compact = false,
  onStart,
  starting,
  step
}: {
  activeJob?: Job;
  compact?: boolean;
  onStart: () => void;
  starting: boolean;
  step: SetupStep;
}) {
  const actionLabel = step.action_label || "Öffnen";
  const activeElsewhere = Boolean(activeJob && activeJob.job_type !== step.job_type);
  const canStartJob = Boolean(
    step.job_type &&
      !activeElsewhere &&
      !starting &&
      step.status !== "blocked" &&
      step.status !== "error" &&
      step.status !== "running" &&
      step.status !== "complete"
  );

  if (step.href) {
    return (
      <Link
        className={[
          "inline-flex items-center justify-center gap-2 rounded border border-[#2d333d] bg-[#111419] px-3 py-2 text-sm transition hover:border-emerald-300/60",
          compact ? "w-full" : "min-w-40"
        ].join(" ")}
        href={step.href}
      >
        {step.key === "portfolio" ? <Upload size={15} /> : <CircleAlert size={15} />}
        {actionLabel}
      </Link>
    );
  }

  if (!step.job_type) {
    return (
      <div className={compact ? "text-sm text-[#77808f]" : "min-w-40 text-sm text-[#77808f]"}>
        Keine direkte Aktion
      </div>
    );
  }

  return (
    <button
      className={[
        "inline-flex items-center justify-center gap-2 rounded border border-emerald-300/35 bg-emerald-300/10 px-3 py-2 text-sm text-emerald-100 transition hover:border-emerald-200 disabled:cursor-not-allowed disabled:opacity-50",
        compact ? "w-full" : "min-w-40"
      ].join(" ")}
      disabled={!canStartJob}
      type="button"
      onClick={onStart}
    >
      <Play size={15} />
      {starting ? "Startet" : step.status === "warning" ? actionLabel || "Aktualisieren" : actionLabel || "Starten"}
    </button>
  );
}

function QuickLink({ href, icon, label }: { href: string; icon: ReactNode; label: string }) {
  return (
    <Link
      className="inline-flex items-center justify-between gap-3 rounded border border-[#2d333d] bg-[#111419] px-3 py-2 text-sm transition hover:border-emerald-300/60"
      href={href}
    >
      <span>{label}</span>
      <span className="text-emerald-300">{icon}</span>
    </Link>
  );
}

function InfoRow({
  label,
  tone = "neutral",
  value
}: {
  label: string;
  tone?: "good" | "neutral" | "warning" | "bad";
  value: string;
}) {
  return (
    <div className="flex items-center justify-between gap-3 border-b border-[#242a33] pb-3 last:border-b-0">
      <span className="text-[#a0a7b4]">{label}</span>
      <StatusChip tone={tone}>{value}</StatusChip>
    </div>
  );
}

function JobFreshnessPanel({
  isFetching,
  isLoading,
  isOpen,
  onRefresh,
  onToggle,
  services
}: {
  isFetching: boolean;
  isLoading: boolean;
  isOpen: boolean;
  onRefresh: () => void;
  onToggle: () => void;
  services: ServiceFreshness[];
}) {
  const staleCount = services.filter((service) => service.status !== "fresh").length;
  return (
    <section className="rounded border border-[#2d333d] bg-[#171a20] p-5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold">Job Freshness</h2>
          <p className="mt-1 text-sm leading-6 text-[#a0a7b4]">
            Datenstand von Price Cache, Marktanalyse, RS, 13F und Positionsmonitor.
          </p>
        </div>
        {isOpen && services.length > 0 ? (
          <StatusChip tone={staleCount === 0 ? "good" : "warning"}>
            {staleCount === 0 ? "aktuell" : `${staleCount} prüfen`}
          </StatusChip>
        ) : null}
      </div>
      <div className="mt-4 flex flex-wrap gap-2">
        <button
          className="inline-flex items-center gap-2 rounded border border-[#2d333d] bg-[#111419] px-3 py-2 text-sm transition hover:border-emerald-300/60"
          type="button"
          onClick={onToggle}
        >
          <DatabaseZap size={15} className="text-emerald-300" />
          {isOpen ? "Job Freshness schließen" : "Job Freshness öffnen"}
        </button>
        {isOpen ? (
          <button
            className="inline-flex items-center gap-2 rounded border border-[#2d333d] bg-[#111419] px-3 py-2 text-sm transition hover:border-emerald-300/60"
            type="button"
            onClick={onRefresh}
          >
            <RefreshCw size={15} className={isFetching ? "animate-spin text-emerald-300" : "text-[#a0a7b4]"} />
            Aktualisieren
          </button>
        ) : null}
      </div>
      {isOpen ? (
        <div className="mt-4 space-y-3">
          {isLoading ? (
            <div className="text-sm text-[#a0a7b4]">Freshness lädt...</div>
          ) : services.length === 0 ? (
            <div className="text-sm text-[#a0a7b4]">Noch keine Freshness-Daten verfügbar.</div>
          ) : (
            services.map((service) => (
              <div key={service.name} className="flex items-center justify-between gap-4 border-b border-[#242a33] pb-3 last:border-0 last:pb-0">
                <div className="min-w-0">
                  <div className="text-sm font-medium">{freshnessLabel(service.name)}</div>
                  <div className="text-xs text-[#a0a7b4]">Stand {service.as_of || "n/a"}</div>
                  {service.detail ? <div className="mt-1 text-xs leading-5 text-[#77808f]">{service.detail}</div> : null}
                </div>
                <StatusChip tone={freshnessTone(service.status)}>{service.status}</StatusChip>
              </div>
            ))
          )}
        </div>
      ) : null}
    </section>
  );
}

function freshnessLabel(name: string) {
  const labels: Record<string, string> = {
    prices: "Price-Cache allgemein",
    market_snapshot: "Market Snapshot",
    trend_benchmark: "Trend-Ampel Benchmark",
    market_breadth: "Marktbreite",
    relative_strength: "Relative Stärke",
    institutional_13f: "13F/SEC Trends",
    sell_ranking: "Positionsmonitor"
  };
  return labels[name] ?? name;
}

function freshnessTone(status: ServiceFreshness["status"]) {
  if (status === "fresh") return "good";
  if (status === "missing") return "bad";
  return "warning";
}

function renderStepIcon(step: SetupStep) {
  const className = step.status === "complete" ? "text-emerald-300" : "text-[#a0a7b4]";
  if (step.status === "complete") return <CheckCircle2 size={19} className={className} />;
  if (step.status === "error" || step.status === "blocked") {
    return <CircleAlert size={19} className={className} />;
  }
  if (step.status === "running") return <Activity size={19} className={className} />;
  return <CircleDashed size={19} className={className} />;
}

function toneForOverall(status: "ready" | "needs_action" | "running" | "blocked") {
  if (status === "ready") return "good";
  if (status === "running") return "warning";
  if (status === "blocked") return "bad";
  return "neutral";
}

function toneForStep(status: SetupStep["status"]) {
  if (status === "complete") return "good";
  if (status === "running" || status === "warning") return "warning";
  if (status === "error") return "bad";
  if (status === "blocked") return "bad";
  return "neutral";
}

function labelForStepStatus(status: SetupStep["status"]) {
  if (status === "complete") return "bereit";
  if (status === "pending") return "offen";
  if (status === "running") return "läuft";
  if (status === "warning") return "prüfen";
  if (status === "blocked") return "wartet";
  return "fehler";
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat("de-DE", {
    dateStyle: "short",
    timeStyle: "short"
  }).format(new Date(value));
}
