"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, CircleDashed, Play, RotateCw, XCircle } from "lucide-react";
import { useEffect, useState } from "react";
import { StatusChip } from "@/components/ui/status-chip";
import { api } from "@/lib/api/client";
import type { Job, JobStatus, JobType, PriceRange } from "@/lib/types/api";

const jobTypes: { type: JobType; label: string; description: string }[] = [
  { type: "refresh_prices", label: "Prices", description: "Inkrementelle OHLC-Aktualisierung" },
  { type: "refresh_breadth", label: "Breadth", description: "Marktbreite und Snapshots" },
  { type: "refresh_relative_strength", label: "RS Ratings", description: "Relative-Stärke-Ranking" },
  { type: "refresh_fundamentals", label: "Fundamentals", description: "EPS, ROE, Marge, Earnings" },
  { type: "refresh_universe", label: "Universe", description: "US Common Stocks von Nasdaq Trader" },
  { type: "refresh_sec13f", label: "13F / SEC", description: "Offizielle SEC-Datensätze, monatlich/manuell" },
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

type PricePreset = "all" | "market_core" | "volatility" | "sector" | "custom";

type MarketDataBootstrapConfig = {
  pricePreset: PricePreset;
  priceRange: PriceRange;
  customTickers: string;
  breadthLookbackDays: number;
  rsLookbackDays: number;
  rsBenchmarkTicker: string;
};

const BOOTSTRAP_CONFIG_STORAGE_KEY = "boerse-dashboard.market-data-bootstrap.v1";

const defaultBootstrapConfig: MarketDataBootstrapConfig = {
  pricePreset: "all",
  priceRange: "1y",
  customTickers: "",
  breadthLookbackDays: 370,
  rsLookbackDays: 430,
  rsBenchmarkTicker: "SPY"
};

function UniverseStatusPanel({
  activeJob,
  memberCount,
  source,
  updatedAt,
  sampleTickers,
  isFetching,
  onRefresh,
  onStart,
  starting
}: {
  activeJob?: Job;
  memberCount: number;
  source: string;
  updatedAt: string | null;
  sampleTickers: string[];
  isFetching: boolean;
  onRefresh: () => void;
  onStart: () => void;
  starting: boolean;
}) {
  return (
    <section className="rounded border border-[#2d333d] bg-[#171a20] p-5">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-base font-semibold">Aktienuniversum</h2>
            <StatusChip tone={source === "nasdaq_trader" ? "good" : "warning"}>{source}</StatusChip>
            <StatusChip tone={memberCount > 100 ? "good" : "neutral"}>{memberCount.toLocaleString("de-DE")} Ticker</StatusChip>
          </div>
          <div className="mt-1 text-sm text-[#a0a7b4]">
            {updatedAt ? `Aktualisiert ${new Date(updatedAt).toLocaleString("de-DE")}` : "Noch kein gespeichertes Live-Universe."}
          </div>
          <div className="mt-2 max-w-4xl truncate text-xs text-[#697386]">
            {sampleTickers.length ? sampleTickers.join(", ") : "Fallback-Starterliste wird verwendet."}
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            className="inline-flex items-center gap-2 rounded border border-[#2d333d] bg-[#111419] px-3 py-2 text-sm transition hover:border-emerald-300/60"
            type="button"
            onClick={onRefresh}
          >
            <RotateCw size={15} className={isFetching ? "animate-spin text-emerald-300" : "text-[#a0a7b4]"} />
            Status
          </button>
          <button
            className="inline-flex items-center gap-2 rounded bg-emerald-300 px-3 py-2 text-sm font-semibold text-[#101318] transition hover:bg-emerald-200 disabled:cursor-not-allowed disabled:opacity-50"
            type="button"
            disabled={Boolean(activeJob) || starting}
            onClick={onStart}
          >
            <Play size={15} />
            Universe aktualisieren
          </button>
        </div>
      </div>
    </section>
  );
}

export default function JobsPage() {
  const queryClient = useQueryClient();
  const [selectedType, setSelectedType] = useState<JobType>("refresh_prices");
  const [startingType, setStartingType] = useState<JobType | null>(null);
  const [bootstrapConfig, setBootstrapConfig] = useState<MarketDataBootstrapConfig>(readBootstrapConfigFromStorage);
  const { data, isFetching, refetch } = useQuery({
    queryKey: ["jobs"],
    queryFn: api.jobs,
    refetchInterval: 5000
  });
  const universeQuery = useQuery({
    queryKey: ["market-universe"],
    queryFn: api.marketUniverse,
    staleTime: 60_000
  });
  const jobs = data ?? [];
  const activeJob = jobs.find((job) => job.status === "queued" || job.status === "running");

  const startMutation = useMutation({
    mutationFn: ({ type, payload }: { type: JobType; payload: Record<string, unknown> }) => {
      setStartingType(type);
      return api.startJob({ type, payload });
    },
    onSettled: () => setStartingType(null),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["jobs"] })
  });

  const cancelMutation = useMutation({
    mutationFn: (jobId: string) => api.cancelJob(jobId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["jobs"] })
  });

  useEffect(() => {
    window.localStorage.setItem(BOOTSTRAP_CONFIG_STORAGE_KEY, JSON.stringify(bootstrapConfig));
  }, [bootstrapConfig]);

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

      <RefreshSequence
        activeJob={activeJob}
        config={bootstrapConfig}
        onConfigChange={(patch) => setBootstrapConfig((current) => ({ ...current, ...patch }))}
        jobs={jobs}
        onStart={(type, payload) => startMutation.mutate({ type, payload })}
        startingType={startingType}
      />

      <UniverseStatusPanel
        activeJob={activeJob}
        memberCount={universeQuery.data?.member_count ?? 0}
        source={universeQuery.data?.source ?? "missing"}
        updatedAt={universeQuery.data?.updated_at ?? null}
        sampleTickers={universeQuery.data?.sample_tickers ?? []}
        isFetching={universeQuery.isFetching}
        onRefresh={() => universeQuery.refetch()}
        onStart={() => startMutation.mutate({ type: "refresh_universe", payload: defaultPayloadForJob("refresh_universe") })}
        starting={startingType === "refresh_universe"}
      />

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
            onClick={() => startMutation.mutate({ type: selectedType, payload: defaultPayloadForJob(selectedType) })}
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

