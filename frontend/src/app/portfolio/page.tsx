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
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-semibold">Portfolio</h1>
      </div>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-6">
        {data?.kpis.map((item) => <KpiCard key={item.label} item={item} />)}
      </div>
      <section className="rounded border border-[#2d333d] bg-[#171a20] p-5">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <h2 className="text-base font-semibold">After Market</h2>
            <p className="mt-1 text-sm leading-5 text-[#a0a7b4]">
              Holt gesammelt die aktuellen Yahoo-Finance-After-Hours-Kurse deiner offenen Positionen.
              Die Werte werden nur per Button aktualisiert.
            </p>
          </div>
          <button
            className="inline-flex items-center justify-center gap-2 rounded-full border border-emerald-300/40 bg-emerald-300/10 px-4 py-2 text-sm text-emerald-100 transition hover:border-emerald-200 disabled:cursor-not-allowed disabled:opacity-60"
            disabled={afterHoursMutation.isPending || !data?.positions.length}
            type="button"
            onClick={() => afterHoursMutation.mutate()}
          >
            <RefreshCw className={afterHoursMutation.isPending ? "animate-spin" : ""} size={16} />
            {afterHoursMutation.isPending ? "lädt" : "After Market aktualisieren"}
          </button>
        </div>
        {afterHoursMutation.data ? (
          <div className="mt-4 grid gap-3 md:grid-cols-3">
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
          <div className="mt-3 rounded border border-rose-300/30 bg-rose-300/10 p-3 text-sm text-rose-100">
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
    tone === "good" ? "text-emerald-300" : tone === "bad" ? "text-rose-300" : "text-[#d8dde6]";
  return (
    <div className="rounded border border-[#2d333d] bg-[#111419] p-4">
      <div className="text-xs uppercase tracking-wide text-[#a0a7b4]">{label}</div>
      <div className={`mt-2 text-xl font-semibold tabular-nums ${toneClass}`}>{value}</div>
      {detail ? <div className="mt-1 text-xs text-[#a0a7b4]">{detail}</div> : null}
    </div>
  );
}

function signedNumber(value: number, digits = 2) {
  return `${value >= 0 ? "+" : ""}${value.toLocaleString("de-DE", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits
  })}`;
}
