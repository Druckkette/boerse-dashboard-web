"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BellOff, Minus, Plus, Save } from "lucide-react";
import { useParams } from "next/navigation";
import { useState } from "react";
import { KpiCard } from "@/components/ui/kpi-card";
import { StatusChip } from "@/components/ui/status-chip";
import { StockPricePanel } from "@/features/stocks/stock-price-panel";
import { api } from "@/lib/api/client";
import type { PendingStatus, SellManualInput, SellSignal } from "@/lib/types/api";

const toneByStatus = {
  Halten: "good",
  Beobachten: "warning",
  Verkaufen: "bad"
} as const;

const toneByPending: Record<PendingStatus, "good" | "neutral" | "warning" | "bad"> = {
  halten: "good",
  in_bestaetigung: "warning",
  snoozed: "neutral",
  scharf: "bad"
};

export default function SellMonitorTickerPage() {
  const params = useParams<{ ticker: string }>();
  const ticker = params.ticker.toUpperCase();
  const queryClient = useQueryClient();
  const metrics = useQuery({ queryKey: ["sell-metrics", ticker], queryFn: () => api.sellMetrics(ticker) });
  const evaluation = useQuery({ queryKey: ["sell-evaluation", ticker], queryFn: () => api.sellEvaluation(ticker) });
  const [manualDraft, setManualDraft] = useState<{ ticker: string; value: SellManualInput } | null>(null);
  const [tranchePct, setTranchePct] = useState(25);
  const [trancheReason, setTrancheReason] = useState("Manuelle Tranche");

  const saveManual = useMutation({
    mutationFn: (nextManual: SellManualInput) => api.patchSellManual(ticker, nextManual),
    onSuccess: (updated) => {
      setManualDraft(null);
      queryClient.setQueryData(["sell-evaluation", ticker], evaluation.data ? { ...evaluation.data, manual: updated } : evaluation.data);
      queryClient.invalidateQueries({ queryKey: ["sell-evaluation", ticker] });
      queryClient.invalidateQueries({ queryKey: ["sell-ranking"] });
    }
  });

  const trancheMutation = useMutation({
    mutationFn: () =>
      api.createSellTranche(ticker, {
        ticker,
        pct: tranchePct,
        reason: trancheReason || "Manuelle Tranche"
      }),
    onSuccess: (payload) => {
      queryClient.setQueryData(
        ["sell-evaluation", ticker],
        evaluation.data ? { ...evaluation.data, tranche_log: payload.tranche_log } : evaluation.data
      );
      queryClient.invalidateQueries({ queryKey: ["sell-evaluation", ticker] });
      queryClient.invalidateQueries({ queryKey: ["sell-ranking"] });
    }
  });

  const snoozeMutation = useMutation({
    mutationFn: () => api.snoozeSellSignal(ticker, { snoozed_pct: 100, days: 5 }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["sell-evaluation", ticker] });
      queryClient.invalidateQueries({ queryKey: ["sell-ranking"] });
    }
  });

  const currentManual =
    manualDraft?.ticker === ticker ? manualDraft.value : evaluation.data?.manual ?? null;
  const manualDirty = manualDraft?.ticker === ticker;
  const storedAtr = currentManual?.sell_setup?.atr_multiple;
  const atrMultiple = typeof storedAtr === "number" ? storedAtr : 1.5;

  const mainSignals = [
    ...(evaluation.data?.killer_signals ?? []),
    ...(evaluation.data?.tranche_signals ?? [])
  ].slice(0, 5);
  const warningSignals = [
    ...(evaluation.data?.warning_signals ?? []),
    ...(evaluation.data?.watch_signals ?? [])
  ].slice(0, 6);

  function updateManual(patch: Partial<SellManualInput>) {
    setManualDraft((previous) => {
      const base = previous?.ticker === ticker ? previous.value : evaluation.data?.manual;
      return base ? { ticker, value: { ...base, ...patch, ticker } } : previous;
    });
  }

  function updateAtr(nextValue: number) {
    const clamped = Math.max(0.5, Math.min(4, Math.round(nextValue * 10) / 10));
    const sellSetup = { ...(currentManual?.sell_setup ?? {}), atr_multiple: clamped };
    updateManual({ sell_setup: sellSetup });
  }

  function updateNullableNumber(key: "pivot" | "low_day_1" | "low_day_0", value: string) {
    updateManual({ [key]: value === "" ? null : Number(value) });
  }

  function persistManual() {
    if (!currentManual) return;
    saveManual.mutate({
      ...currentManual,
      ticker,
      sell_setup: { ...currentManual.sell_setup, atr_multiple: atrMultiple }
    });
  }

  const health = evaluation.data?.health ?? metrics.data?.health;
  const recommendationTone =
    (evaluation.data?.recommendation_percent ?? 0) >= 75
      ? "bad"
      : (evaluation.data?.recommendation_percent ?? 0) > 0
        ? "warning"
        : "good";
  const priceDataSource = dataSourceFromMetrics(metrics.data?.raw_payload.metrics, "price_data_source");
  const benchmarkDataSource = dataSourceFromMetrics(metrics.data?.raw_payload.metrics, "benchmark_data_source");

  return (
    <div className="space-y-5">
      <div className="rounded border border-[#2d333d] bg-[#171a20] p-5">
        <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div>
            <div className="text-sm text-[#a0a7b4]">Sell Monitor</div>
            <h1 className="text-3xl font-semibold">{ticker}</h1>
            <div className="mt-2 text-sm text-[#a0a7b4]">
              {evaluation.data?.explanation_short ?? "Evaluation wird geladen."}
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <StatusChip tone={health ? toneByStatus[health.status] : "neutral"}>
              {health?.status ?? "lädt"}
            </StatusChip>
            <StatusChip tone={evaluation.data ? toneByPending[evaluation.data.pending_status] : "neutral"}>
              {evaluation.data?.display_label ?? "loading"}
            </StatusChip>
            <StatusChip tone={toneForDataSource(priceDataSource)}>
              {labelForDataSource(priceDataSource)}
            </StatusChip>
          </div>
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
        <KpiCard item={{ label: "Health Score", value: health ? health.health_score.toFixed(1) : "-", detail: health?.rs_trend ?? "RS Trend", tone: health ? toneByStatus[health.status] : "neutral" }} />
        <KpiCard item={{ label: "Empfehlung", value: `${evaluation.data?.sell_now_percent ?? 0}%`, detail: evaluation.data?.regime ?? "Regime", tone: recommendationTone }} />
        <KpiCard item={{ label: "P&L", value: formatPct(metrics.data?.pnl_pct), detail: "seit Kauf", tone: (metrics.data?.pnl_pct ?? 0) >= 0 ? "good" : "bad" }} />
        <KpiCard item={{ label: "ATR14", value: formatNumber(metrics.data?.atr14), detail: `x ${atrMultiple.toFixed(1)} lokal`, tone: "neutral" }} />
        <KpiCard item={{ label: "Datenquelle", value: labelForDataSource(priceDataSource), detail: `Benchmark: ${labelForDataSource(benchmarkDataSource)}`, tone: toneForDataSource(priceDataSource) }} />
      </div>

      <div className="grid gap-5 xl:grid-cols-[1.35fr_0.9fr]">
        <div className="space-y-5">
          <section className="rounded border border-[#2d333d] bg-[#171a20] p-5">
            <div className="mb-4 flex items-center justify-between gap-3">
              <div>
                <h2 className="text-base font-semibold">ATR / Stop / Signal</h2>
                <div className="text-sm text-[#a0a7b4]">Lokale ATR-Änderungen blockieren keine Queries.</div>
              </div>
              <StatusChip tone={manualDirty ? "warning" : "good"}>
                {manualDirty ? "ungespeichert" : "synchron"}
              </StatusChip>
            </div>
            <div className="grid gap-3 md:grid-cols-3">
              <MetricTile label="Stop" value={formatCurrency(evaluation.data?.stop_price)} detail={evaluation.data?.sell_mode || "Regel-Engine"} />
              <MetricTile label="Nächste Tranche" value={formatCurrency(evaluation.data?.next_tranche_trigger_price)} detail={evaluation.data?.sell_style || "Signalmarke"} />
              <MetricTile label="Full Exit" value={formatCurrency(evaluation.data?.full_exit_price)} detail={evaluation.data?.pending_status ?? "Status"} />
            </div>
            <div className="mt-4 flex flex-wrap items-center gap-3">
              <button
                aria-label="ATR-Multiplikator senken"
                className="flex size-10 items-center justify-center rounded border border-[#2d333d] bg-[#111419] transition hover:border-emerald-300/60"
                type="button"
                onClick={() => updateAtr(atrMultiple - 0.1)}
              >
                <Minus size={16} />
              </button>
              <input
                aria-label="ATR-Multiplikator"
                className="min-w-[180px] flex-1 accent-emerald-300"
                max="4"
                min="0.5"
                step="0.1"
                type="range"
                value={atrMultiple}
                onChange={(event) => updateAtr(Number(event.target.value))}
                onInput={(event) => updateAtr(Number(event.currentTarget.value))}
              />
              <div className="w-16 rounded border border-[#2d333d] bg-[#111419] px-3 py-2 text-right tabular-nums">
                {atrMultiple.toFixed(1)}
              </div>
              <button
                aria-label="ATR-Multiplikator erhöhen"
                className="flex size-10 items-center justify-center rounded border border-[#2d333d] bg-[#111419] transition hover:border-emerald-300/60"
                type="button"
                onClick={() => updateAtr(atrMultiple + 0.1)}
              >
                <Plus size={16} />
              </button>
            </div>
          </section>

          <StockPricePanel ticker={ticker} title="Sell Context" />

          <section className="rounded border border-[#2d333d] bg-[#171a20] p-5">
            <h2 className="mb-4 text-base font-semibold">Hauptgründe</h2>
            <SignalList signals={mainSignals} empty="Keine aktiven Hauptsignale." />
          </section>

          <section className="rounded border border-[#2d333d] bg-[#171a20] p-5">
            <h2 className="mb-4 text-base font-semibold">Warnungen</h2>
            <SignalList signals={warningSignals} empty="Keine Warnungen im aktuellen Dummy-Szenario." />
          </section>
        </div>

        <aside className="space-y-5">
          <section className="rounded border border-[#2d333d] bg-[#171a20] p-5">
            <div className="mb-4 flex items-center justify-between gap-3">
              <h2 className="text-base font-semibold">Manuelle Inputs</h2>
              <button
                className="inline-flex items-center gap-2 rounded border border-emerald-300/35 bg-emerald-300/10 px-3 py-2 text-sm text-emerald-100 transition hover:border-emerald-200 disabled:cursor-not-allowed disabled:opacity-50"
                disabled={!currentManual || saveManual.isPending || !manualDirty}
                type="button"
                onClick={persistManual}
              >
                <Save size={15} />
                {saveManual.isPending ? "Speichert" : "Speichern"}
              </button>
            </div>
            {currentManual && (
              <div className="space-y-4">
                <label className="block text-sm">
                  <span className="mb-1 block text-[#a0a7b4]">Marktumfeld</span>
                  <select
                    className="w-full rounded border border-[#2d333d] bg-[#111419] px-3 py-2"
                    value={currentManual.market_environment}
                    onChange={(event) => updateManual({ market_environment: event.target.value as SellManualInput["market_environment"] })}
                  >
                    <option>Bullisch</option>
                    <option>Unsicher</option>
                    <option>Bärisch</option>
                  </select>
                </label>
                <label className="block text-sm">
                  <span className="mb-1 block text-[#a0a7b4]">Industriegruppe</span>
                  <select
                    className="w-full rounded border border-[#2d333d] bg-[#111419] px-3 py-2"
                    value={currentManual.industry_group_status}
                    onChange={(event) => updateManual({ industry_group_status: event.target.value as SellManualInput["industry_group_status"] })}
                  >
                    <option>Stark</option>
                    <option>Neutral</option>
                    <option>Schwach</option>
                  </select>
                </label>
                <div className="grid gap-3 sm:grid-cols-3 xl:grid-cols-1">
                  <NumberField label="Pivot" value={currentManual.pivot} onChange={(value) => updateNullableNumber("pivot", value)} />
                  <NumberField label="Tief Tag 1" value={currentManual.low_day_1} onChange={(value) => updateNullableNumber("low_day_1", value)} />
                  <NumberField label="Tief Tag 0" value={currentManual.low_day_0} onChange={(value) => updateNullableNumber("low_day_0", value)} />
                </div>
                <label className="flex items-center justify-between gap-3 rounded border border-[#2d333d] bg-[#111419] px-3 py-2 text-sm">
                  <span>Persönlichkeits-Check</span>
                  <input
                    checked={currentManual.personality_changed}
                    className="size-4 accent-emerald-300"
                    type="checkbox"
                    onChange={(event) => updateManual({ personality_changed: event.target.checked })}
                  />
                </label>
              </div>
            )}
          </section>

          <section className="rounded border border-[#2d333d] bg-[#171a20] p-5">
            <div className="mb-4 flex items-center justify-between gap-3">
              <h2 className="text-base font-semibold">Tranche-Log</h2>
              <StatusChip tone="neutral">{evaluation.data?.already_sold_percent ?? 0}% verkauft</StatusChip>
            </div>
            <div className="space-y-2">
              {(evaluation.data?.tranche_log ?? []).length === 0 && (
                <div className="text-sm text-[#a0a7b4]">Noch keine Tranchen erfasst.</div>
              )}
              {(evaluation.data?.tranche_log ?? []).map((entry) => (
                <div key={`${entry.created_at}-${entry.pct}`} className="border-b border-[#242a33] pb-2 text-sm">
                  <div className="flex justify-between gap-3">
                    <span>{entry.reason || "Tranche"}</span>
                    <span className="tabular-nums">{entry.pct}%</span>
                  </div>
                  <div className="mt-1 text-xs text-[#a0a7b4]">{entry.date}</div>
                </div>
              ))}
            </div>
            <div className="mt-4 grid gap-3 sm:grid-cols-[110px_1fr] xl:grid-cols-1">
              <input
                aria-label="Tranche Prozent"
                className="rounded border border-[#2d333d] bg-[#111419] px-3 py-2 text-sm"
                max={100}
                min={0}
                step={1}
                type="number"
                value={tranchePct}
                onChange={(event) => setTranchePct(Number(event.target.value))}
              />
              <input
                aria-label="Tranche Grund"
                className="rounded border border-[#2d333d] bg-[#111419] px-3 py-2 text-sm"
                value={trancheReason}
                onChange={(event) => setTrancheReason(event.target.value)}
              />
              <button
                className="inline-flex items-center justify-center gap-2 rounded border border-[#2d333d] bg-[#111419] px-3 py-2 text-sm transition hover:border-emerald-300/60 disabled:cursor-not-allowed disabled:opacity-50 sm:col-span-2 xl:col-span-1"
                disabled={trancheMutation.isPending}
                type="button"
                onClick={() => trancheMutation.mutate()}
              >
                <Plus size={15} />
                Tranche erfassen
              </button>
            </div>
          </section>

          <section className="rounded border border-[#2d333d] bg-[#171a20] p-5">
            <div className="mb-3 flex items-center justify-between gap-3">
              <h2 className="text-base font-semibold">Recommendation State</h2>
              <StatusChip tone={evaluation.data ? toneByPending[evaluation.data.pending_status] : "neutral"}>
                {evaluation.data?.pending_status ?? "loading"}
              </StatusChip>
            </div>
            <div className="space-y-2 text-sm">
              <StateRow label="Streak" value={`${evaluation.data?.next_recommendation_state.consecutive_days ?? 0} Tage`} />
              <StateRow label="Letzte Quote" value={`${evaluation.data?.next_recommendation_state.last_pct ?? 0}%`} />
              <StateRow label="Snooze bis" value={evaluation.data?.next_recommendation_state.snoozed_until || "-"} />
            </div>
            <button
              className="mt-4 inline-flex w-full items-center justify-center gap-2 rounded border border-[#2d333d] bg-[#111419] px-3 py-2 text-sm transition hover:border-amber-300/60 disabled:cursor-not-allowed disabled:opacity-50"
              disabled={snoozeMutation.isPending}
              type="button"
              onClick={() => snoozeMutation.mutate()}
            >
              <BellOff size={15} />
              Signal 5 Tage snoozen
            </button>
          </section>
        </aside>
      </div>
    </div>
  );
}

