"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowRight,
  BellRing,
  DatabaseZap,
  Play,
  RefreshCw,
  Rocket,
  ServerCog,
  SlidersHorizontal,
  Upload
} from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { StatusChip } from "@/components/ui/status-chip";
import { Sec13FMappingPanel } from "@/features/stocks/sec13f-mapping-panel";
import { api } from "@/lib/api/client";
import type {
  AppSettings,
  DataDiagnosticIssue,
  DataDiagnostics,
  SystemReadiness,
  SystemReadinessCheck
} from "@/lib/types/api";

const fallbackSettings: AppSettings = {
  atr_threshold: 1.5,
  risk_per_position_pct: 1,
  target_risk_contribution: 0.2,
  max_depot_loss_lower_pct: 4,
  max_depot_loss_upper_pct: 8,
  position_monitor_enabled: false,
  position_monitor_interval_minutes: 1,
  position_monitor_threshold_atr: 1.5,
  position_monitor_atr_period: 14,
  position_monitor_lookback_days: 420,
  position_monitor_cooldown_hours: 18,
  position_monitor_reference: "previous_close",
  pushover_enabled: false,
  pushover_configured: false,
  rs_rating_source: "computed",
  data_jobs_enabled: true
};

export function SettingsPanel() {
  const queryClient = useQueryClient();
  const { data } = useQuery({ queryKey: ["settings"], queryFn: api.settings });
  const dataDiagnostics = useQuery({
    queryKey: ["settings-data-diagnostics"],
    queryFn: api.dataDiagnostics,
    staleTime: 60_000
  });
  const readiness = useQuery({
    queryKey: ["system-readiness"],
    queryFn: api.readiness,
    refetchInterval: 30_000,
    staleTime: 15_000
  });
  const [local, setLocal] = useState<AppSettings | null>(null);
  const [dirty, setDirty] = useState(false);
  const settings = local ?? data ?? fallbackSettings;

  const mutation = useMutation({
    mutationFn: api.patchSettings,
    onSuccess: (updated) => {
      queryClient.setQueryData(["settings"], updated);
      setLocal(null);
      setDirty(false);
    }
  });
  const pushoverMutation = useMutation({
    mutationFn: () =>
      api.startJob({
        type: "pushover_test",
        payload: { mode: "manual", source: "settings" }
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["jobs"] })
  });
  const diagnosticJobMutation = useMutation({
    mutationFn: (issue: DataDiagnosticIssue) =>
      api.startJob({
        type: issue.job_type!,
        payload: { ...issue.job_payload, source: "settings_data_diagnostics" }
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["jobs"] });
      queryClient.invalidateQueries({ queryKey: ["settings-data-diagnostics"] });
    }
  });

  useEffect(() => {
    if (!dirty) return;
    const handle = window.setTimeout(() => {
      mutation.mutate(settings);
    }, 550);
    return () => window.clearTimeout(handle);
  }, [dirty, mutation, settings]);

  function update<K extends keyof AppSettings>(key: K, value: AppSettings[K]) {
    setLocal((current) => ({ ...(current ?? data ?? fallbackSettings), [key]: value }));
    setDirty(true);
  }

  function updateNumber(key: keyof AppSettings, value: number, min: number, max: number, step = 0.1) {
    const rounded = Math.round(value / step) * step;
    update(key, Math.max(min, Math.min(max, Number(rounded.toFixed(4)))) as never);
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-end gap-2">
        <StatusChip tone={mutation.isPending ? "warning" : dirty ? "neutral" : "good"}>
          {mutation.isPending ? "speichert" : dirty ? "lokal geändert" : "persistiert"}
        </StatusChip>
        <SlidersHorizontal className="text-[#0f766e]" size={18} />
      </div>

      <SettingsWorkflowLinks />

      <details className="group rounded-[14px] border border-[#e3e8ef] bg-white p-4 shadow-[0_5px_18px_rgba(15,23,42,0.05)]">
        <summary className="cursor-pointer list-none">
          <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
            <div>
              <h2 className="text-base font-semibold">13F CUSIP-Mapping</h2>
              <p className="mt-0.5 text-xs leading-5 text-[#687386]">
                SEC-CUSIPs auf Ticker mappen, damit institutionelle 13F-Trends korrekt Aktien zugeordnet werden.
              </p>
            </div>
            <StatusChip tone="neutral">einklappbar</StatusChip>
          </div>
        </summary>
        <div className="mt-4">
          <Sec13FMappingPanel />
        </div>
      </details>

      <div className="grid gap-4 xl:grid-cols-[1fr_380px]">
        <section className="space-y-4">
          <SettingCard
            description="Ein eigener Monitor-Worker prüft offene Positionen werktags jede Minute mit einem gemeinsamen Yahoo-Intraday-Abruf. Schwere Datenjobs können ATR-Alarme dadurch nicht mehr verzögern."
            title="Positionsmonitor"
            value={settings.position_monitor_enabled ? "aktiv" : "aus"}
          >
            <div className="grid gap-3 md:grid-cols-2">
              <label className="flex items-center justify-between gap-3 rounded border border-[#2d333d] bg-[#111419] px-3 py-2 text-sm">
                <span>Monitor aktiv</span>
                <input
                  checked={settings.position_monitor_enabled}
                  className="size-4 accent-emerald-300"
                  type="checkbox"
                  onChange={(event) => update("position_monitor_enabled", event.target.checked)}
                />
              </label>
              <Field label="Referenz">
                <select
                  className="input-dark"
                  value={settings.position_monitor_reference}
                  onChange={(event) =>
                    update(
                      "position_monitor_reference",
                      event.target.value as AppSettings["position_monitor_reference"]
                    )
                  }
                >
                  <option value="high_since_buy">High seit Kauf</option>
                  <option value="close_since_buy">Close seit Kauf</option>
                  <option value="entry_price">Einstand</option>
                  <option value="previous_close">Vortagesschluss</option>
                </select>
              </Field>
              <p className="rounded border border-[#2d333d] bg-[#111419] px-3 py-2 text-xs leading-5 text-[#a0a7b4] md:col-span-2">
                Bei Vortagesschluss wird nur der ATR-Verlust unter dem vorherigen Handelstagesschluss
                bewertet. Der Cooldown wird an einem neuen Handelstag ab 07:30 Uhr deutscher Zeit
                nur dann erneut ausgelöst, wenn die Referenz oder der Verlust wirklich neu ist.
                Am selben Tag eskaliert der Monitor erneut bei 2x ATR-Schwelle. Ein Alarm gilt
                erst nach bestätigter Pushover-Zustellung als versendet. Der Scheduler prüft
                an Handelstagen zwischen 08:00 und 02:00 Uhr inklusive US-Nachbörse jede Minute.
              </p>
              <NumberField
                label="ATR Schwelle"
                max={10}
                min={0.5}
                step={0.1}
                value={settings.position_monitor_threshold_atr}
                onChange={(value) => updateNumber("position_monitor_threshold_atr", value, 0.5, 10)}
              />
              <NumberField
                label="ATR Periode"
                max={63}
                min={5}
                step={1}
                value={settings.position_monitor_atr_period}
                onChange={(value) => updateNumber("position_monitor_atr_period", value, 5, 63, 1)}
              />
              <NumberField
                label="Lookback Tage"
                max={740}
                min={30}
                step={5}
                value={settings.position_monitor_lookback_days}
                onChange={(value) => updateNumber("position_monitor_lookback_days", value, 30, 740, 5)}
              />
            </div>
          </SettingCard>

          <SettingCard description="Worker dürfen schwere Datenjobs starten; UI-Clicks bleiben davon getrennt." title="Datenjobs" value={settings.data_jobs_enabled ? "aktiv" : "aus"}>
            <div className="grid gap-3 md:grid-cols-2">
              <label className="flex items-center justify-between gap-3 rounded border border-[#2d333d] bg-[#111419] px-3 py-2 text-sm">
                <span>Datenjobs aktiv</span>
                <input
                  checked={settings.data_jobs_enabled}
                  className="size-4 accent-emerald-300"
                  type="checkbox"
                  onChange={(event) => update("data_jobs_enabled", event.target.checked)}
                />
              </label>
              <Field label="RS Quelle">
                <select
                  className="input-dark"
                  value={settings.rs_rating_source}
                  onChange={(event) => update("rs_rating_source", event.target.value as AppSettings["rs_rating_source"])}
                >
                  <option value="computed">Computed aus Kursdaten</option>
                  <option value="csv_latest">CSV Latest</option>
                </select>
              </Field>
            </div>
          </SettingCard>

          <SettingCard
            description="Secrets bleiben in der Container-Umgebung. Die Oberfläche speichert nur, ob Alerts genutzt werden sollen."
            title="Pushover"
            value={settings.pushover_configured ? "konfiguriert" : "Secrets fehlen"}
          >
            <div className="grid gap-3 md:grid-cols-2">
              <label className="flex items-center justify-between gap-3 rounded border border-[#2d333d] bg-[#111419] px-3 py-2 text-sm">
                <span>Pushover aktiv</span>
                <input
                  checked={settings.pushover_enabled}
                  className="size-4 accent-emerald-300"
                  type="checkbox"
                  onChange={(event) => update("pushover_enabled", event.target.checked)}
                />
              </label>
              <button
                className="inline-flex items-center justify-center gap-2 rounded border border-[#2d333d] bg-[#111419] px-3 py-2 text-sm transition hover:border-emerald-300/60 disabled:cursor-not-allowed disabled:opacity-50"
                disabled={pushoverMutation.isPending}
                type="button"
                onClick={() => pushoverMutation.mutate()}
              >
                <BellRing size={16} />
                {pushoverMutation.isPending ? "Startet" : "Pushover-Testjob"}
              </button>
            </div>
            {pushoverMutation.error && (
              <div className="mt-3 rounded border border-rose-300/30 bg-rose-300/10 p-3 text-sm text-rose-100">
                {pushoverMutation.error instanceof Error
                  ? pushoverMutation.error.message
                  : "Pushover-Test konnte nicht gestartet werden."}
              </div>
            )}
          </SettingCard>
        </section>

        <aside className="space-y-4">
          <SystemReadinessPanel
            data={readiness.data}
            isLoading={readiness.isLoading}
            onRefresh={() => readiness.refetch()}
          />
          <section className="rounded border border-[#2d333d] bg-[#171a20] p-5">
            <h2 className="text-base font-semibold">Runtime Status</h2>
            <div className="mt-4 space-y-3 text-sm">
              <InfoRow label="Monitor" value={settings.position_monitor_enabled ? "aktiv" : "aus"} tone={settings.position_monitor_enabled ? "good" : "neutral"} />
              <InfoRow label="Scheduler-Takt" value="1 min · Handelstage 08–02 Uhr" />
              <InfoRow label="ATR Schwelle" value={`${settings.position_monitor_threshold_atr.toFixed(1)} ATR`} />
              <InfoRow label="RS Quelle" value={settings.rs_rating_source} />
              <InfoRow label="Pushover" value={settings.pushover_configured ? "konfiguriert" : "nicht konfiguriert"} tone={settings.pushover_configured ? "good" : "neutral"} />
            </div>
          </section>
          <DataDiagnosticsPanel
            data={dataDiagnostics.data}
            isLoading={dataDiagnostics.isLoading}
            startingKey={diagnosticJobMutation.isPending ? diagnosticJobMutation.variables?.key ?? null : null}
            onRefresh={() => dataDiagnostics.refetch()}
            onStartJob={(issue) => diagnosticJobMutation.mutate(issue)}
          />
        </aside>
      </div>
    </div>
  );
}

