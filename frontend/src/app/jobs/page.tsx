"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, CircleDashed, Play, RotateCw, Save, SearchCheck, WandSparkles, XCircle } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { StatusChip } from "@/components/ui/status-chip";
import { api } from "@/lib/api/client";
import type {
  Job,
  JobStatus,
  JobType,
  PriceRange,
  SetupStatus,
  SetupStep,
  UniverseSymbolMappingReview,
  UniverseSymbolMappingUpdate
} from "@/lib/types/api";

const jobTypes: { type: JobType; label: string; description: string }[] = [
  { type: "smart_refresh_market_data", label: "Alles smart aktualisieren", description: "Prüfen und nur fehlende/veraltete Daten aktualisieren" },
  { type: "bootstrap_market_data", label: "Alles", description: "Universe, Kurse, Breadth, RS und Monitor" },
  { type: "refresh_prices", label: "Market Prices", description: "OHLC-Kurse in den Cache laden" },
  { type: "refresh_breadth", label: "Market Breadth", description: "Marktbreite und Snapshot berechnen" },
  { type: "refresh_relative_strength", label: "RS Ratings", description: "Relative-Stärke-Ranking berechnen" },
  { type: "refresh_fundamentals", label: "Fundamentals", description: "Fundamentaldaten je Aktie laden" },
  { type: "refresh_stock_detail", label: "Stock Detail", description: "Eine Aktie vollständig aktualisieren" },
  { type: "refresh_universe", label: "Aktienuniversum", description: "US-Common-Stocks-Liste aktualisieren" },
  { type: "yahoo_symbol_diagnostics", label: "Yahoo Diagnose", description: "Ticker-Mapping nur prüfen" },
  { type: "yahoo_symbol_rescue", label: "Yahoo Auto-Rescue", description: "gültige Yahoo-Mappings speichern" },
  { type: "refresh_sec13f", label: "13F / SEC", description: "SEC-Institutional-Daten laden" },
  { type: "position_atr_monitor", label: "Positionsmonitor", description: "offene Positionen prüfen" }
];

const pricePresetHelp: Record<PricePreset, string> = {
  all: "Empfohlen für den Start: Marktindizes, Equal-Weight-ETFs, Starter-Aktien, VIX/VXX und Sektor-ETFs.",
  market_core: "Kleiner Streamlit-Kern: S&P 500, Nasdaq, Russell 2000, RSP, QQEW und Starter-Aktien.",
  stored_universe: "Das vorher geladene US-Aktienuniversum. Gut für breite Analysen, auf der NAS aber deutlich schwerer.",
  volatility: "Nur SPY, VIX und VXX. Reicht für Volatilitätskarten, aber nicht für Marktbreite/RS.",
  sector: "Nur SPDR-Sektor-ETFs. Reicht für Sektorrotation, aber nicht für Aktien-Rankings.",
  custom: "Nur die manuell eingetragenen Ticker plus Benchmark/Volatility-Hilfsticker."
};

const statusTone: Record<JobStatus, "good" | "neutral" | "warning" | "bad"> = {
  queued: "neutral",
  running: "warning",
  done: "good",
  failed: "bad",
  skipped: "neutral",
  cancelled: "neutral"
};

type PricePreset = "all" | "stored_universe" | "market_core" | "volatility" | "sector" | "custom";

type MarketDataBootstrapConfig = {
  pricePreset: PricePreset;
  priceRange: PriceRange;
  storedUniverseLimit: number;
  customTickers: string;
  breadthLookbackDays: number;
  rsLookbackDays: number;
  rsBenchmarkTicker: string;
};

const BOOTSTRAP_CONFIG_STORAGE_KEY = "boerse-dashboard.market-data-bootstrap.v2";

const defaultBootstrapConfig: MarketDataBootstrapConfig = {
  pricePreset: "stored_universe",
  priceRange: "2y",
  storedUniverseLimit: 10000,
  customTickers: "",
  breadthLookbackDays: 550,
  rsLookbackDays: 430,
  rsBenchmarkTicker: "SPY"
};

function UniverseStatusPanel({
  activeJob,
  latestJob,
  memberCount,
  source,
  updatedAt,
  sampleTickers,
  isFetching,
  onRefresh,
  onStart,
  startError,
  starting
}: {
  activeJob?: Job;
  latestJob?: Job;
  memberCount: number;
  source: string;
  updatedAt: string | null;
  sampleTickers: string[];
  isFetching: boolean;
  onRefresh: () => void;
  onStart: () => void;
  startError: string;
  starting: boolean;
}) {
  const blockedByOtherJob = Boolean(activeJob && activeJob.job_type !== "refresh_universe");
  const universeRunning = latestJob?.status === "queued" || latestJob?.status === "running";
  const disabled = blockedByOtherJob || universeRunning || starting;

  return (
    <section className="rounded border border-[#2d333d] bg-[#171a20] p-5">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-base font-semibold">Aktienuniversum</h2>
            <StatusChip tone={source === "nasdaq_trader" ? "good" : "warning"}>{source}</StatusChip>
            <StatusChip tone={memberCount > 100 ? "good" : "neutral"}>{memberCount.toLocaleString("de-DE")} Ticker</StatusChip>
            {latestJob && <StatusChip tone={statusTone[latestJob.status]}>{jobStatusLabel(latestJob.status)}</StatusChip>}
          </div>
          <div className="mt-1 text-sm text-[#a0a7b4]">
            {updatedAt ? `Aktualisiert ${new Date(updatedAt).toLocaleString("de-DE")}` : "Noch kein gespeichertes Live-Universe."}
          </div>
          <div className="mt-2 max-w-4xl text-xs leading-5 text-[#77808f]">
            Dieser Button lädt nur die handelbare Aktienliste von Nasdaq Trader. Er lädt keine Kurse und berechnet keine
            Marktbreite; dafür danach Market Prices und Market Breadth starten.
          </div>
          <div className="mt-2 max-w-4xl truncate text-xs text-[#697386]">
            {sampleTickers.length ? sampleTickers.join(", ") : "Fallback-Starterliste wird verwendet."}
          </div>
        </div>
        <div className="flex shrink-0 flex-wrap gap-2 lg:justify-end">
          <button
            className="inline-flex items-center gap-2 rounded border border-[#2d333d] bg-[#111419] px-3 py-2 text-sm transition hover:border-emerald-300/60"
            type="button"
            onClick={onRefresh}
          >
            <RotateCw size={15} className={isFetching ? "animate-spin text-emerald-300" : "text-[#a0a7b4]"} />
            Status
          </button>
          <button
            className="inline-flex max-w-full items-center justify-center gap-2 rounded bg-emerald-300 px-3 py-2 text-sm font-semibold text-[#101318] transition hover:bg-emerald-200 disabled:cursor-not-allowed disabled:opacity-50"
            type="button"
            disabled={disabled}
            onClick={onStart}
          >
            <Play size={15} />
            {starting ? "Startet" : universeRunning ? "Läuft" : "Universum aktualisieren"}
          </button>
        </div>
      </div>
      {latestJob && (
        <div className="mt-4 rounded border border-[#242a33] bg-[#111419] p-3 text-sm">
          <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
            <div>
              <div className="font-medium">Letzter Universe-Job</div>
              <div className="mt-1 text-xs leading-5 text-[#77808f]">
                {latestJob.current_step || latestJob.message || "Jobstatus wird aktualisiert."}
              </div>
            </div>
            <div className="text-xs tabular-nums text-[#a0a7b4]">{formatDate(latestJob.created_at)}</div>
          </div>
          {(latestJob.status === "queued" || latestJob.status === "running") && (
            <div className="mt-3">
              <div className="h-2 overflow-hidden rounded bg-[#171a20]">
                <div className="h-2 rounded bg-emerald-300" style={{ width: `${latestJob.progress}%` }} />
              </div>
              <div className="mt-1 text-right text-xs tabular-nums text-[#77808f]">{latestJob.progress}%</div>
            </div>
          )}
          {latestJob.status === "failed" && latestJob.error_message && (
            <div className="mt-3 rounded border border-rose-300/30 bg-rose-300/10 p-3 text-xs leading-5 text-rose-100">
              {latestJob.error_message}
            </div>
          )}
        </div>
      )}
      {blockedByOtherJob && activeJob && (
        <div className="mt-3 rounded border border-amber-300/35 bg-amber-300/10 p-3 text-sm text-amber-100">
          Ein anderer Job läuft gerade: {activeJob.job_type}. Auf der NAS wird nur ein schwerer Job gleichzeitig gestartet.
        </div>
      )}
      {startError && (
        <div className="mt-3 rounded border border-rose-300/30 bg-rose-300/10 p-3 text-sm text-rose-100">
          {startError}
        </div>
      )}
    </section>
  );
}