function SignalList({ signals, empty }: { signals: SellSignal[]; empty: string }) {
  if (signals.length === 0) {
    return <div className="text-sm text-[#a0a7b4]">{empty}</div>;
  }
  return (
    <div className="grid gap-3 md:grid-cols-2">
      {signals.map((signal) => (
        <div key={`${signal.severity}-${signal.id}`} className="rounded border border-[#2d333d] bg-[#111419] p-3">
          <div className="mb-2 flex items-start justify-between gap-3">
            <div className="font-medium">{signal.label}</div>
            <StatusChip tone={signal.severity === "killer" ? "bad" : signal.severity === "tranche" ? "warning" : "neutral"}>
              {signal.contribution_percent}%
            </StatusChip>
          </div>
          <div className="text-sm text-[#a0a7b4]">{signal.event_note || signal.strategy_key}</div>
        </div>
      ))}
    </div>
  );
}

function MetricTile({ label, value, detail }: { label: string; value: string; detail: string }) {
  return (
    <div className="rounded border border-[#2d333d] bg-[#111419] p-3">
      <div className="text-xs uppercase text-[#a0a7b4]">{label}</div>
      <div className="mt-2 text-xl font-semibold tabular-nums">{value}</div>
      <div className="mt-1 line-clamp-2 text-xs text-[#a0a7b4]">{detail}</div>
    </div>
  );
}