function SettingsWorkflowLinks() {
  return (
    <section className="rounded border border-[#2d333d] bg-[#171a20] p-5">
      <div className="mb-4">
        <h2 className="text-base font-semibold">Setup und Import</h2>
        <p className="mt-1 text-sm text-[#a0a7b4]">
          Einmalige Einrichtung und Portfolio-Imports sind aus der Hauptnavigation hierher verschoben.
        </p>
      </div>
      <div className="grid gap-3 md:grid-cols-3">
        <SettingsWorkflowLink
          description="Erststart, Runtime-Secrets, Datenbank-Ziel, Datenjobs und Systemprüfung."
          href="/setup"
          icon={<Rocket size={18} />}
          title="Setup öffnen"
        />
        <SettingsWorkflowLink
          description="Positions-CSV und Trade-Republic-Import als vollständige Importseite."
          href="/portfolio/imports"
          icon={<Upload size={18} />}
          title="Import öffnen"
        />
        <SettingsWorkflowLink
          description="Marktdaten initialisieren, Smart Refresh starten und Worker-Status prüfen."
          href="/jobs"
          icon={<DatabaseZap size={18} />}
          title="Jobs öffnen"
        />
      </div>
    </section>
  );
}

function SettingsWorkflowLink({
  href,
  icon,
  title,
  description
}: {
  href: string;
  icon: React.ReactNode;
  title: string;
  description: string;
}) {
  return (
    <Link
      className="group rounded border border-[#2d333d] bg-[#111419] p-4 transition hover:border-emerald-300/60 hover:bg-[#151a20]"
      href={href}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="text-emerald-300">{icon}</div>
        <ArrowRight className="text-[#a0a7b4] transition group-hover:translate-x-0.5 group-hover:text-emerald-200" size={16} />
      </div>
      <div className="mt-3 font-semibold">{title}</div>
      <p className="mt-1 text-sm leading-5 text-[#a0a7b4]">{description}</p>
    </Link>
  );
}