function UniverseSymbolMappingPanel({
  failedTickers,
  isFetching,
  onRefresh,
  onSave,
  review,
  saveError,
  saving
}: {
  failedTickers: string[];
  isFetching: boolean;
  onRefresh: () => void;
  onSave: (payload: UniverseSymbolMappingUpdate) => void;
  review?: UniverseSymbolMappingReview;
  saveError: string;
  saving: boolean;
}) {
  const [sourceTicker, setSourceTicker] = useState("");
  const [yahooSymbol, setYahooSymbol] = useState("");
  const [status, setStatus] = useState<"active" | "ignored">("active");
  const [note, setNote] = useState("");
  const canSave = sourceTicker.trim().length > 0 && (status === "ignored" || yahooSymbol.trim().length > 0);
  const mappedRows = review?.mappings.slice(0, 8) ?? [];
  const unmappedSample = review?.unmapped_sample.slice(0, 18) ?? [];

  function fillTicker(ticker: string) {
    setSourceTicker(ticker);
    setYahooSymbol(ticker);
    setStatus("active");
  }

  function submit() {
    if (!canSave) return;
    onSave({
      universe_key: review?.universe_key ?? "us_common_stocks",
      source_ticker: normalizeTicker(sourceTicker),
      yahoo_symbol: normalizeTicker(yahooSymbol),
      status,
      note
    });
  }

  return (
    <section className="rounded border border-[#2d333d] bg-[#171a20] p-5">
      <div className="mb-4 flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-base font-semibold">Yahoo-Symbol Rescue</h2>
            <StatusChip tone={review?.source === "database" ? "good" : "neutral"}>
              {review?.source ?? "lädt"}
            </StatusChip>
            <StatusChip tone={(review?.mapped_count ?? 0) > 0 ? "good" : "neutral"}>
              {(review?.mapped_count ?? 0).toLocaleString("de-DE")} Mappings
            </StatusChip>
            <StatusChip tone={(review?.ignored_count ?? 0) > 0 ? "warning" : "neutral"}>
              {(review?.ignored_count ?? 0).toLocaleString("de-DE")} ignoriert
            </StatusChip>
          </div>
          <div className="mt-1 text-sm text-[#a0a7b4]">
            Universe-Ticker bleiben stabil; nur der yfinance-Ladealias wird hier korrigiert.
          </div>
        </div>
        <button
          className="inline-flex items-center gap-2 rounded border border-[#2d333d] bg-[#111419] px-3 py-2 text-sm transition hover:border-emerald-300/60"
          type="button"
          onClick={onRefresh}
        >
          <RotateCw size={15} className={isFetching ? "animate-spin text-emerald-300" : "text-[#a0a7b4]"} />
          Mappings prüfen
        </button>
      </div>

      {failedTickers.length > 0 && (
        <div className="mb-4 rounded border border-rose-300/30 bg-rose-300/10 p-3">
          <div className="text-sm font-medium text-rose-100">Letzte Preisfehler</div>
          <div className="mt-2 flex flex-wrap gap-2">
            {failedTickers.map((ticker) => (
              <button
                key={ticker}
                className="rounded border border-rose-300/30 bg-[#111419] px-2 py-1 text-xs text-rose-100 transition hover:border-rose-200"
                type="button"
                onClick={() => fillTicker(ticker)}
              >
                {ticker}
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="grid gap-3 xl:grid-cols-[160px_160px_140px_1fr_auto]">
        <label className="rounded border border-[#2d333d] bg-[#111419] p-3 text-sm">
          <span className="text-xs uppercase text-[#77808f]">Universe-Ticker</span>
          <input
            className="mt-2 w-full rounded border border-[#2d333d] bg-[#171a20] px-3 py-2 text-sm uppercase outline-none transition focus:border-emerald-300/70"
            placeholder="BRK-B"
            value={sourceTicker}
            onChange={(event) => setSourceTicker(event.target.value.toUpperCase())}
          />
        </label>
        <label className="rounded border border-[#2d333d] bg-[#111419] p-3 text-sm">
          <span className="text-xs uppercase text-[#77808f]">Yahoo-Symbol</span>
          <input
            className="mt-2 w-full rounded border border-[#2d333d] bg-[#171a20] px-3 py-2 text-sm uppercase outline-none transition focus:border-emerald-300/70"
            placeholder="BRK-B"
            value={yahooSymbol}
            onChange={(event) => setYahooSymbol(event.target.value.toUpperCase())}
          />
        </label>
        <label className="rounded border border-[#2d333d] bg-[#111419] p-3 text-sm">
          <span className="text-xs uppercase text-[#77808f]">Status</span>
          <select
            className="mt-2 w-full rounded border border-[#2d333d] bg-[#171a20] px-3 py-2 text-sm outline-none transition focus:border-emerald-300/70"
            value={status}
            onChange={(event) => setStatus(event.target.value as "active" | "ignored")}
          >
            <option value="active">Aktiv</option>
            <option value="ignored">Ignorieren</option>
          </select>
        </label>
        <label className="rounded border border-[#2d333d] bg-[#111419] p-3 text-sm">
          <span className="text-xs uppercase text-[#77808f]">Notiz</span>
          <input
            className="mt-2 w-full rounded border border-[#2d333d] bg-[#171a20] px-3 py-2 text-sm outline-none transition placeholder:text-[#697386] focus:border-emerald-300/70"
            placeholder="z. B. Yahoo nutzt anderes Symbol"
            value={note}
            onChange={(event) => setNote(event.target.value)}
          />
        </label>
        <button
          className="inline-flex items-center justify-center gap-2 rounded bg-emerald-300 px-4 py-3 text-sm font-semibold text-[#101318] transition hover:bg-emerald-200 disabled:cursor-not-allowed disabled:opacity-50 xl:self-end"
          disabled={!canSave || saving}
          type="button"
          onClick={submit}
        >
          <Save size={15} />
          {saving ? "Speichert" : "Speichern"}
        </button>
      </div>
      {saveError && <div className="mt-3 text-sm text-rose-200">{saveError}</div>}

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <div className="rounded border border-[#242a33] bg-[#111419] p-3">
          <div className="mb-2 flex items-center justify-between gap-3">
            <div className="text-sm font-medium">Aktive Overrides</div>
            <div className="text-xs text-[#77808f]">
              {review ? `${review.member_count.toLocaleString("de-DE")} Universe-Ticker` : "lädt"}
            </div>
          </div>
          <div className="space-y-2">
            {mappedRows.length === 0 && (
              <div className="text-sm text-[#77808f]">Noch keine manuellen Symbol-Mappings gespeichert.</div>
            )}
            {mappedRows.map((row) => (
              <button
                key={`${row.universe_key}-${row.source_ticker}`}
                className="grid w-full grid-cols-[1fr_1fr_auto] items-center gap-2 rounded border border-[#2d333d] px-3 py-2 text-left text-sm transition hover:border-[#697386]"
                type="button"
                onClick={() => {
                  setSourceTicker(row.source_ticker);
                  setYahooSymbol(row.yahoo_symbol);
                  setStatus(row.status === "ignored" ? "ignored" : "active");
                  setNote(row.note);
                }}
              >
                <span className="font-medium">{row.source_ticker}</span>
                <span className="text-[#a0a7b4]">{row.yahoo_symbol || "-"}</span>
                <StatusChip tone={row.status === "ignored" ? "warning" : "good"}>{row.status}</StatusChip>
              </button>
            ))}
          </div>
        </div>
        <div className="rounded border border-[#242a33] bg-[#111419] p-3">
          <div className="mb-2 flex items-center justify-between gap-3">
            <div className="text-sm font-medium">Ungemappte Stichprobe</div>
            <div className="text-xs text-[#77808f]">
              {(review?.unmapped_count ?? 0).toLocaleString("de-DE")} ohne Override
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            {unmappedSample.map((ticker) => (
              <button
                key={ticker}
                className="rounded border border-[#2d333d] px-2 py-1 text-xs text-[#d8dde6] transition hover:border-emerald-300/60"
                type="button"
                onClick={() => fillTicker(ticker)}
              >
                {ticker}
              </button>
            ))}
            {unmappedSample.length === 0 && (
              <div className="text-sm text-[#77808f]">Keine ungemappten Ticker in der aktuellen Stichprobe.</div>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}

type YahooProbeCandidate = {
  symbol: string;
  ok?: boolean;
  records_seen?: number;
  last_date?: string | null;
  error_message?: string;
};

type YahooProbeItem = {
  source_ticker: string;
  best_candidate: string;
  status: string;
  mapping_applied?: boolean;
  candidates: YahooProbeCandidate[];
};

function YahooDiagnosticsPanel({
  activeJob,
  failedTickers,
  latestDiagnosticsJob,
  latestRescueJob,
  onStart,
  startingType
}: {
  activeJob?: Job;
  failedTickers: string[];
  latestDiagnosticsJob?: Job;
  latestRescueJob?: Job;
  onStart: (type: JobType, payload: Record<string, unknown>) => void;
  startingType: JobType | null;
}) {
  const latestJob = newerJob(latestDiagnosticsJob, latestRescueJob);
  const items = yahooProbeItems(latestJob).slice(0, 12);
  const running =
    latestDiagnosticsJob?.status === "queued" ||
    latestDiagnosticsJob?.status === "running" ||
    latestRescueJob?.status === "queued" ||
    latestRescueJob?.status === "running";
  const disabled = Boolean(activeJob) || Boolean(running);
  const probePayload = failedTickers.length
    ? { source: "dashboard", tickers: failedTickers, limit: Math.min(120, failedTickers.length), period: "1mo" }
    : { source: "dashboard", universe: "us_common_stocks", limit: 40, period: "1mo" };

  return (
    <section className="rounded border border-[#2d333d] bg-[#171a20] p-5">
      <div className="mb-4 flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-base font-semibold">Yahoo-Diagnose & Auto-Rescue</h2>
            {latestJob ? <StatusChip tone={statusTone[latestJob.status]}>{jobStatusLabel(latestJob.status)}</StatusChip> : null}
            {failedTickers.length ? (
              <StatusChip tone="warning">{failedTickers.length.toLocaleString("de-DE")} Preisfehler</StatusChip>
            ) : (
              <StatusChip tone="neutral">Universe-Stichprobe</StatusChip>
            )}
          </div>
          <div className="mt-1 max-w-4xl text-sm leading-6 text-[#a0a7b4]">
            Diagnose prüft nur Kandidaten und schreibt nichts. Auto-Rescue speichert nur Kandidaten, die echte
            Daily-Bars liefern; Kursdaten werden danach über den normalen Market-Prices-Job geladen.
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            className="inline-flex items-center gap-2 rounded border border-[#2d333d] bg-[#111419] px-3 py-2 text-sm transition hover:border-emerald-300/60 disabled:cursor-not-allowed disabled:opacity-50"
            disabled={disabled || startingType === "yahoo_symbol_diagnostics"}
            type="button"
            onClick={() => onStart("yahoo_symbol_diagnostics", probePayload)}
          >
            <SearchCheck size={15} />
            {startingType === "yahoo_symbol_diagnostics" ? "Startet" : "Diagnose starten"}
          </button>
          <button
            className="inline-flex items-center gap-2 rounded border border-emerald-300/40 bg-emerald-300/10 px-3 py-2 text-sm text-emerald-100 transition hover:border-emerald-200 disabled:cursor-not-allowed disabled:opacity-50"
            disabled={disabled || startingType === "yahoo_symbol_rescue"}
            type="button"
            onClick={() => onStart("yahoo_symbol_rescue", probePayload)}
          >
            <WandSparkles size={15} />
            {startingType === "yahoo_symbol_rescue" ? "Startet" : "Auto-Rescue"}
          </button>
        </div>
      </div>

      {latestJob && (
        <div className="mb-4 rounded border border-[#242a33] bg-[#111419] p-3 text-sm">
          <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
            <div>
              <div className="font-medium">Letzter Yahoo-Job: {latestJob.job_type}</div>
              <div className="mt-1 text-xs leading-5 text-[#77808f]">{latestJob.message || latestJob.current_step}</div>
            </div>
            <div className="text-xs tabular-nums text-[#a0a7b4]">{formatDate(latestJob.created_at)}</div>
          </div>
          {(latestJob.status === "queued" || latestJob.status === "running") && (
            <div className="mt-3">
              <div className="h-2 overflow-hidden rounded bg-[#171a20]">
                <div className="h-2 rounded bg-emerald-300" style={{ width: `${latestJob.progress}%` }} />
              </div>
            </div>
          )}
        </div>
      )}

      {items.length ? (
        <div className="overflow-hidden rounded border border-[#2d333d]">
          <table className="w-full text-left text-sm">
            <thead className="bg-[#111419] text-xs uppercase text-[#a0a7b4]">
              <tr>
                <th className="px-3 py-2">Ticker</th>
                <th className="px-3 py-2">Status</th>
                <th className="px-3 py-2">Bester Kandidat</th>
                <th className="px-3 py-2">Geprüfte Symbole</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.source_ticker} className="border-t border-[#2d333d]">
                  <td className="px-3 py-2 font-medium text-emerald-100">{item.source_ticker}</td>
                  <td className="px-3 py-2">
                    <StatusChip tone={toneForYahooStatus(item.status, item.mapping_applied)}>
                      {item.mapping_applied ? "mapping gespeichert" : item.status}
                    </StatusChip>
                  </td>
                  <td className="px-3 py-2 text-[#d8dde6]">{item.best_candidate || "-"}</td>
                  <td className="px-3 py-2">
                    <div className="flex flex-wrap gap-1">
                      {item.candidates.slice(0, 4).map((candidate) => (
                        <span
                          key={candidate.symbol}
                          className={[
                            "rounded border px-2 py-1 text-xs",
                            candidate.ok
                              ? "border-emerald-300/35 bg-emerald-300/10 text-emerald-100"
                              : "border-[#2d333d] bg-[#111419] text-[#a0a7b4]"
                          ].join(" ")}
                        >
                          {candidate.symbol}
                        </span>
                      ))}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="rounded border border-dashed border-[#2d333d] bg-[#111419] p-4 text-sm text-[#a0a7b4]">
          Noch keine Yahoo-Diagnose gelaufen. Starte zuerst eine Diagnose oder nutze Auto-Rescue nach einem fehlgeschlagenen Price-Refresh.
        </div>
      )}
    </section>
  );
}

export default function JobsPage() {
  const queryClient = useQueryClient();
  const [selectedType, setSelectedType] = useState<JobType>("bootstrap_market_data");
  const [startingType, setStartingType] = useState<JobType | null>(null);
  const [bootstrapConfig, setBootstrapConfig] = useState<MarketDataBootstrapConfig>(loadBootstrapConfig);
  const { data, isFetching, refetch } = useQuery({
    queryKey: ["jobs"],
    queryFn: api.jobs,
    refetchInterval: 5000
  });
  const setupQuery = useQuery({
    queryKey: ["setup-status"],
    queryFn: api.setupStatus,
    refetchInterval: 5000,
    staleTime: 3000
  });
  const universeQuery = useQuery({
    queryKey: ["market-universe"],
    queryFn: api.marketUniverse,
    staleTime: 60_000
  });
  const universeMappingsQuery = useQuery({
    queryKey: ["market-universe-mappings"],
    queryFn: () => api.marketUniverseMappings(500),
    staleTime: 60_000
  });
  const jobs = data ?? [];
  const activeJobs = jobs.filter(isActiveJob);
  const activeJob = activeJobs[0];
  const visibleJobs = mergeJobs(activeJobs, jobs.filter((job) => !isActiveJob(job)).slice(0, 3));
  const latestUniverseJob = latestJobForType(jobs, "refresh_universe");
  const latestYahooDiagnosticsJob = latestJobForType(jobs, "yahoo_symbol_diagnostics");
  const latestYahooRescueJob = latestJobForType(jobs, "yahoo_symbol_rescue");
  const priceFailures = latestFailedPriceTickers(jobs);

  const startMutation = useMutation({
    mutationFn: ({ type, payload }: { type: JobType; payload: Record<string, unknown> }) => {
      setStartingType(type);
      return api.startJob({ type, payload });
    },
    onSettled: () => {
      setStartingType(null);
      queryClient.invalidateQueries({ queryKey: ["jobs"] });
      queryClient.invalidateQueries({ queryKey: ["setup-status"] });
      queryClient.invalidateQueries({ queryKey: ["freshness"] });
    },
    onSuccess: (job) => {
      if (job.job_type === "refresh_universe") {
        queryClient.invalidateQueries({ queryKey: ["market-universe"] });
        queryClient.invalidateQueries({ queryKey: ["market-universe-mappings"] });
      }
    }
  });

  const cancelMutation = useMutation({
    mutationFn: (jobId: string) => api.cancelJob(jobId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["jobs"] });
      queryClient.invalidateQueries({ queryKey: ["setup-status"] });
      queryClient.invalidateQueries({ queryKey: ["freshness"] });
      queryClient.invalidateQueries({ queryKey: ["settings-data-diagnostics"] });
    }
  });

  const mappingMutation = useMutation({
    mutationFn: api.patchMarketUniverseMapping,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["market-universe-mappings"] });
      queryClient.invalidateQueries({ queryKey: ["market-universe"] });
    }
  });

  useEffect(() => {
    window.localStorage.setItem(BOOTSTRAP_CONFIG_STORAGE_KEY, JSON.stringify(bootstrapConfig));
  }, [bootstrapConfig]);

  useEffect(() => {
    if (latestUniverseJob?.status !== "done") return;
    queryClient.invalidateQueries({ queryKey: ["market-universe"] });
    queryClient.invalidateQueries({ queryKey: ["market-universe-mappings"] });
  }, [latestUniverseJob?.job_id, latestUniverseJob?.status, queryClient]);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-end">
        <button
          className="inline-flex h-9 items-center gap-2 rounded-[10px] border border-[#d8e1ea] bg-white px-3 text-sm font-medium text-[#172033] transition hover:border-[#0f766e]"
          type="button"
          onClick={() => refetch()}
        >
          <RotateCw size={15} className={isFetching ? "animate-spin text-emerald-300" : "text-[#a0a7b4]"} />
          Aktualisieren
        </button>
      </div>

      <JobsSetupStatusPanel
        activeJob={activeJob}
        cancellingJobId={cancelMutation.isPending ? cancelMutation.variables : null}
        isFetching={setupQuery.isFetching}
        onCancel={(jobId) => cancelMutation.mutate(jobId)}
        setupStatus={setupQuery.data}
        startingType={startingType}
        onRefresh={() => setupQuery.refetch()}
        onStart={(step) => {
          if (!step.job_type) return;
          startMutation.mutate({
            type: step.job_type,
            payload: { ...step.job_payload, source: "jobs_status" }
          });
        }}
      />

      <MarketDataAssistantPanel
        activeJob={activeJob}
        config={bootstrapConfig}
        jobs={jobs}
        onStart={(type, payload) => startMutation.mutate({ type, payload })}
        startingType={startingType}
      />

      <details className="rounded border border-[#2d333d] bg-[#171a20] p-5">
        <summary className="cursor-pointer text-base font-semibold text-[#d8dde6]">
          Expert-Werkzeuge: Universe, Yahoo-Mapping und Einzeljobs
        </summary>
        <div className="mt-4 space-y-5">
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
            latestJob={latestUniverseJob}
            memberCount={universeQuery.data?.member_count ?? 0}
            source={universeQuery.data?.source ?? "missing"}
            updatedAt={universeQuery.data?.updated_at ?? null}
            sampleTickers={universeQuery.data?.sample_tickers ?? []}
            isFetching={universeQuery.isFetching}
            onRefresh={() => universeQuery.refetch()}
            onStart={() => startMutation.mutate({ type: "refresh_universe", payload: defaultPayloadForJob("refresh_universe") })}
            startError={
              startMutation.isError &&
              startMutation.variables?.type === "refresh_universe" &&
              startMutation.error instanceof Error
                ? startMutation.error.message
                : ""
            }
            starting={startingType === "refresh_universe"}
          />

          <UniverseSymbolMappingPanel
            failedTickers={priceFailures}
            isFetching={universeMappingsQuery.isFetching}
            review={universeMappingsQuery.data}
            saving={mappingMutation.isPending}
            saveError={
              mappingMutation.isError && mappingMutation.error instanceof Error
                ? mappingMutation.error.message
                : ""
            }
            onRefresh={() => universeMappingsQuery.refetch()}
            onSave={(payload) => mappingMutation.mutate(payload)}
          />

          <YahooDiagnosticsPanel
            activeJob={activeJob}
            failedTickers={priceFailures}
            latestDiagnosticsJob={latestYahooDiagnosticsJob}
            latestRescueJob={latestYahooRescueJob}
            onStart={(type, payload) => startMutation.mutate({ type, payload })}
            startingType={startingType}
          />
        </div>
      </details>

      <details className="rounded border border-[#2d333d] bg-[#171a20] p-5">
        <summary className="cursor-pointer text-base font-semibold text-[#d8dde6]">
          Einzeljob manuell starten
        </summary>
        <div className="mt-4 flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <div>
            <h2 className="text-base font-semibold">Job manuell starten</h2>
            <div className="text-sm text-[#a0a7b4]">
              Expert-Modus mit festen Default-Einstellungen. Für die Erstbefüllung die Box „Marktdaten initial laden“
              oben verwenden.
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
        {selectedType === "refresh_sec13f" && (
          <div className="mt-3 rounded border border-amber-300/30 bg-amber-300/10 p-3 text-sm leading-6 text-amber-100">
            13F/SEC benötigt einen SEC User-Agent im Setup/Security-Bereich, zum Beispiel
            `boerse-dashboard-web name@example.com`. Danach zieht Smart-Refresh fehlende 13F-Daten automatisch nach.
          </div>
        )}
        <details className="mt-3 rounded border border-[#242a33] bg-[#111419] p-3 text-sm">
          <summary className="cursor-pointer text-[#d8dde6]">Default-Einstellungen für diesen manuellen Start</summary>
          <p className="mt-2 leading-6 text-[#a0a7b4]">
            Diese Werte sind unabhängig von den Hauptbuttons. Für Marktbreite und RS wird das volle gespeicherte
            US-Common-Stocks-Universum verwendet. 13F wird im Smart-Refresh nur bei fehlenden oder veralteten
            Quartalsdaten gestartet.
          </p>
          <pre className="mt-3 max-h-44 overflow-auto rounded border border-[#242a33] bg-[#0f1115] p-3 text-xs text-[#d8dde6]">
            {JSON.stringify(defaultPayloadForJob(selectedType), null, 2)}
          </pre>
        </details>
        {startMutation.isError && (
          <div className="mt-3 text-sm text-rose-200">
            {startMutation.error instanceof Error ? startMutation.error.message : "Job konnte nicht gestartet werden."}
          </div>
        )}
      </details>

      <div className="space-y-3">
        <div className="flex flex-col gap-2 md:flex-row md:items-end md:justify-between">
          <div>
            <h2 className="text-base font-semibold">Letzte Jobs</h2>
            <p className="text-sm text-[#a0a7b4]">
              Aktive Jobs werden immer angezeigt, plus die letzten drei abgeschlossenen Einträge.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            {activeJobs.length > 0 && <StatusChip tone="warning">{activeJobs.length} aktiv</StatusChip>}
            <StatusChip tone="neutral">{jobs.length.toLocaleString("de-DE")} geladen</StatusChip>
          </div>
        </div>
        {jobs.length === 0 && (
          <div className="rounded border border-[#2d333d] bg-[#171a20] p-5 text-sm text-[#a0a7b4]">
            Noch keine Jobs vorhanden. Das Frontend bleibt auch ohne laufenden Worker nutzbar.
          </div>
        )}
        {visibleJobs.map((job) => (
          <JobRow key={job.job_id} job={job} onCancel={(jobId) => cancelMutation.mutate(jobId)} />
        ))}
      </div>
    </div>
  );
}

function JobsSetupStatusPanel({
  activeJob,
  cancellingJobId,
  isFetching,
  onCancel,
  onRefresh,
  onStart,
  setupStatus,
  startingType
}: {
  activeJob?: Job;
  cancellingJobId: string | null;
  isFetching: boolean;
  onCancel: (jobId: string) => void;
  onRefresh: () => void;
  onStart: (step: SetupStep) => void;
  setupStatus?: SetupStatus;
  startingType: JobType | null;
}) {
  const steps = setupStatus?.steps ?? [];
  const nextStep = steps.find((step) => step.key === setupStatus?.next_step_key);
  const blockedByActiveJob = Boolean(activeJob);
  return (
    <section className="rounded border border-[#2d333d] bg-[#171a20] p-5">
      <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
        <div className="min-w-0">
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <h2 className="text-base font-semibold">Betriebsstatus</h2>
            <StatusChip tone={setupStatus ? toneForSetupOverall(setupStatus.status) : "neutral"}>
              {setupStatus ? setupOverallLabel(setupStatus.status) : "Lädt"}
            </StatusChip>
            {activeJob ? <StatusChip tone="warning">läuft: {activeJob.job_type}</StatusChip> : null}
          </div>
          <p className="max-w-4xl text-sm leading-6 text-[#a0a7b4]">
            {setupStatus?.summary ?? "Prüfe System, Depot, Kursdaten, Marktbreite, RS-Ratings, 13F-Daten und Positionsmonitor."}
          </p>
        </div>
        <div className="flex shrink-0 flex-wrap gap-2">
          <button
            className="inline-flex items-center gap-2 rounded border border-[#2d333d] bg-[#111419] px-3 py-2 text-sm transition hover:border-emerald-300/60"
            type="button"
            onClick={onRefresh}
          >
            <RotateCw size={15} className={isFetching ? "animate-spin text-emerald-300" : "text-[#a0a7b4]"} />
            Status prüfen
          </button>
          {nextStep?.job_type ? (
            <button
              className="inline-flex items-center justify-center gap-2 rounded bg-emerald-300 px-3 py-2 text-sm font-semibold text-[#101318] transition hover:bg-emerald-200 disabled:cursor-not-allowed disabled:opacity-50"
              disabled={blockedByActiveJob || startingType === nextStep.job_type}
              type="button"
              onClick={() => onStart(nextStep)}
            >
              <Play size={15} />
              {startingType === nextStep.job_type ? "Startet" : nextStep.action_label}
            </button>
          ) : nextStep?.href ? (
            <Link
              className="inline-flex items-center justify-center gap-2 rounded bg-emerald-300 px-3 py-2 text-sm font-semibold text-[#101318] transition hover:bg-emerald-200"
              href={nextStep.href}
            >
              {nextStep.action_label}
            </Link>
          ) : null}
          {activeJob ? (
            <button
              className="inline-flex items-center justify-center gap-2 rounded border border-amber-200/50 bg-[#111419] px-3 py-2 text-sm text-amber-100 transition hover:border-rose-200/70 disabled:cursor-not-allowed disabled:opacity-50"
              disabled={cancellingJobId === activeJob.job_id}
              type="button"
              onClick={() => onCancel(activeJob.job_id)}
            >
              <XCircle size={15} />
              {cancellingJobId === activeJob.job_id ? "Bricht ab" : "Job abbrechen"}
            </button>
          ) : null}
        </div>
      </div>
      {activeJob ? (
        <div className="mt-4 rounded border border-amber-300/35 bg-amber-300/10 p-3 text-sm text-amber-100">
          <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
            <div className="min-w-0">
              <div className="font-medium">Aktiver Job: {activeJob.job_type}</div>
              <div className="mt-1 text-xs leading-5 text-amber-100/80">
                {activeJob.current_step || activeJob.message || "Der Worker hat noch keinen Detailstatus gemeldet."}
              </div>
              <div className="mt-1 truncate text-xs text-amber-100/60">{activeJob.job_id}</div>
            </div>
            <div className="text-xs tabular-nums text-amber-100/80">{activeJob.progress}%</div>
          </div>
          <div className="mt-3 h-2 overflow-hidden rounded bg-[#111419]">
            <div className="h-2 rounded bg-emerald-300" style={{ width: `${activeJob.progress}%` }} />
          </div>
        </div>
      ) : null}
      {nextStep ? (
        <div className="mt-4 rounded border border-[#242a33] bg-[#111419] p-3 text-sm">
          <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
            <div>
              <div className="font-medium">Nächste Aktion: {nextStep.label}</div>
              <div className="mt-1 text-xs leading-5 text-[#8e97a6]">{nextStep.detail}</div>
            </div>
            <StatusChip tone={toneForSetupStep(nextStep.status)}>{shortSetupStatus(nextStep.status)}</StatusChip>
          </div>
        </div>
      ) : null}
      {steps.length > 0 ? (
        <div className="mt-4 grid gap-2 md:grid-cols-3 xl:grid-cols-7">
          {steps.map((step) => (
            <div key={step.key} className="rounded border border-[#242a33] bg-[#111419] p-3">
              <div className="mb-2 flex items-center justify-between gap-2">
                <span className="truncate text-xs font-medium">{step.label}</span>
                <StatusChip tone={toneForSetupStep(step.status)}>{shortSetupStatus(step.status)}</StatusChip>
              </div>
              <div className="line-clamp-2 text-xs leading-5 text-[#77808f]">{step.detail}</div>
            </div>
          ))}
        </div>
      ) : null}
    </section>
  );
}

function MarketDataAssistantPanel({
  activeJob,
  config,
  jobs,
  onStart,
  startingType
}: {
  activeJob?: Job;
  config: MarketDataBootstrapConfig;
  jobs: Job[];
  onStart: (type: JobType, payload: Record<string, unknown>) => void;
  startingType: JobType | null;
}) {
  const latestSmart = latestJobForType(jobs, "smart_refresh_market_data");
  const latestBootstrap = latestJobForType(jobs, "bootstrap_market_data");
  const disabled = Boolean(activeJob) || startingType === "smart_refresh_market_data" || startingType === "bootstrap_market_data";
  const smartPayload = buildSmartRefreshPayload(config);
  const initialPayload = buildBootstrapPayload(config, "initial");
  const updatePayload = buildBootstrapPayload(config, "update");
  const latestAssistantJob = newerJob(latestSmart, latestBootstrap);

  return (
    <section className="rounded border border-emerald-300/25 bg-[#171a20] p-5">
      <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
        <div className="max-w-4xl">
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <h2 className="text-lg font-semibold">Marktdaten-Assistent</h2>
            <StatusChip tone={activeJob ? "warning" : "good"}>{activeJob ? `läuft: ${activeJob.job_type}` : "bereit"}</StatusChip>
            {latestAssistantJob && <StatusChip tone={statusTone[latestAssistantJob.status]}>{jobStatusLabel(latestAssistantJob.status)}</StatusChip>}
          </div>
          <p className="text-sm leading-6 text-[#a0a7b4]">
            Für die Marktampel braucht die App ein gespeichertes US-Aktienuniversum, Kursdaten, Marktbreite und RS-Ratings.
            Alles smart aktualisieren prüft zuerst die Datenlage und aktualisiert nur fehlende oder veraltete Teile,
            inklusive 13F/SEC-Trends, wenn sie fehlen oder veraltet sind.
            Geplante Smart-Refreshes laufen automatisch um 16:00 und 22:30 Uhr deutscher Zeit und erzwingen den Market-Refresh-Pfad.
          </p>
          <div className="mt-3 grid gap-2 text-xs text-[#77808f] md:grid-cols-4">
            <span>Universe: US Common Stocks</span>
            <span>Limit: {config.storedUniverseLimit.toLocaleString("de-DE")} Ticker</span>
            <span>Initial: {config.priceRange}</span>
            <span>Breadth: {config.breadthLookbackDays.toLocaleString("de-DE")} Tage</span>
          </div>
        </div>
        <div className="flex shrink-0 flex-col gap-2 sm:flex-row xl:flex-col">
          <button
            className="inline-flex items-center justify-center gap-2 rounded border border-emerald-300/60 bg-emerald-300 px-4 py-3 text-sm font-semibold text-[#101318] transition hover:bg-emerald-200 disabled:cursor-not-allowed disabled:opacity-50"
            disabled={disabled}
            type="button"
            onClick={() => onStart("smart_refresh_market_data", smartPayload)}
          >
            <SearchCheck size={16} />
            {startingType === "smart_refresh_market_data" ? "Prüft" : "Alles smart aktualisieren"}
          </button>
          <button
            className="inline-flex items-center justify-center gap-2 rounded border border-emerald-300/50 bg-emerald-300/15 px-4 py-3 text-sm font-medium text-emerald-100 transition hover:border-emerald-200 disabled:cursor-not-allowed disabled:opacity-50"
            disabled={disabled}
            type="button"
            onClick={() => onStart("bootstrap_market_data", initialPayload)}
          >
            <WandSparkles size={16} />
            {startingType === "bootstrap_market_data" ? "Startet" : "Alles initialisieren"}
          </button>
          <button
            className="inline-flex items-center justify-center gap-2 rounded border border-[#2d333d] bg-[#111419] px-4 py-3 text-sm text-[#d8dde6] transition hover:border-emerald-300/60 disabled:cursor-not-allowed disabled:opacity-50"
            disabled={disabled}
            type="button"
            onClick={() => onStart("bootstrap_market_data", updatePayload)}
          >
            <RotateCw size={16} />
            Alles aktualisieren
          </button>
        </div>
      </div>
      {latestAssistantJob && (
        <div className="mt-4 rounded border border-[#2d333d] bg-[#111419] p-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <div className="text-sm font-medium">{latestAssistantJob.current_step}</div>
              <div className="mt-1 text-xs text-[#8e97a6]">{latestAssistantJob.message || "Noch keine Detailmeldung."}</div>
            </div>
            <StatusChip tone={statusTone[latestAssistantJob.status]}>{latestAssistantJob.progress}%</StatusChip>
          </div>
          <div className="mt-3 h-2 overflow-hidden rounded-full bg-[#242a33]">
            <div className="h-full rounded-full bg-emerald-300" style={{ width: `${latestAssistantJob.progress}%` }} />
          </div>
          {latestAssistantJob.error_message ? (
            <div className="mt-3 rounded border border-rose-300/30 bg-rose-300/10 p-3 text-sm text-rose-100">
              {latestAssistantJob.error_message}
            </div>
          ) : null}
        </div>
      )}
    </section>
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
            <option value="stored_universe">Gespeichertes US-Universe</option>
            <option value="market_core">Starter-Universum</option>
            <option value="volatility">Nur SPY, VIX, VXX</option>
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
          label="Universe Limit"
          max={10000}
          min={25}
          suffix="Ticker"
          value={config.storedUniverseLimit}
          onChange={(value) => onConfigChange({ storedUniverseLimit: value })}
        />
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
      <BootstrapExplanation config={config} />
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
              <details className="mt-3 rounded border border-[#242a33] bg-[#171a20] p-3 text-xs">
                <summary className="cursor-pointer text-[#a0a7b4]">Einstellungen anzeigen</summary>
                <p className="mt-2 leading-5 text-[#77808f]">{step.settings}</p>
                <pre className="mt-2 max-h-32 overflow-auto rounded border border-[#242a33] bg-[#0f1115] p-2 text-[#d8dde6]">
                  {JSON.stringify(step.payload, null, 2)}
                </pre>
              </details>
            </div>
          );
        })}
      </div>
    </section>
  );
}