function RefreshSequence({
  activeJob,
  config,
  jobs,
  onConfigChange,
  onStart,
  startingType
}: {
  activeJob?: Job;
  config: MarketDataBootstrapConfig;
  jobs: Job[];
  onConfigChange: (patch: Partial<MarketDataBootstrapConfig>) => void;
  onStart: (type: JobType, payload: Record<string, unknown>) => void;
  startingType: JobType | null;
}) {
  const refreshSequence = buildRefreshSequence(config);
  const customTickerCount = parseTickers(config.customTickers).length;
  const customPresetNeedsTickers = config.pricePreset === "custom" && customTickerCount === 0;

  return (
    <section className="rounded border border-[#2d333d] bg-[#171a20] p-5">
      <div className="mb-4 flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div>
          <h2 className="text-base font-semibold">Marktdaten initial laden</h2>
          <div className="text-sm text-[#a0a7b4]">
            Ersetzt die curl-Befehle: Werte eintragen, Jobs nacheinander starten, Status bleibt sichtbar.
          </div>
        </div>
        <StatusChip tone={activeJob ? "warning" : "good"}>
          {activeJob ? `läuft: ${activeJob.job_type}` : "bereit"}
        </StatusChip>
      </div>
      <div className="mb-4 grid gap-3 lg:grid-cols-[1fr_1fr] xl:grid-cols-[1.2fr_0.8fr_0.8fr_0.8fr]">
        <label className="rounded border border-[#2d333d] bg-[#111419] p-3 text-sm">
          <span className="text-xs uppercase text-[#77808f]">Price-Universum</span>
          <select
            className="mt-2 w-full rounded border border-[#2d333d] bg-[#171a20] px-3 py-2 text-sm outline-none transition focus:border-emerald-300/70"
            value={config.pricePreset}
            onChange={(event) => onConfigChange({ pricePreset: event.target.value as PricePreset })}
          >
            <option value="all">Starter + Volatility</option>
            <option value="market_core">Starter-Universum</option>
            <option value="volatility">Nur SPY, VIX, VIXY</option>
            <option value="sector">Nur Sektor-ETFs</option>
            <option value="custom">Eigene Tickerliste</option>
          </select>
        </label>
        <label className="rounded border border-[#2d333d] bg-[#111419] p-3 text-sm">
          <span className="text-xs uppercase text-[#77808f]">Price Range</span>
          <select
            className="mt-2 w-full rounded border border-[#2d333d] bg-[#171a20] px-3 py-2 text-sm outline-none transition focus:border-emerald-300/70"
            value={config.priceRange}
            onChange={(event) => onConfigChange({ priceRange: event.target.value as PriceRange })}
          >
            <option value="1m">1 Monat</option>
            <option value="3m">3 Monate</option>
            <option value="6m">6 Monate</option>
            <option value="1y">1 Jahr</option>
            <option value="2y">2 Jahre</option>
            <option value="5y">5 Jahre</option>
          </select>
        </label>
        <NumberField
          label="Breadth Lookback"
          max={2000}
          min={90}
          suffix="Tage"
          value={config.breadthLookbackDays}
          onChange={(value) => onConfigChange({ breadthLookbackDays: value })}
        />
        <NumberField
          label="RS Lookback"
          max={2000}
          min={120}
          suffix="Tage"
          value={config.rsLookbackDays}
          onChange={(value) => onConfigChange({ rsLookbackDays: value })}
        />
      </div>
      <div className="mb-4 grid gap-3 lg:grid-cols-[1fr_220px]">
        <label className="rounded border border-[#2d333d] bg-[#111419] p-3 text-sm">
          <span className="text-xs uppercase text-[#77808f]">Eigene Tickerliste</span>
          <input
            className="mt-2 w-full rounded border border-[#2d333d] bg-[#171a20] px-3 py-2 text-sm outline-none transition placeholder:text-[#697386] focus:border-emerald-300/70"
            placeholder="Optional, z. B. SPY, QQQ, NVDA, MSFT"
            value={config.customTickers}
            onChange={(event) => onConfigChange({ customTickers: event.target.value })}
          />
          <div className="mt-2 text-xs text-[#77808f]">
            {customTickerCount > 0
              ? `${customTickerCount} Ticker werden für Custom-Jobs verwendet. Benchmark und Volatility-Ticker werden beim Price-Refresh mitgeladen.`
              : "Leer lassen für das vorbereitete Starter-Universum."}
          </div>
        </label>
        <label className="rounded border border-[#2d333d] bg-[#111419] p-3 text-sm">
          <span className="text-xs uppercase text-[#77808f]">RS Benchmark</span>
          <input
            className="mt-2 w-full rounded border border-[#2d333d] bg-[#171a20] px-3 py-2 text-sm uppercase outline-none transition focus:border-emerald-300/70"
            value={config.rsBenchmarkTicker}
            onChange={(event) => onConfigChange({ rsBenchmarkTicker: event.target.value.toUpperCase() })}
          />
        </label>
      </div>
      {customPresetNeedsTickers && (
        <div className="mb-4 rounded border border-amber-300/35 bg-amber-300/10 p-3 text-sm text-amber-100">
          Für das Custom-Universum bitte mindestens einen Ticker eintragen.
        </div>
      )}
      <div className="grid gap-3 xl:grid-cols-5">
        {refreshSequence.map((step) => {
          const latest = latestJobForType(jobs, step.type);
          const done = latest?.status === "done";
          const running = latest?.status === "running" || latest?.status === "queued";
          const disabled = Boolean(activeJob) || startingType === step.type || running || step.disabled;
          return (
            <div key={step.type} className="rounded border border-[#2d333d] bg-[#111419] p-4">
              <div className="mb-3 flex items-start justify-between gap-3">
                <div>
                  <div className="font-medium">{step.label}</div>
                  <div className="mt-1 text-xs leading-5 text-[#a0a7b4]">{step.description}</div>
                </div>
                {done ? <CheckCircle2 size={18} className="text-emerald-300" /> : <CircleDashed size={18} className="text-[#77808f]" />}
              </div>
              <div className="mb-3 flex flex-wrap items-center gap-2">
                <StatusChip tone={latest ? statusTone[latest.status] : "neutral"}>
                  {latest?.status ?? "nie gelaufen"}
                </StatusChip>
                {latest?.finished_at && (
                  <span className="text-xs text-[#77808f]">{formatDate(latest.finished_at)}</span>
                )}
              </div>
              <button
                className="inline-flex w-full items-center justify-center gap-2 rounded border border-emerald-300/35 bg-emerald-300/10 px-3 py-2 text-sm text-emerald-100 transition hover:border-emerald-200 disabled:cursor-not-allowed disabled:opacity-50"
                disabled={disabled}
                type="button"
                onClick={() => onStart(step.type, step.payload)}
              >
                <Play size={15} />
                {startingType === step.type ? "Startet" : running ? "aktiv" : "Starten"}
              </button>
            </div>
          );
        })}
      </div>
    </section>
  );
}