function SettingCard({
  title,
  description,
  value,
  children
}: {
  title: string;
  description: string;
  value: string;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded border border-[#2d333d] bg-[#171a20] p-5">
      <div className="mb-4 flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
        <div>
          <h2 className="text-base font-semibold">{title}</h2>
          <p className="mt-1 text-sm text-[#a0a7b4]">{description}</p>
        </div>
        <StatusChip tone="neutral">{value}</StatusChip>
      </div>
      {children}
    </div>
  );
}

function NumberField({
  label,
  value,
  min,
  max,
  step,
  onChange
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  onChange: (value: number) => void;
}) {
  return (
    <Field label={label}>
      <input
        className="input-dark"
        max={max}
        min={min}
        step={step}
        type="number"
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
      />
    </Field>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block text-sm">
      <span className="mb-1 block text-[#a0a7b4]">{label}</span>
      {children}
    </label>
  );
}

function InfoRow({
  label,
  value,
  tone = "neutral"
}: {
  label: string;
  value: string;
  tone?: "good" | "neutral" | "warning" | "bad";
}) {
  return (
    <div className="flex items-center justify-between gap-3 border-b border-[#242a33] pb-3 last:border-b-0">
      <span className="text-[#a0a7b4]">{label}</span>
      <StatusChip tone={tone}>{value}</StatusChip>
    </div>
  );
}

function DataDiagnosticsPanel({
  data,
  isLoading,
  startingKey,
  onRefresh,
  onStartJob
}: {
  data?: DataDiagnostics;
  isLoading: boolean;
  startingKey: string | null;
  onRefresh: () => void;
  onStartJob: (issue: DataDiagnosticIssue) => void;
}) {
  if (isLoading) {
    return (
      <section className="rounded border border-[#2d333d] bg-[#171a20] p-5 text-sm text-[#a0a7b4]">
        Daten-Diagnose lädt...
      </section>
    );
  }

  if (!data) {
    return (
      <section className="rounded border border-rose-300/30 bg-rose-300/10 p-5 text-sm text-rose-100">
        Daten-Diagnose ist aktuell nicht erreichbar.
      </section>
    );
  }

  return (
    <section className="rounded border border-[#2d333d] bg-[#171a20] p-5">
      <div className="mb-4 flex items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <DatabaseZap className="text-emerald-300" size={18} />
            <h2 className="text-base font-semibold">Daten-Diagnose</h2>
          </div>
          <p className="mt-2 text-sm leading-5 text-[#a0a7b4]">{data.summary}</p>
        </div>
        <button
          className="flex size-9 items-center justify-center rounded border border-[#2d333d] bg-[#111419] transition hover:border-emerald-300/60"
          type="button"
          onClick={onRefresh}
        >
          <RefreshCw size={15} />
        </button>
      </div>
      <div className="grid gap-2 text-sm">
        <InfoRow label="Offene Positionen" value={String(data.open_positions_count)} />
        <InfoRow label="Price-Cache Ticker" value={String(data.price_cache_tickers_count)} />
        <InfoRow label="Fehlende Kurse" value={String(data.missing_price_count)} tone={data.missing_price_count ? "bad" : "good"} />
        <InfoRow label="Veraltete Kurse" value={String(data.stale_price_count)} tone={data.stale_price_count ? "warning" : "good"} />
        <InfoRow label="ISIN-Mappings" value={String(data.isin_mappings_count)} />
      </div>
      <div className="mt-4 space-y-3">
        {data.issues.map((issue) => (
          <div key={issue.key} className="rounded border border-[#242a33] bg-[#111419] p-3">
            <div className="mb-2 flex items-start justify-between gap-3">
              <div>
                <div className="font-medium">{issue.label}</div>
                <div className="mt-1 text-xs leading-5 text-[#77808f]">{issue.detail}</div>
              </div>
              <StatusChip tone={toneForSeverity(issue.severity)}>{issue.severity}</StatusChip>
            </div>
            {issue.tickers.length > 0 && (
              <div className="mb-3 flex flex-wrap gap-1">
                {issue.tickers.slice(0, 10).map((ticker) => (
                  <span key={ticker} className="rounded bg-[#242a33] px-2 py-1 text-xs text-[#d8dde6]">
                    {ticker}
                  </span>
                ))}
              </div>
            )}
            {issue.job_type && (
              <button
                className="inline-flex w-full items-center justify-center gap-2 rounded border border-[#2d333d] bg-[#171a20] px-3 py-2 text-sm transition hover:border-emerald-300/60 disabled:cursor-not-allowed disabled:opacity-50"
                disabled={startingKey === issue.key}
                type="button"
                onClick={() => onStartJob(issue)}
              >
                <Play size={14} />
                {startingKey === issue.key ? "Startet" : issue.action_label || "Job starten"}
              </button>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}

function SystemReadinessPanel({
  data,
  isLoading,
  onRefresh
}: {
  data?: SystemReadiness;
  isLoading: boolean;
  onRefresh: () => void;
}) {
  if (isLoading) {
    return (
      <section className="rounded border border-[#2d333d] bg-[#171a20] p-5 text-sm text-[#a0a7b4]">
        Systemstatus lädt...
      </section>
    );
  }

  if (!data) {
    return (
      <section className="rounded border border-rose-300/30 bg-rose-300/10 p-5 text-sm text-rose-100">
        Systemstatus ist aktuell nicht erreichbar.
      </section>
    );
  }

  return (
    <section className="rounded border border-[#2d333d] bg-[#171a20] p-5">
      <div className="mb-4 flex items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <ServerCog className="text-sky-300" size={18} />
            <h2 className="text-base font-semibold">Systemstatus</h2>
          </div>
          <p className="mt-2 text-sm leading-5 text-[#a0a7b4]">
            DB, Migrationen und Redis werden ohne Seitenblockade geprüft.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <StatusChip tone={toneForReadiness(data.status)}>{readinessLabel(data.status)}</StatusChip>
          <button
            className="flex size-9 items-center justify-center rounded border border-[#2d333d] bg-[#111419] transition hover:border-emerald-300/60"
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
    <div className="rounded border border-[#242a33] bg-[#111419] p-3 text-sm">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="font-medium">{systemCheckLabel(check.name)}</div>
          <div className="mt-1 text-xs leading-5 text-[#77808f]">{check.detail}</div>
          {revision && <div className="mt-1 text-xs text-[#a0a7b4]">Revision {revision}</div>}
        </div>
        <StatusChip tone={toneForSystemCheck(check.status)}>{check.status}</StatusChip>
      </div>
      <div className="mt-2 flex items-center justify-between text-xs text-[#77808f]">
        <span>{check.required ? "erforderlich" : "optional"}</span>
        <span>{check.latency_ms === null || check.latency_ms === undefined ? "-" : `${check.latency_ms} ms`}</span>
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
  if (status === "ready") return "ready";
  if (status === "degraded") return "degraded";
  return "not ready";
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
