"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { RefreshCw } from "lucide-react";
import { KpiCard } from "@/components/ui/kpi-card";
import { BuyStrengthPanel } from "@/features/portfolio/buy-strength-panel";
import { PortfolioCurvePanel } from "@/features/portfolio/portfolio-curve-panel";
import { PortfolioManagementPanel } from "@/features/portfolio/portfolio-management-panel";
import { PositionTable } from "@/features/portfolio/position-table";
import { api } from "@/lib/api/client";

export default function PortfolioPage() {
  const { data } = useQuery({ queryKey: ["portfolio-snapshot"], queryFn: api.portfolioSnapshot });
  const afterHoursMutation = useMutation({ mutationFn: api.portfolioAfterHours });
  const afterHoursByTicker = new Map(
    afterHoursMutation.data?.positions.map((position) => [position.ticker, position]) ?? []
  );

  return (
    <div className="space-y-4">
      <div className="grid gap-2.5 sm:grid-cols-2 xl:grid-cols-4 2xl:grid-cols-7">
        {data?.kpis.map((item) => <KpiCard key={item.label} item={item} />)}
      </div>
      <section className="rounded-[14px] border border-[#e3e8ef] bg-white p-4 shadow-[0_5px_18px_rgba(15,23,42,0.05)]">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <h2 className="text-base font-semibold">After Market</h2>
            <p className="mt-0.5 text-xs leading-5 text-[#687386]">
              Holt gesammelt die aktuellen Yahoo-Finance-After-Hours-Kurse deiner offenen Positionen.
              Die Werte werden nur per Button aktualisiert.
            </p>
          </div>
          <button
            className="inline-flex h-9 items-center justify-center gap-2 rounded-[10px] border border-[#b7ddd6] bg-[#e8f4f2] px-3 text-sm font-semibold text-[#0f766e] transition hover:border-[#0f766e] disabled:cursor-not-allowed disabled:opacity-60"
            disabled={afterHoursMutation.isPending || !data?.positions.length}
            type="button"
            onClick={() => afterHoursMutation.mutate()}
          >
            <RefreshCw className={afterHoursMutation.isPending ? "animate-spin" : ""} size={16} />
            {afterHoursMutation.isPending ? "lädt" : "After Market aktualisieren"}
          </button>
        </div>
        {afterHoursMutation.data ? (
          <div className="mt-3 grid gap-2 md:grid-cols-3">
            <AfterHoursMetric
              label="Depotbewegung After Market"
              value={`${signedNumber(afterHoursMutation.data.total_after_hours_change)} ${afterHoursMutation.data.currency}`}
              tone={afterHoursMutation.data.total_after_hours_change >= 0 ? "good" : "bad"}
            />
            <AfterHoursMetric
              label="Depotbewegung %"
              value={`${signedNumber(afterHoursMutation.data.total_after_hours_change_pct, 2)}%`}
              tone={afterHoursMutation.data.total_after_hours_change_pct >= 0 ? "good" : "bad"}
            />
            <AfterHoursMetric
              label="Aktualisiert"
              value={new Date(afterHoursMutation.data.as_of).toLocaleString("de-DE")}
              tone="neutral"
              detail={`${afterHoursMutation.data.available_count}/${afterHoursMutation.data.positions_count} Positionen mit After-Hours-Kurs`}
            />
          </div>
        ) : null}
        {afterHoursMutation.error ? (
          <div className="mt-3 rounded-[10px] border border-[#f0b9b5] bg-[#fff0ef] p-3 text-sm text-[#c2413b]">
            {afterHoursMutation.error instanceof Error
              ? afterHoursMutation.error.message
              : "After-Market-Kurse konnten nicht geladen werden."}
          </div>
        ) : null}
      </section>
      {data ? (
        <>
          <PortfolioCurvePanel />
          <BuyStrengthPanel />
          <PositionTable afterHoursByTicker={afterHoursByTicker} positions={data.positions} />
          <PortfolioManagementPanel positions={data.positions} />
        </>
      ) : (
        <div className="rounded border border-[#2d333d] p-4">Portfolio lädt...</div>
      )}
    </div>
  );
}

function AfterHoursMetric({
  label,
  value,
  tone,
  detail
}: {
  label: string;
  value: string;
  tone: "good" | "bad" | "neutral";
  detail?: string;
}) {
  const toneClass =
    tone === "good" ? "text-[#138a57]" : tone === "bad" ? "text-[#c2413b]" : "text-[#172033]";
  return (
    <div className="rounded-[10px] border border-[#e3e8ef] bg-[#f9fbfd] px-3 py-2.5">
      <div className="text-[10px] font-semibold uppercase tracking-[0.08em] text-[#687386]">{label}</div>
      <div className={`mt-1 text-lg font-semibold tabular-nums ${toneClass}`}>{value}</div>
      {detail ? <div className="mt-0.5 text-[11px] leading-4 text-[#687386]">{detail}</div> : null}
    </div>
  );
}

function signedNumber(value: number, digits = 2) {
  return `${value >= 0 ? "+" : ""}${value.toLocaleString("de-DE", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits
  })}`;
}