function NumberField({
  label,
  max,
  min,
  onChange,
  suffix,
  value
}: {
  label: string;
  max: number;
  min: number;
  onChange: (value: number) => void;
  suffix: string;
  value: number;
}) {
  return (
    <label className="rounded border border-[#2d333d] bg-[#111419] p-3 text-sm">
      <span className="text-xs uppercase text-[#77808f]">{label}</span>
      <div className="mt-2 flex items-center gap-2">
        <input
          className="w-full rounded border border-[#2d333d] bg-[#171a20] px-3 py-2 text-sm tabular-nums outline-none transition focus:border-emerald-300/70"
          max={max}
          min={min}
          type="number"
          value={value}
          onChange={(event) => onChange(clampNumber(event.currentTarget.valueAsNumber, min, max, value))}
        />
        <span className="text-xs text-[#77808f]">{suffix}</span>
      </div>
    </label>
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

function latestJobForType(jobs: Job[], type: JobType) {
  return jobs.find((job) => job.job_type === type);
}

function buildRefreshSequence(config: MarketDataBootstrapConfig): {
  type: JobType;
  label: string;
  description: string;
  payload: Record<string, unknown>;
  disabled?: boolean;
}[] {
  const customTickers = config.pricePreset === "custom" ? parseTickers(config.customTickers) : [];
  const customUniversePayload = customTickers.length > 0 ? { tickers: customTickers } : {};
  const rsBenchmarkTicker = normalizeTicker(config.rsBenchmarkTicker) || "SPY";
  const pricePayload =
    config.pricePreset === "custom"
      ? {
          mode: "manual",
          range: config.priceRange,
          tickers: uniqueTickers([...customTickers, rsBenchmarkTicker, "SPY", "^VIX", "VIXY"])
        }
      : { mode: "manual", range: config.priceRange, preset: config.pricePreset };

  return [
    {
      type: "refresh_prices",
      label: "1. Market Prices",
      description: "OHLC-Cache für Market-, Benchmark- und Volatility-Ticker füllen.",
      payload: pricePayload,
      disabled: config.pricePreset === "custom" && customTickers.length === 0
    },
    {
      type: "refresh_breadth",
      label: "2. Market Breadth",
      description: "Marktbreite und MarketSnapshot aus dem Price Cache vorberechnen.",
      payload: { mode: "manual", lookback_days: config.breadthLookbackDays, ...customUniversePayload }
    },
    {
      type: "refresh_relative_strength",
      label: "3. RS Ratings",
      description: "Relative Stärke aus gecachten Kursen berechnen.",
      payload: {
        mode: "manual",
        lookback_days: config.rsLookbackDays,
        benchmark_ticker: rsBenchmarkTicker,
        ...customUniversePayload
      }
    },
    {
      type: "refresh_fundamentals",
      label: "4. Fundamentals",
      description: "EPS, Umsatz, ROE, Marge, Beta und Earnings in den Cache laden.",
      payload: { mode: "manual", include_holders: true, ...customUniversePayload }
    },
    {
      type: "position_atr_monitor",
      label: "5. Positionsmonitor",
      description: "Offene Positionen gegen Price Cache und Sell-Engine prüfen.",
      payload: { mode: "manual" }
    }
  ];
}

function defaultPayloadForJob(type: JobType): Record<string, unknown> {
  if (type === "refresh_prices") return { mode: "manual", range: "1y", preset: "all" };
  if (type === "refresh_breadth") return { mode: "manual", lookback_days: 370 };
  if (type === "refresh_relative_strength") return { mode: "manual", lookback_days: 430 };
  if (type === "refresh_fundamentals") return { mode: "manual", include_holders: true };
  if (type === "refresh_universe") return { mode: "manual", source: "dashboard" };
  if (type === "refresh_sec13f") {
    return { mode: "manual", universe: "open_positions", dataset_count: 2, limit_universe: 120 };
  }
  return { mode: "manual" };
}

function parseTickers(value: string) {
  return uniqueTickers(value.replaceAll(";", ",").split(","));
}

function uniqueTickers(values: string[]) {
  return Array.from(
    new Set(
      values
        .map((value) => normalizeTicker(value))
        .filter((value): value is string => Boolean(value))
    )
  ).slice(0, 120);
}

function normalizeTicker(value: string) {
  return value.trim().toUpperCase();
}

function clampNumber(value: number, min: number, max: number, fallback: number) {
  if (!Number.isFinite(value)) return fallback;
  return Math.max(min, Math.min(max, Math.round(value)));
}

function normalizeBootstrapConfig(value: unknown): MarketDataBootstrapConfig {
  const raw = value && typeof value === "object" ? (value as Partial<MarketDataBootstrapConfig>) : {};
  const pricePreset = ["all", "market_core", "volatility", "sector", "custom"].includes(String(raw.pricePreset))
    ? (raw.pricePreset as PricePreset)
    : defaultBootstrapConfig.pricePreset;
  const priceRange = ["1m", "3m", "6m", "1y", "2y", "5y"].includes(String(raw.priceRange))
    ? (raw.priceRange as PriceRange)
    : defaultBootstrapConfig.priceRange;

  return {
    pricePreset,
    priceRange,
    customTickers: typeof raw.customTickers === "string" ? raw.customTickers : "",
    breadthLookbackDays: clampNumber(
      Number(raw.breadthLookbackDays),
      90,
      2000,
      defaultBootstrapConfig.breadthLookbackDays
    ),
    rsLookbackDays: clampNumber(Number(raw.rsLookbackDays), 120, 2000, defaultBootstrapConfig.rsLookbackDays),
    rsBenchmarkTicker: normalizeTicker(String(raw.rsBenchmarkTicker || defaultBootstrapConfig.rsBenchmarkTicker))
  };
}

function readBootstrapConfigFromStorage() {
  if (typeof window === "undefined") return defaultBootstrapConfig;
  const raw = window.localStorage.getItem(BOOTSTRAP_CONFIG_STORAGE_KEY);
  if (!raw) return defaultBootstrapConfig;
  try {
    return normalizeBootstrapConfig(JSON.parse(raw));
  } catch {
    return defaultBootstrapConfig;
  }
}
