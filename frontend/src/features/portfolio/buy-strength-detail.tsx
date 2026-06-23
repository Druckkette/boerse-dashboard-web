"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, CalendarDays, LineChart, ShieldAlert, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { StatusChip } from "@/components/ui/status-chip";
import { api } from "@/lib/api/client";
import type { BuyStrengthAssessment, BuyStrengthCheck } from "@/lib/types/api";
import { BUY_STRENGTH_WEEK_OPTIONS, buyStrengthWindowLabel, normalizeBuyStrengthWeeks } from "./buy-strength-window";

const statusTone: Record<BuyStrengthAssessment["status"], "good" | "neutral" | "warning" | "bad"> = {
  stark: "good",
  ok: "neutral",
  watch: "warning",
  risk: "bad",
  missing: "neutral"
};

export function BuyStrengthDetail({ ticker, initialWeeks = 3 }: { ticker: string; initialWeeks?: number }) {
  const [weeks, setWeeks] = useState(() => normalizeBuyStrengthWeeks(initialWeeks));
  const query = useQuery({
    queryKey: ["portfolio-buy-strength-detail", ticker, weeks],
    queryFn: () => api.portfolioBuyStrengthDetail(ticker, { weeks }),
    staleTime: 60_000
  });
  const data = query.data;
  const windowLabel = buyStrengthWindowLabel(weeks);

  if (query.isLoading) {
    return (
      <div className="rounded border border-[#2d333d] bg-[#171a20] p-5">
        Bewertung für {windowLabel} lädt...
      </div>
    );
  }

  if (!data) {
    return (
      <div className="rounded border border-rose-300/30 bg-rose-300/10 p-5 text-rose-100">
        {query.error instanceof Error ? query.error.message : "Bewertung konnte nicht geladen werden."}
      </div>
    );
  }

  const activeWarnings = data.warnings.filter((check) => !check.passed).length;
  const passedChecks = data.checks.filter((check) => check.passed).length;

  return (
    <div className="space-y-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <Link className="inline-flex items-center gap-2 text-sm text-[#a0a7b4] hover:text-white" href={`/portfolio/buy-strength?weeks=${weeks}`}>
          <ArrowLeft size={16} />
          Zurück zur Stärke-Übersicht
        </Link>
        <div className="flex flex-wrap items-end gap-2">
          <label className="text-sm">
            <span className="mb-1 block text-xs uppercase text-[#a0a7b4]">Zeitraum</span>
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
          <StatusChip tone={statusTone[data.status]}>{data.status_label}</StatusChip>
          <StatusChip tone={data.data_status === "fresh" ? "good" : data.data_status === "stale" ? "warning" : "neutral"}>
            Kurse {data.data_status}
          </StatusChip>
        </div>
      </div>

      <section className="rounded border border-[#2d333d] bg-[#171a20] p-5">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <div className="text-sm text-[#a0a7b4]">Stärke nach Kauf Bewertung</div>
            <h1 className="mt-1 text-2xl font-semibold">{data.ticker}</h1>
            <p className="mt-2 max-w-3xl text-sm text-[#c7ccd6]">
              {data.message} Auswertungsfenster: {windowLabel} ab Kaufdatum.
            </p>
          </div>
          <div className="grid min-w-[280px] grid-cols-2 gap-2">
            <Metric label="Kaufdatum" value={data.buy_date ?? "-"} />
            <Metric label="Alter" value={data.age_days !== null && data.age_days !== undefined ? `${data.age_days} Tage` : "-"} />
            <Metric label="Fenster" value={`${data.window_days} Tage`} />
            <Metric label="P&L" value={formatPercent(data.pnl_pct)} tone={(data.pnl_pct ?? 0) >= 0 ? "good" : "bad"} />
            <Metric label="Stand Kurse" value={data.latest_price_date ?? "-"} />
          </div>
        </div>
      </section>

      <div className="grid gap-4 lg:grid-cols-4">
        <InfoTile icon={<ShieldCheck size={18} />} label="Positive Checks" value={`${passedChecks}/${data.checks.length}`} tone="good" />
        <InfoTile icon={<ShieldAlert size={18} />} label="Aktive Warnzeichen" value={`${activeWarnings}/${data.warnings.length}`} tone={activeWarnings ? "bad" : "good"} />
        <InfoTile icon={<LineChart size={18} />} label="Letzter Schluss" value={money(data.latest_close)} />
        <InfoTile icon={<CalendarDays size={18} />} label="Kauftag-Tief" value={money(data.buy_day_low)} />
      </div>

      <div className="grid gap-5 xl:grid-cols-2">
        <CheckSection
          title="Positive Zeichen"
          subtitle="Diese Signale sollen bestätigen, dass der Kauf zügig getragen wird."
          checks={data.checks}
          empty="Keine positiven Checks verfügbar."
        />
        <CheckSection
          title="Warnzeichen nach Kauf"
          subtitle="Aktive Warnzeichen sind rot markiert und sollten zuerst geprüft werden."
          checks={data.warnings}
          empty="Keine Warnzeichen verfügbar."
        />
      </div>
    </div>
  );
}

function CheckSection({
  title,
  subtitle,
  checks,
  empty
}: {
  title: string;
  subtitle: string;
  checks: BuyStrengthCheck[];
  empty: string;
}) {
  return (
    <section className="rounded border border-[#2d333d] bg-[#171a20] p-5">
      <div className="mb-4">
        <h2 className="text-base font-semibold">{title}</h2>
        <p className="mt-1 text-sm text-[#a0a7b4]">{subtitle}</p>
      </div>
      {checks.length === 0 ? (
        <div className="rounded border border-[#2d333d] bg-[#111419] p-4 text-sm text-[#a0a7b4]">{empty}</div>
      ) : (
        <div className="space-y-3">
          {checks.map((check) => (
            <div key={check.key} className="rounded border border-[#2d333d] bg-[#111419] p-4">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <h3 className="text-sm font-semibold">{check.label}</h3>
                  <p className="mt-1 text-sm text-[#a0a7b4]">{check.detail}</p>
                </div>
                <StatusChip tone={check.tone}>{check.category === "warning" ? (check.passed ? "OK" : "aktiv") : check.passed ? "gut" : "fehlt"}</StatusChip>
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

function InfoTile({
  icon,
  label,
  value,
  tone = "neutral"
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  tone?: "good" | "neutral" | "bad";
}) {
  const color = tone === "good" ? "text-emerald-300" : tone === "bad" ? "text-rose-300" : "text-white";
  return (
    <div className="rounded border border-[#2d333d] bg-[#171a20] p-4">
      <div className="mb-3 text-[#a0a7b4]">{icon}</div>
      <div className="text-xs uppercase text-[#a0a7b4]">{label}</div>
      <div className={`mt-1 text-lg font-semibold ${color}`}>{value}</div>
    </div>
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
    <div className="rounded border border-[#2d333d] bg-[#111419] px-3 py-2">
      <div className="text-[11px] uppercase text-[#a0a7b4]">{label}</div>
      <div className={`mt-1 text-sm font-semibold ${color}`}>{value}</div>
    </div>
  );
}

function formatPercent(value?: number | null) {
  if (value === undefined || value === null || Number.isNaN(value)) return "-";
  return `${value >= 0 ? "+" : ""}${value.toFixed(1)}%`;
}

function money(value?: number | null) {
  if (value === undefined || value === null || Number.isNaN(value)) return "-";
  return `$${value.toLocaleString("de-DE", { maximumFractionDigits: 2 })}`;
}
