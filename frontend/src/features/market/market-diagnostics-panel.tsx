"use client";

import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, CircleDashed, RotateCw } from "lucide-react";
import { StatusChip } from "@/components/ui/status-chip";
import { api } from "@/lib/api/client";
import type {
  MarketDiagnosticCheck,
  MarketIntermarketItem,
  MarketSectorRotationGroup,
  Tone
} from "@/lib/types/api";
import { labelForSource, labelForStatus, toneForSource, toneForStatus } from "./data-status";
import { MARKET_REFETCH_INTERVAL_MS } from "./query-timing";

export function MarketDiagnosticsPanel() {
  const query = useQuery({
    queryKey: ["market-diagnostics"],
    queryFn: api.marketDiagnostics,
    staleTime: 60_000,
    refetchInterval: MARKET_REFETCH_INTERVAL_MS
  });
  const data = query.data;

  if (query.isLoading) {
    return (
      <section className="rounded border border-[#2d333d] bg-[#171a20] p-5 text-sm text-[#a0a7b4]">
        Markt-Diagnose lädt...
      </section>
    );
  }

  if (query.error || !data) {
    return (
      <section className="rounded border border-rose-400/40 bg-rose-400/10 p-5 text-sm text-rose-100">
        Markt-Diagnose ist aktuell nicht erreichbar.
      </section>
    );
  }

  return (
    <section className="space-y-4">
      <div className="rounded border border-[#2d333d] bg-[#171a20] p-5">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <div className="mb-3 flex flex-wrap items-center gap-2">
              <StatusChip tone={warningTone(data.warning_count)}>{data.warning_count} Warnzeichen</StatusChip>
              <StatusChip tone={toneForSource(data.source)}>{labelForSource(data.source)}</StatusChip>
              <StatusChip tone={toneForStatus(data.data_status)}>{labelForStatus(data.data_status)}</StatusChip>
              {data.defensive_lead !== null && data.defensive_lead !== undefined && (
                <StatusChip tone={data.defensive_lead ? "warning" : "good"}>
                  {data.defensive_lead ? "Defensiv führt" : "Offensiv bestätigt"}
                </StatusChip>
              )}
            </div>
            <h2 className="text-xl font-semibold tracking-normal">Tägliche Markt-Diagnose</h2>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-[#a0a7b4]">{data.summary}</p>
            {data.message && <p className="mt-2 max-w-3xl text-xs leading-5 text-[#77808f]">{data.message}</p>}
          </div>
          <button
            className="inline-flex w-fit items-center gap-2 rounded border border-[#2d333d] bg-[#111419] px-3 py-2 text-sm text-[#d8dde6] transition hover:border-emerald-300/60"
            type="button"
            onClick={() => query.refetch()}
          >
            <RotateCw size={15} className={query.isFetching ? "animate-spin text-emerald-300" : "text-[#a0a7b4]"} />
            Aktualisieren
          </button>
        </div>
      </div>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.35fr)_minmax(340px,0.65fr)]">
        <Checklist checks={data.checklist} />
        <SectorRotation groups={data.sector_rotation} spread={data.defensive_spread_pct} />
      </div>
      <IntermarketTable items={data.intermarket} />
    </section>
  );
}