function BootstrapExplanation({ config }: { config: MarketDataBootstrapConfig }) {
  return (
    <div className="mb-4 grid gap-3 xl:grid-cols-2">
      <div className="rounded border border-[#2d333d] bg-[#111419] p-4">
        <h3 className="text-sm font-semibold">Was bedeutet Price-Universum?</h3>
        <p className="mt-2 text-sm leading-6 text-[#a0a7b4]">{pricePresetHelp[config.pricePreset]}</p>
        <div className="mt-3 grid gap-2 text-xs text-[#77808f] md:grid-cols-2">
          <span>Range: {config.priceRange}</span>
          <span>Universe-Limit: {config.storedUniverseLimit.toLocaleString("de-DE")} Ticker</span>
          <span>Breadth: {config.breadthLookbackDays.toLocaleString("de-DE")} Tage</span>
          <span>RS: {config.rsLookbackDays.toLocaleString("de-DE")} Tage gegen {normalizeTicker(config.rsBenchmarkTicker) || "SPY"}</span>
        </div>
      </div>
      <div className="rounded border border-[#2d333d] bg-[#111419] p-4">
        <h3 className="text-sm font-semibold">Initialisierung auf der NAS</h3>
        <p className="mt-2 text-sm leading-6 text-[#a0a7b4]">
          Für den ersten Start: Market Prices, danach Market Breadth, danach RS Ratings. Fundamentals und
          Positionsmonitor sind optional und können später laufen. Auf der DS220+ wird nur ein schwerer Job gleichzeitig
          gestartet.
        </p>
      </div>
    </div>
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
            <StatusChip tone={statusTone[job.status]}>{jobStatusLabel(job.status)}</StatusChip>
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

function isActiveJob(job: Job) {
  return job.status === "queued" || job.status === "running";
}

function mergeJobs(...groups: Job[][]) {
  const seen = new Set<string>();
  return groups.flat().filter((job) => {
    if (seen.has(job.job_id)) return false;
    seen.add(job.job_id);
    return true;
  });
}

function newerJob(left?: Job, right?: Job) {
  if (!left) return right;
  if (!right) return left;
  return new Date(left.created_at).getTime() >= new Date(right.created_at).getTime() ? left : right;
}

function yahooProbeItems(job?: Job): YahooProbeItem[] {
  const rawItems = job?.result?.items;
  if (!Array.isArray(rawItems)) return [];
  return rawItems
    .filter((item): item is Record<string, unknown> => Boolean(item && typeof item === "object"))
    .map((item) => ({
      source_ticker: String(item.source_ticker ?? ""),
      best_candidate: String(item.best_candidate ?? ""),
      status: String(item.status ?? "unknown"),
      mapping_applied: Boolean(item.mapping_applied),
      candidates: Array.isArray(item.candidates)
        ? item.candidates
            .filter((candidate): candidate is Record<string, unknown> => Boolean(candidate && typeof candidate === "object"))
            .map((candidate) => ({
              symbol: String(candidate.symbol ?? ""),
              ok: Boolean(candidate.ok),
              records_seen: Number(candidate.records_seen ?? 0),
              last_date: typeof candidate.last_date === "string" ? candidate.last_date : null,
              error_message: String(candidate.error_message ?? "")
            }))
        : []
    }))
    .filter((item) => item.source_ticker);
}

function toneForYahooStatus(status: string, mappingApplied?: boolean): "good" | "neutral" | "warning" | "bad" {
  if (mappingApplied) return "good";
  if (status === "valid_current") return "good";
  if (status === "candidate_found") return "warning";
  if (status === "not_found") return "bad";
  return "neutral";
}

function latestFailedPriceTickers(jobs: Job[]) {
  const latest = jobs.find((job) => job.job_type === "refresh_prices");
  const result = latest?.result ?? {};
  const failedFromList = Array.isArray(result.failed_tickers)
    ? result.failed_tickers.map((value) => String(value))
    : [];
  const failedFromItems = Array.isArray(result.items)
    ? result.items
        .filter((item) => item && typeof item === "object" && (item as { ok?: unknown }).ok === false)
        .map((item) => String((item as { ticker?: unknown }).ticker ?? ""))
    : [];
  return uniqueTickers([...failedFromList, ...failedFromItems]).slice(0, 24);
}

function buildRefreshSequence(config: MarketDataBootstrapConfig): {
  type: JobType;
  label: string;
  description: string;
  settings: string;
  payload: Record<string, unknown>;
  disabled?: boolean;
}[] {
  const customTickers = config.pricePreset === "custom" ? parseTickers(config.customTickers) : [];
  const storedUniversePayload =
    config.pricePreset === "stored_universe"
      ? { universe: "us_common_stocks", limit_universe: config.storedUniverseLimit }
      : {};
  const customUniversePayload = customTickers.length > 0 ? { tickers: customTickers } : storedUniversePayload;
  const rsBenchmarkTicker = normalizeTicker(config.rsBenchmarkTicker) || "SPY";
  const pricePayload =
    config.pricePreset === "custom"
      ? {
          mode: "manual",
          range: config.priceRange,
          tickers: uniqueTickers([...customTickers, rsBenchmarkTicker, "SPY", "^VIX", "VXX"])
        }
      : config.pricePreset === "stored_universe"
        ? {
            mode: "manual",
            range: config.priceRange,
            universe: "us_common_stocks",
            limit_universe: config.storedUniverseLimit
          }
      : { mode: "manual", range: config.priceRange, preset: config.pricePreset };

  return [
    {
      type: "refresh_prices",
      label: "1. Market Prices",
      description: "OHLC-Cache für Market-, Benchmark- und Volatility-Ticker füllen.",
      settings: `Lädt Tageskurse für ${config.pricePreset}; Zeitraum ${config.priceRange}. Bei stored_universe werden maximal ${config.storedUniverseLimit} Ticker verwendet.`,
      payload: pricePayload,
      disabled: config.pricePreset === "custom" && customTickers.length === 0
    },
    {
      type: "refresh_breadth",
      label: "2. Market Breadth",
      description: "Marktbreite und MarketSnapshot aus gespeicherten Kursdaten vorberechnen.",
      settings: `Nutzt vorhandene Kurse aus Postgres, Lookback ${config.breadthLookbackDays} Tage. Kein yfinance im Request.`,
      payload: { mode: "manual", lookback_days: config.breadthLookbackDays, ...customUniversePayload }
    },
    {
      type: "refresh_relative_strength",
      label: "3. RS Ratings",
      description: "Relative Stärke aus gecachten Kursen berechnen.",
      settings: `Berechnet RS-Ratings gegen ${rsBenchmarkTicker} über ${config.rsLookbackDays} Tage aus gespeicherten Kursdaten.`,
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
      settings: "Lädt fundamentale Kennzahlen für das gewählte Universe. Dieser Job ist langsamer und für die Marktampel nicht zwingend nötig.",
      payload: { mode: "manual", include_holders: true, ...customUniversePayload }
    },
    {
      type: "position_atr_monitor",
      label: "5. Positionsmonitor",
      description: "Offene Positionen gegen gespeicherte Kursdaten und Sell-Engine prüfen.",
      settings: "Prüft importierte offene Positionen, aktualisiert Sell-Recommendation-State und nutzt vorhandene Kursdaten.",
      payload: { mode: "manual" }
    }
  ];
}

function buildBootstrapPayload(config: MarketDataBootstrapConfig, mode: "initial" | "update"): Record<string, unknown> {
  return {
    mode,
    source: "dashboard",
    universe: "us_common_stocks",
    limit_universe: config.storedUniverseLimit,
    range: mode === "initial" ? config.priceRange : "6m",
    breadth_lookback_days: config.breadthLookbackDays,
    rs_lookback_days: config.rsLookbackDays,
    benchmark_ticker: normalizeTicker(config.rsBenchmarkTicker) || "SPY",
    refresh_universe: mode === "initial"
  };
}

function buildSmartRefreshPayload(config: MarketDataBootstrapConfig): Record<string, unknown> {
  return {
    mode: "smart",
    source: "dashboard",
    universe: "us_common_stocks",
    limit_universe: config.storedUniverseLimit,
    range: "6m",
    initial_range: config.priceRange,
    price_batch_size: 50,
    price_overlap_days: 1,
    breadth_lookback_days: config.breadthLookbackDays,
    rs_lookback_days: config.rsLookbackDays,
    benchmark_ticker: normalizeTicker(config.rsBenchmarkTicker) || "SPY",
    include_position_monitor: true,
    include_fundamentals: true,
    force_fundamentals: true,
    fundamental_universe: "all",
    fundamental_limit: config.storedUniverseLimit,
    incremental_fundamentals: true,
    include_sec13f: true,
    force_sec13f: true,
    sec13f_universe: "us_common_stocks",
    sec13f_limit_universe: config.storedUniverseLimit
  };
}

function defaultPayloadForJob(type: JobType): Record<string, unknown> {
  if (type === "smart_refresh_market_data") {
    return {
      mode: "smart",
      source: "dashboard",
      range: "6m",
      initial_range: "2y",
      price_batch_size: 50,
      price_overlap_days: 1,
      universe: "us_common_stocks",
      limit_universe: 10000,
      breadth_lookback_days: 550,
      rs_lookback_days: 430,
      benchmark_ticker: "SPY",
      include_position_monitor: true,
      include_fundamentals: true,
      fundamental_universe: "all",
      fundamental_limit: 10000,
      incremental_fundamentals: true,
      include_sec13f: true,
      sec13f_universe: "us_common_stocks",
      sec13f_limit_universe: 10000
    };
  }
  if (type === "bootstrap_market_data") {
    return {
      mode: "update",
      source: "dashboard",
      range: "6m",
      universe: "us_common_stocks",
      limit_universe: 10000,
      breadth_lookback_days: 550,
      rs_lookback_days: 430,
      benchmark_ticker: "SPY",
      refresh_universe: false
    };
  }
  if (type === "refresh_prices") return { mode: "manual", range: "1y", preset: "all" };
  if (type === "refresh_breadth") return { mode: "manual", lookback_days: 550, universe: "us_common_stocks", limit_universe: 10000 };
  if (type === "refresh_relative_strength") {
    return { mode: "manual", lookback_days: 430, universe: "us_common_stocks", limit_universe: 10000 };
  }
  if (type === "refresh_fundamentals") return { mode: "manual", include_holders: true };
  if (type === "refresh_stock_detail") {
    return { ticker: "AAPL", source: "dashboard", range: "2y", benchmark_ticker: "SPY", include_13f: true };
  }
  if (type === "refresh_universe") return { mode: "manual", source: "dashboard" };
  if (type === "yahoo_symbol_diagnostics") return { mode: "manual", source: "dashboard", universe: "us_common_stocks", limit: 40 };
  if (type === "yahoo_symbol_rescue") return { mode: "manual", source: "dashboard", universe: "us_common_stocks", limit: 40 };
  if (type === "refresh_sec13f") {
    return { mode: "manual", universe: "open_positions", dataset_count: 2, limit_universe: 120 };
  }
  return { mode: "manual" };
}

function loadBootstrapConfig(): MarketDataBootstrapConfig {
  if (typeof window === "undefined") return defaultBootstrapConfig;
  try {
    const raw = window.localStorage.getItem(BOOTSTRAP_CONFIG_STORAGE_KEY);
    if (!raw) return defaultBootstrapConfig;
    return sanitizeBootstrapConfig(JSON.parse(raw));
  } catch {
    return defaultBootstrapConfig;
  }
}

function sanitizeBootstrapConfig(value: unknown): MarketDataBootstrapConfig {
  if (!value || typeof value !== "object") return defaultBootstrapConfig;
  const candidate = value as Partial<MarketDataBootstrapConfig>;
  return {
    pricePreset: isPricePreset(candidate.pricePreset) ? candidate.pricePreset : defaultBootstrapConfig.pricePreset,
    priceRange: isPriceRange(candidate.priceRange) ? candidate.priceRange : defaultBootstrapConfig.priceRange,
    storedUniverseLimit: clampNumber(
      Number(candidate.storedUniverseLimit),
      25,
      10000,
      defaultBootstrapConfig.storedUniverseLimit
    ),
    customTickers: typeof candidate.customTickers === "string" ? candidate.customTickers : "",
    breadthLookbackDays: clampNumber(
      Number(candidate.breadthLookbackDays),
      90,
      2000,
      defaultBootstrapConfig.breadthLookbackDays
    ),
    rsLookbackDays: clampNumber(
      Number(candidate.rsLookbackDays),
      120,
      2000,
      defaultBootstrapConfig.rsLookbackDays
    ),
    rsBenchmarkTicker: normalizeTicker(candidate.rsBenchmarkTicker || defaultBootstrapConfig.rsBenchmarkTicker) || "SPY"
  };
}

function isPricePreset(value: unknown): value is PricePreset {
  return ["all", "stored_universe", "market_core", "volatility", "sector", "custom"].includes(String(value));
}

function isPriceRange(value: unknown): value is PriceRange {
  return ["1m", "3m", "6m", "1y", "2y", "5y"].includes(String(value));
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

function toneForSetupOverall(status: SetupStatus["status"]): "good" | "neutral" | "warning" | "bad" {
  if (status === "ready") return "good";
  if (status === "running") return "warning";
  if (status === "blocked") return "bad";
  return "warning";
}

function toneForSetupStep(status: SetupStep["status"]): "good" | "neutral" | "warning" | "bad" {
  if (status === "complete") return "good";
  if (status === "running" || status === "warning") return "warning";
  if (status === "blocked" || status === "error") return "bad";
  return "neutral";
}

function shortSetupStatus(status: SetupStep["status"]) {
  if (status === "complete") return "ok";
  if (status === "pending") return "offen";
  if (status === "running") return "läuft";
  if (status === "warning") return "prüfen";
  if (status === "blocked") return "blockiert";
  return "fehler";
}

function jobStatusLabel(status: JobStatus) {
  return ({ queued: "Wartet", running: "Läuft", done: "Abgeschlossen", failed: "Fehlgeschlagen", skipped: "Übersprungen", cancelled: "Abgebrochen" } as const)[status];
}

function setupOverallLabel(status: SetupStatus["status"]) {
  return ({ ready: "Bereit", running: "Läuft", blocked: "Blockiert", incomplete: "Unvollständig", error: "Fehler" } as Record<string, string>)[status] ?? status;
}
