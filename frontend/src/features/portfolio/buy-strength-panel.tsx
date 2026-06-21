"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowRight, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { StatusChip } from "@/components/ui/status-chip";
import { api } from "@/lib/api/client";
import type { BuyStrengthSummaryItem } from "@/lib/types/api";

const statusTone: Record<BuyStrengthSummaryItem["status"], "good" | "neutral" | "warning" | "bad"> = {
  stark: "good",
  ok: "neutral",
  watch: "warning",
  risk: "bad",
  missing: "neutral"
};

export function BuyStrengthPanel() {
  const query = useQuery({
    queryKey: ["portfolio-buy-strength"],
    queryFn: api.portfolioBuyStrength,
    staleTime: 60_000
  });
  const items = query.data?.items ?? [];

  return (
    <section className="rounded border border-[#2d333d] bg-[#171a20] p-5">
      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h2 className="text-base font-semibold">Stärke nach Kauf Check</h2>
          <p className="mt-1 text-sm text-[#a0a7b4]">
            Frische Käufe unter drei Wochen werden aus Kaufdatum, CSV-Import oder Trade-Republic-Import automatisch erkannt.
          </p>
        </div>
        <StatusChip tone={items.length ? "warning" : "neutral"}>
          {query.isLoading ? "lädt" : `${items.length} frisch`}
        </StatusChip>
      </div>

      {items.length === 0 ? (
        <div className="rounded border border-[#2d333d] bg-[#111419] p-4 text-sm text-[#a0a7b4]">
          Keine frischen Käufe im Depot. Manuell erfasste Positionen erscheinen hier, sobald ein Kaufdatum innerhalb der letzten drei Wochen gespeichert ist.
        </div>
      ) : (
        <div className="grid gap-3 xl:grid-cols-3">
          {items.map((item) => (
            <Link
              key={item.ticker}
              className="group rounded border border-[#2d333d] bg-[#111419] p-4 transition hover:border-emerald-300/50 hover:bg-[#151a20]"
              href={`/portfolio/buy-strength/${item.ticker}`}
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="text-lg font-semibold">{item.ticker}</div>
                  <div className="text-xs text-[#a0a7b4]">{item.name || item.buy_date}</div>
                </div>
                <StatusChip tone={statusTone[item.status]}>{item.status_label}</StatusChip>
              </div>
              <div className="mt-4 grid grid-cols-3 gap-2 text-sm">
                <Metric label="Alter" value={`${item.age_days}T`} />
                <Metric label="P&L" value={formatPercent(item.pnl_pct)} tone={(item.pnl_pct ?? 0) >= 0 ? "good" : "bad"} />
                <Metric label="Warnungen" value={`${item.warnings_active}/${item.warnings_total}`} tone={item.warnings_active ? "bad" : "good"} />
              </div>
              <div className="mt-4 flex items-center justify-between gap-3 text-xs text-[#a0a7b4]">
                <span className="inline-flex items-center gap-1">
                  <ShieldCheck size={14} />
                  {item.checks_passed}/{item.checks_total} Checks
                </span>
                <span className="inline-flex items-center gap-1 text-emerald-200">
                  Öffnen
                  <ArrowRight className="transition group-hover:translate-x-0.5" size={14} />
                </span>
              </div>
            </Link>
          ))}
        </div>
      )}
      {query.error instanceof Error ? (
        <div className="mt-4 rounded border border-rose-300/30 bg-rose-300/10 p-3 text-sm text-rose-100">
          {query.error.message}
        </div>
      ) : null}
    </section>
  );
}

function Metric({
  label,
  value,
  tone = "neutral"
}: {
  label: string;
  value: string;
  tone?: "good" | "neutral" | "bad";
}) {
  const color = tone === "good" ? "text-emerald-300" : tone === "bad" ? "text-rose-300" : "text-white";
  return (
    <div className="rounded border border-[#2d333d] bg-[#171a20] px-3 py-2">
      <div className="text-[11px] uppercase text-[#a0a7b4]">{label}</div>
      <div className={`mt-1 font-semibold ${color}`}>{value}</div>
    </div>
  );
}

function formatPercent(value?: number | null) {
  if (value === undefined || value === null || Number.isNaN(value)) return "-";
  return `${value >= 0 ? "+" : ""}${value.toFixed(1)}%`;
}