function Checklist({ checks }: { checks: MarketDiagnosticCheck[] }) {
  return (
    <div className="rounded border border-[#2d333d] bg-[#171a20] p-4">
      <div className="mb-4 flex items-center justify-between gap-3">
        <div>
          <h3 className="text-base font-semibold">Checkliste</h3>
          <p className="text-sm text-[#a0a7b4]">Streamlit-Regeln als API-Auswertung, ohne Live-Refresh im Klickpfad.</p>
        </div>
        <StatusChip tone="neutral">{checks.length} Regeln</StatusChip>
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        {checks.map((check) => (
          <div key={`${check.category}-${check.label}`} className="rounded border border-[#242a33] bg-[#111419] p-3">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="text-sm font-medium text-[#d8dde6]">{check.label}</div>
                <div className="mt-1 text-xs leading-5 text-[#77808f]">{check.detail}</div>
              </div>
              <CheckIcon passed={check.passed} tone={check.tone} />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function SectorRotation({
  groups,
  spread
}: {
  groups: MarketSectorRotationGroup[];
  spread?: number | null;
}) {
  return (
    <div className="rounded border border-[#2d333d] bg-[#171a20] p-4">
      <div className="mb-4 flex items-center justify-between gap-3">
        <div>
          <h3 className="text-base font-semibold">Sektorrotation 10T</h3>
          <p className="text-sm text-[#a0a7b4]">Defensive gegen offensive Leader aus dem Price-Cache.</p>
        </div>
        <StatusChip tone={spread && spread > 0 ? "warning" : "good"}>Spread {formatPct(spread)}</StatusChip>
      </div>
      {groups.length === 0 ? (
        <div className="rounded border border-[#242a33] bg-[#111419] p-3 text-sm text-[#a0a7b4]">
          Keine Sektor-ETF-Daten im Cache.
        </div>
      ) : (
        <div className="space-y-4">
          {groups.map((group) => (
            <div key={group.group}>
              <div className="mb-2 flex items-center justify-between gap-3 text-xs uppercase text-[#77808f]">
                <span>{group.label}</span>
                <span className={pctClass(group.avg_return_10d_pct)}>{formatPct(group.avg_return_10d_pct)}</span>
              </div>
              <div className="space-y-2">
                {group.items.map((item) => (
                  <div key={item.ticker} className="flex items-center justify-between gap-3 text-sm">
                    <div>
                      <div className="font-medium text-[#d8dde6]">{item.ticker}</div>
                      <div className="text-xs text-[#77808f]">{item.name}</div>
                    </div>
                    <div className={["tabular-nums", pctClass(item.return_10d_pct)].join(" ")}>
                      {formatPct(item.return_10d_pct)}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function IntermarketTable({ items }: { items: MarketIntermarketItem[] }) {
  return (
    <div className="rounded border border-[#2d333d] bg-[#171a20] p-4">
      <div className="mb-4">
        <h3 className="text-base font-semibold">Intermarket-Bild</h3>
        <p className="text-sm text-[#a0a7b4]">
          Tagesveränderung und Abstand zum vorherigen 20-Tage-Hoch zeigen, ob wichtige Indizes Stärke gemeinsam
          bestätigen.
        </p>
      </div>
      {items.length === 0 ? (
        <div className="rounded border border-[#242a33] bg-[#111419] p-3 text-sm text-[#a0a7b4]">
          Keine Indexdaten für SPY, QQQ oder IWM im Cache.
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[720px] border-collapse text-sm">
            <thead>
              <tr className="border-b border-[#2d333d] text-left text-xs uppercase text-[#77808f]">
                <th className="py-3 pr-3">Index</th>
                <th className="px-3 py-3 text-right">Close</th>
                <th className="px-3 py-3 text-right">Tag</th>
                <th className="px-3 py-3 text-right">Zum 20T-Hoch</th>
                <th className="px-3 py-3 text-right">Status</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.ticker} className="border-b border-[#242a33] last:border-0">
                  <td className="py-3 pr-3">
                    <div className="font-medium text-[#d8dde6]">{item.name}</div>
                    <div className="text-xs text-[#77808f]">{item.ticker}</div>
                  </td>
                  <td className="px-3 py-3 text-right tabular-nums text-[#d8dde6]">{formatNumber(item.close)}</td>
                  <td className={["px-3 py-3 text-right tabular-nums", pctClass(item.day_pct)].join(" ")}>
                    {formatPct(item.day_pct)}
                  </td>
                  <td className={["px-3 py-3 text-right tabular-nums", pctClass(item.dist_to_20d_high_pct)].join(" ")}>
                    {formatPct(item.dist_to_20d_high_pct)}
                  </td>
                  <td className="px-3 py-3 text-right">
                    <StatusChip tone={item.tone}>{item.status}</StatusChip>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function CheckIcon({ passed, tone }: { passed: boolean; tone: Tone }) {
  if (passed) return <CheckCircle2 className="mt-0.5 shrink-0 text-emerald-300" size={18} />;
  if (tone === "bad") return <AlertTriangle className="mt-0.5 shrink-0 text-rose-300" size={18} />;
  return <CircleDashed className="mt-0.5 shrink-0 text-amber-300" size={18} />;
}

function warningTone(count: number): Tone {
  if (count <= 0) return "good";
  if (count <= 2) return "warning";
  return "bad";
}

function pctClass(value?: number | null) {
  if (value === null || value === undefined) return "text-[#77808f]";
  return value >= 0 ? "text-emerald-200" : "text-rose-200";
}

function formatPct(value?: number | null) {
  if (value === null || value === undefined) return "-";
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
}

function formatNumber(value?: number | null) {
  if (value === null || value === undefined) return "-";
  return new Intl.NumberFormat("de-DE", { maximumFractionDigits: 2 }).format(value);
}
