"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowRight, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { StatusChip } from "@/components/ui/status-chip";
import { api } from "@/lib/api/client";
import type { BuyStrengthSummaryItem } from "@/lib/types/api";
import { BUY_STRENGTH_WEEK_OPTIONS, buyStrengthWindowLabel, normalizeBuyStrengthWeeks } from "./buy-strength-window";

const statusTone: Record<BuyStrengthSummaryItem["status"], "good" | "neutral" | "warning" | "bad"> = {
  stark: "good",
  ok: "neutral",
  watch: "warning",
  risk: "bad",
  missing: "neutral"
};

export function BuyStrengthPanel({ initialWeeks = 3 }: { initialWeeks?: number }) {
  const [weeks, setWeeks] = useState(() => normalizeBuyStrengthWeeks(initialWeeks));
  const query = useQuery({
    queryKey: ["portfolio-buy-strength", weeks],
    queryFn: () => api.portfolioBuyStrength({ weeks }),
    staleTime: 60_000
  });
  const items = query.data?.items ?? [];
  const windowLabel = buyStrengthWindowLabel(weeks);

  return (
    <section className="rounded-[14px] border border-[#e3e8ef] bg-white p-4 shadow-[0_5px_18px_rgba(15,23,42,0.05)]">
      <div className="mb-3 flex flex-col gap-2.5 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-base font-semibold text-[#172033]">Stärke nach Kauf</h2>
          <p className="mt-0.5 text-xs leading-5 text-[#687386]">
            Frische Käufe innerhalb von {windowLabel} ab Kaufdatum werden aus manueller Pflege, CSV-Import oder Trade-Republic-Import erkannt.
          </p>
        </div>
        <div className="flex flex-wrap items-end gap-2">
          <label className="text-sm">
            <span className="mb-1 block text-[10px] font-semibold uppercase tracking-[0.08em] text-[#687386]">Zeitraum</span>
            <select
              className="input-dark h-9 min-w-[8rem]"
              value={weeks}
              onChange={(event) => setWeeks(normalizeBuyStrengthWeeks(event.target.value))}
            >
              {BUY_STRENGTH_WEEK_OPTIONS.map((option) => (
                <option key={option} value={option}>
                  {buyStrengthWindowLabel(option)}
                </option>
              ))}
            </select>
          </label>
          <StatusChip tone={items.length ? "warning" : "neutral"}>
            {query.isLoading ? "lädt" : `${items.length} frisch`}
          </StatusChip>
        </div>
      </div>

      {items.length === 0 ? (
        <div className="rounded-[10px] border border-dashed border-[#cbd5e1] bg-[#f9fbfd] px-3 py-2.5 text-sm text-[#687386]">
          Keine frischen Käufe im Depot. Manuell erfasste Positionen erscheinen hier, sobald ein Kaufdatum innerhalb der letzten {windowLabel} gespeichert ist.
        </div>
      ) : (
        <div className="grid gap-2.5 xl:grid-cols-3">
          {items.map((item) => (
            <Link
              key={item.ticker}
              className="group rounded-[12px] border border-[#e3e8ef] bg-[#fbfcfe] p-3.5 transition hover:-translate-y-0.5 hover:border-[#9ccfc6] hover:bg-white hover:shadow-[0_6px_18px_rgba(15,23,42,0.06)]"
              href={`/portfolio/buy-strength/${item.ticker}?weeks=${weeks}`}
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="text-base font-semibold text-[#172033]">{item.ticker}</div>
                  <div className="text-xs text-[#687386]">{item.name || item.buy_date}</div>
                </div>
                <StatusChip tone={statusTone[item.status]}>{item.status_label}</StatusChip>
              </div>
              <div className="mt-3 grid grid-cols-2 gap-1.5 text-sm">
                <Metric label="Kaufdatum" value={formatDate(item.buy_date)} />
                <Metric label="Alter" value={`${item.age_days} Tage`} />
                <Metric label="Fenster" value={`${item.window_days ?? query.data?.window_days ?? weeks * 7} Tage`} />
                <Metric label="Stand Kurse" value={formatDate(item.latest_price_date)} tone={item.data_status === "stale" ? "bad" : "neutral"} />
                <Metric label="P&L" value={formatPercent(item.pnl_pct)} tone={(item.pnl_pct ?? 0) >= 0 ? "good" : "bad"} />
                <Metric label="Warnungen" value={`${item.warnings_active}/${item.warnings_total}`} tone={item.warnings_active ? "bad" : "good"} />
              </div>
              <div className="mt-3 flex items-center justify-between gap-3 text-xs text-[#687386]">
                <span className="inline-flex items-center gap-1">
                  <ShieldCheck size={14} />
                  {item.checks_passed}/{item.checks_total} Checks
                </span>
                <span className="inline-flex items-center gap-1 font-semibold text-[#0f766e]">
                  Öffnen
                  <ArrowRight className="transition group-hover:translate-x-0.5" size={14} />
                </span>
              </div>
            </Link>
          ))}
        </div>
      )}
      {query.error instanceof Error ? (
        <div className="mt-3 rounded-[10px] border border-[#f0b9b5] bg-[#fff0ef] p-3 text-sm text-[#c2413b]">
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
  const color = tone === "good" ? "text-[#138a57]" : tone === "bad" ? "text-[#c2413b]" : "text-[#172033]";
  return (
    <div className="rounded-[9px] border border-[#e3e8ef] bg-white px-2.5 py-2">
      <div className="text-[10px] font-semibold uppercase tracking-[0.05em] text-[#687386]">{label}</div>
      <div className={`mt-0.5 text-sm font-semibold ${color}`}>{value}</div>
    </div>
  );
}

function formatPercent(value?: number | null) {
  if (value === undefined || value === null || Number.isNaN(value)) return "-";
  return `${value >= 0 ? "+" : ""}${value.toFixed(1)}%`;
}

function formatDate(value?: string | null) {
  if (!value) return "-";
  const parsed = new Date(`${value}T00:00:00`);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleDateString("de-DE", { day: "2-digit", month: "2-digit", year: "2-digit" });
}