function NumberField({
  label,
  value,
  onChange
}: {
  label: string;
  value?: number | null;
  onChange: (value: string) => void;
}) {
  return (
    <label className="block text-sm">
      <span className="mb-1 block text-[#a0a7b4]">{label}</span>
      <input
        className="w-full rounded border border-[#2d333d] bg-[#111419] px-3 py-2"
        step="0.01"
        type="number"
        value={value ?? ""}
        onChange={(event) => onChange(event.target.value)}
      />
    </label>
  );
}

function StateRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between border-b border-[#242a33] pb-2">
      <span className="text-[#a0a7b4]">{label}</span>
      <span>{value}</span>
    </div>
  );
}

function formatNumber(value?: number | null) {
  return value == null ? "-" : value.toFixed(2);
}

function formatPct(value?: number | null) {
  return value == null ? "-" : `${value.toFixed(1)}%`;
}

function formatCurrency(value?: number | null) {
  return value == null ? "-" : value.toFixed(2);
}

function dataSourceFromMetrics(metrics?: Record<string, unknown>, key?: string) {
  const value = key ? metrics?.[key] : undefined;
  return typeof value === "string" ? value : "";
}

function labelForDataSource(value: string) {
  if (value === "database") return "Price Cache";
  if (value === "synthetic_fallback") return "Fallback";
  if (value === "synthetic_fixture") return "Fixture";
  return "unbekannt";
}

function toneForDataSource(value: string): "good" | "neutral" | "warning" | "bad" {
  if (value === "database") return "good";
  if (value === "synthetic_fixture") return "neutral";
  if (value === "synthetic_fallback") return "warning";
  return "neutral";
}
