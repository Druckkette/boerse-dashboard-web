"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { DatabaseZap, Play, RefreshCw, ServerCog } from "lucide-react";
import { StatusChip } from "@/components/ui/status-chip";
import { Sec13FMappingPanel } from "@/features/stocks/sec13f-mapping-panel";
import { api } from "@/lib/api/client";
import { qualityLabel } from "@/lib/format";
import type {
  DataDiagnostics,
  DataDiagnosticIssue,
  SystemReadiness,
  SystemReadinessCheck,
} from "@/lib/types/api";

export function DataMaintenancePanel() {
  const queryClient = useQueryClient();
  const diagnostics = useQuery({
    queryKey: ["settings-data-diagnostics"],
    queryFn: api.dataDiagnostics,
    staleTime: 60_000,
  });
  const readiness = useQuery({
    queryKey: ["system-readiness"],
    queryFn: api.readiness,
    staleTime: 15_000,
  });
  const job = useMutation({
    mutationFn: (issue: DataDiagnosticIssue) =>
      api.startJob({
        type: issue.job_type!,
        payload: { ...issue.job_payload, source: "settings_data_diagnostics" },
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["jobs"] });
      queryClient.invalidateQueries({
        queryKey: ["settings-data-diagnostics"],
      });
    },
  });
  return (
    <div className="space-y-4">
      <details
        id="system-status"
        className="scroll-mt-28 rounded-[14px] border border-[#e3e8ef] bg-white p-5"
      >
        <summary className="cursor-pointer font-semibold">
          Systemstatus und Diagnose
        </summary>
        <div className="mt-4">
          <SystemReadinessPanel
            data={readiness.data}
            isLoading={readiness.isLoading}
            onRefresh={() => readiness.refetch()}
          />
        </div>
      </details>
      <DataDiagnosticsPanel
        data={diagnostics.data}
        isLoading={diagnostics.isLoading}
        startingKey={job.isPending ? (job.variables?.key ?? null) : null}
        onRefresh={() => diagnostics.refetch()}
        onStartJob={(issue) => job.mutate(issue)}
      />
      {job.error && (
        <p
          role="alert"
          className="rounded border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700"
        >
          {job.error instanceof Error
            ? job.error.message
            : "Reparaturjob konnte nicht gestartet werden."}
        </p>
      )}
      <details
        id="data-management"
        className="scroll-mt-28 rounded-[14px] border border-[#e3e8ef] bg-white p-5"
      >
        <summary className="cursor-pointer font-semibold">
          Datenverwaltung · 13F CUSIP-Mapping
        </summary>
        <div className="mt-4">
          <Sec13FMappingPanel />
        </div>
      </details>
    </div>
  );
}

function DataDiagnosticsPanel({
  data,
  isLoading,
  startingKey,
  onRefresh,
  onStartJob,
}: {
  data?: DataDiagnostics;
  isLoading: boolean;
  startingKey: string | null;
  onRefresh: () => void;
  onStartJob: (issue: DataDiagnosticIssue) => void;
}) {
  if (isLoading) {
    return (
      <section
        id="data-quality"
        className="rounded-[14px] border border-[#e3e8ef] bg-white p-5 text-sm text-[#687386]"
      >
        Datenqualitätszentrum lädt...
      </section>
    );
  }

  if (!data) {
    return (
      <section
        id="data-quality"
        className="rounded-[14px] border border-[#f0b9b5] bg-[#fff0ef] p-5 text-sm text-[#c2413b]"
      >
        Datenqualitätszentrum ist aktuell nicht erreichbar.
      </section>
    );
  }

  return (
    <section
      id="data-quality"
      className="scroll-mt-28 rounded-[14px] border border-[#e3e8ef] bg-white p-5 shadow-[0_5px_18px_rgba(15,23,42,0.05)]"
    >
      <div className="mb-4 flex items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <DatabaseZap className="text-[#0f766e]" size={18} />
            <h2 className="text-base font-semibold text-[#172033]">
              Datenqualitätszentrum
            </h2>
          </div>
          <p className="mt-2 text-sm leading-5 text-[#687386]">
            {data.summary}
          </p>
        </div>
        <button
          aria-label="Datenqualität aktualisieren"
          className="flex size-9 items-center justify-center rounded-[9px] border border-[#d8e1ea] bg-white text-[#687386] transition hover:border-[#0f766e] hover:text-[#0f766e]"
          title="Datenqualität aktualisieren"
          type="button"
          onClick={onRefresh}
        >
          <RefreshCw size={15} />
        </button>
      </div>
      <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-5">
        <QualityMetric
          label="Entscheidungsstatus"
          value={qualityLabel(data.decision_status)}
          tone={data.health_tone}
        />
        <QualityMetric
          label="Stop-Abdeckung"
          value={`${Math.round(data.stop_coverage_pct)}%`}
          detail={`${data.stop_coverage_count}/${data.stop_coverage_total}`}
          tone={data.stop_coverage_pct >= 95 ? "good" : "warning"}
        />
        <QualityMetric
          label="Fehlende/veraltete Kurse"
          value={`${data.missing_price_count}/${data.stale_price_count}`}
          tone={
            data.missing_price_count
              ? "bad"
              : data.stale_price_count
                ? "warning"
                : "good"
          }
        />
        <QualityMetric
          label="Fundamentals fehlen"
          value={String(data.missing_fundamentals_count)}
          tone={data.missing_fundamentals_count ? "warning" : "good"}
        />
        <QualityMetric
          label="Plausibilitätsfehler"
          value={String(data.implausible_position_count)}
          tone={data.implausible_position_count ? "bad" : "good"}
        />
      </div>
      <div className="mt-4 grid gap-3 lg:grid-cols-2">
        {data.issues.map((issue) => (
          <div
            key={issue.key}
            className="rounded-[10px] border border-[#e3e8ef] bg-[#f9fbfd] p-3"
          >
            <div className="mb-2 flex items-start justify-between gap-3">
              <div>
                <div className="font-medium text-[#172033]">{issue.label}</div>
                <div className="mt-1 text-xs leading-5 text-[#687386]">
                  {issue.detail}
                </div>
              </div>
              <StatusChip tone={toneForSeverity(issue.severity)}>
                {severityLabel(issue.severity)}
              </StatusChip>
            </div>
            {issue.tickers.length > 0 && (
              <div className="mb-3 flex flex-wrap gap-1">
                {issue.tickers.slice(0, 10).map((ticker) => (
                  <span
                    key={ticker}
                    className="rounded-[7px] border border-[#d8e1ea] bg-white px-2 py-1 text-xs text-[#4b5565]"
                  >
                    {ticker}
                  </span>
                ))}
              </div>
            )}
            {issue.job_type && (
              <button
                className="inline-flex w-full items-center justify-center gap-2 rounded-[9px] border border-[#b7ddd6] bg-[#e8f4f2] px-3 py-2 text-sm font-semibold text-[#0f766e] transition hover:border-[#0f766e] disabled:cursor-not-allowed disabled:opacity-50"
                disabled={startingKey === issue.key}
                type="button"
                onClick={() => onStartJob(issue)}
              >
                <Play size={14} />
                {startingKey === issue.key
                  ? "Startet"
                  : issue.action_label || "Job starten"}
              </button>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}

function QualityMetric({
  label,
  value,
  detail,
  tone,
}: {
  label: string;
  value: string;
  detail?: string;
  tone: "good" | "neutral" | "warning" | "bad";
}) {
  const color =
    tone === "good"
      ? "text-[#138a57]"
      : tone === "bad"
        ? "text-[#c2413b]"
        : tone === "warning"
          ? "text-[#9a650f]"
          : "text-[#2563eb]";
  return (
    <div className="rounded-[10px] border border-[#e3e8ef] bg-[#f9fbfd] px-3 py-2.5">
      <div className="text-[10px] font-semibold uppercase tracking-[0.07em] text-[#687386]">
        {label}
      </div>
      <div className={`mt-1 text-lg font-semibold ${color}`}>{value}</div>
      {detail ? (
        <div className="mt-0.5 text-xs text-[#687386]">{detail}</div>
      ) : null}
    </div>
  );
}

function SystemReadinessPanel({
  data,
  isLoading,
  onRefresh,
}: {
  data?: SystemReadiness;
  isLoading: boolean;
  onRefresh: () => void;
}) {
  if (isLoading) {
    return (
      <section className="rounded-[14px] border border-[#e3e8ef] bg-white p-5 text-sm text-[#687386] shadow-[0_5px_18px_rgba(15,23,42,0.05)]">
        Systemstatus lädt...
      </section>
    );
  }

  if (!data) {
    return (
      <section className="rounded-[14px] border border-[#f0b9b5] bg-[#fff0ef] p-5 text-sm text-[#c2413b]">
        Systemstatus ist aktuell nicht erreichbar.
      </section>
    );
  }

  return (
    <section className="rounded-[14px] border border-[#e3e8ef] bg-white p-5 text-[#172033] shadow-[0_5px_18px_rgba(15,23,42,0.05)]">
      <div className="mb-4 flex items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <ServerCog className="text-[#2563eb]" size={18} />
            <h2 className="text-base font-semibold">Systemstatus</h2>
          </div>
          <p className="mt-2 text-sm leading-5 text-[#687386]">
            DB, Migrationen und Redis werden ohne Seitenblockade geprüft.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <StatusChip tone={toneForReadiness(data.status)}>
            {readinessLabel(data.status)}
          </StatusChip>
          <button
            aria-label="Systemstatus aktualisieren"
            className="flex size-9 items-center justify-center rounded-[9px] border border-[#d8e1ea] bg-white text-[#687386] transition hover:border-[#0f766e] hover:text-[#0f766e]"
            title="Systemstatus aktualisieren"
            type="button"
            onClick={onRefresh}
          >
            <RefreshCw size={15} />
          </button>
        </div>
      </div>
      <div className="space-y-3">
        {data.checks.map((check) => (
          <SystemCheckRow check={check} key={check.name} />
        ))}
      </div>
    </section>
  );
}

function SystemCheckRow({ check }: { check: SystemReadinessCheck }) {
  const revision =
    check.metadata.current_revision && check.metadata.head_revision
      ? `${String(check.metadata.current_revision)} / ${String(check.metadata.head_revision)}`
      : "";

  return (
    <div className="rounded-[10px] border border-[#e3e8ef] bg-[#f9fbfd] p-3 text-sm">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="font-medium">{systemCheckLabel(check.name)}</div>
          <div className="mt-1 text-xs leading-5 text-[#687386]">
            {check.detail}
          </div>
          {revision && (
            <div className="mt-1 text-xs text-[#687386]">
              Revision {revision}
            </div>
          )}
        </div>
        <StatusChip tone={toneForSystemCheck(check.status)}>
          {systemStatusLabel(check.status)}
        </StatusChip>
      </div>
      <div className="mt-2 flex items-center justify-between text-xs text-[#687386]">
        <span>{check.required ? "erforderlich" : "optional"}</span>
        <span>
          {check.latency_ms === null || check.latency_ms === undefined
            ? "-"
            : `${check.latency_ms} ms`}
        </span>
      </div>
    </div>
  );
}

function toneForSeverity(severity: DataDiagnosticIssue["severity"]) {
  if (severity === "critical") return "bad";
  if (severity === "warning") return "warning";
  return "neutral";
}

function toneForReadiness(status: SystemReadiness["status"]) {
  if (status === "ready") return "good";
  if (status === "degraded") return "warning";
  return "bad";
}

function readinessLabel(status: SystemReadiness["status"]) {
  if (status === "ready") return "Bereit";
  if (status === "degraded") return "Eingeschränkt";
  return "Nicht bereit";
}

function severityLabel(severity: DataDiagnosticIssue["severity"]) {
  return severity === "critical"
    ? "Kritisch"
    : severity === "warning"
      ? "Warnung"
      : "Hinweis";
}

function systemStatusLabel(status: SystemReadinessCheck["status"]) {
  return (
    (
      {
        ok: "In Ordnung",
        warning: "Warnung",
        unknown: "Unbekannt",
        error: "Fehler",
      } as Record<string, string>
    )[status] ?? status
  );
}

function toneForSystemCheck(status: SystemReadinessCheck["status"]) {
  if (status === "ok") return "good";
  if (status === "warning" || status === "unknown") return "warning";
  return "bad";
}

function systemCheckLabel(name: string) {
  if (name === "database") return "Datenbank";
  if (name === "migrations") return "Migrationen";
  if (name === "redis") return "Redis";
  return name;
}
