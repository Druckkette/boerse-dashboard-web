"use client";

import { AlertTriangle, CalendarClock, CheckCircle2, CircleDot, Gauge, TrendingUp } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { StatusChip } from "@/components/ui/status-chip";
import { api } from "@/lib/api/client";
import type { StockAssessment, StockAssessmentCheck, StockAssessmentSignal, Tone } from "@/lib/types/api";

export function StockAssessmentPanel({ ticker }: { ticker: string }) {
  const clean = ticker.toUpperCase();
  const query = useQuery({
    queryKey: ["stock-assessment", clean],
    queryFn: () => api.stockAssessment(clean),
    staleTime: 60_000
  });

  if (query.isLoading) {
    return (
      <section className="rounded border border-[#2d333d] bg-[#171a20] p-5">
        <div className="h-5 w-44 animate-pulse rounded bg-[#242a33]" />
        <div className="mt-5 grid gap-3 md:grid-cols-4">
          {[0, 1, 2, 3].map((item) => (
            <div key={item} className="h-28 animate-pulse rounded border border-[#242a33] bg-[#111419]" />
          ))}
        </div>
      </section>
    );
  }

  if (query.isError || !query.data) {
    return (
      <section className="rounded border border-rose-300/25 bg-rose-950/20 p-5 text-sm text-rose-100">
        Aktienbewertung konnte nicht geladen werden.
      </section>
    );
  }

  return <AssessmentContent assessment={query.data} />;
}

function AssessmentContent({ assessment }: { assessment: StockAssessment }) {
  const checksByCategory = groupChecks(assessment.checks);
  const signalsByCategory = groupSignals(assessment.chart_signals);
  const hasData = assessment.source === "database";

  return (
    <section className="space-y-4">
      <div className="rounded border border-[#2d333d] bg-[#171a20] p-5">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-xl font-semibold">Aktienbewertung</h2>
              <StatusChip tone={assessment.verdict_tone}>{assessment.verdict_label}</StatusChip>
              <StatusChip tone={hasData ? "good" : "warning"}>
                {hasData ? "Price Cache" : "Daten fehlen"}
              </StatusChip>
              {assessment.earnings && (
                <StatusChip tone={assessment.earnings.tone}>Earnings {assessment.earnings.trading_days ?? "-"}T</StatusChip>
              )}
            </div>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-[#a0a7b4]">{assessment.verdict_text}</p>
            <p className="mt-1 text-xs text-[#7f8794]">
              Stand {assessment.as_of} · {assessment.message}
            </p>
          </div>
          <div className="min-w-36 rounded border border-[#242a33] bg-[#111419] p-4 text-center">
            <div className="text-xs uppercase text-[#a0a7b4]">Gesamtscore</div>
            <div className="mt-1 text-4xl font-semibold tabular-nums">{assessment.scores.overall}</div>
            <ScoreBar value={assessment.scores.overall} tone={assessment.verdict_tone} />
          </div>
        </div>
      </div>

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <ScoreCard label="Technisch" value={assessment.scores.technical} detail="Preis, Volumen, RS und CMF" />
        <ScoreCard
          label="Fundamental"
          value={assessment.scores.fundamental}
          detail={assessment.fundamentals_available ? assessment.fundamentals?.source ?? "Fundamental-Cache" : "Noch neutral, Datenquelle offen"}
          tone={assessment.fundamentals_available ? toneForScore(assessment.scores.fundamental) : "neutral"}
        />
        <ScoreCard label="Trend" value={assessment.scores.moving_averages} detail="10/21/50/200 + Ordnung" />
        <ScoreCard label="Chart" value={assessment.scores.chart_behavior} detail="Positiv-/Negativsignale" />
      </div>

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <Metric label="Letzter Schluss" value={money(assessment.metrics.last_close)} detail={pct(assessment.metrics.change_pct)} />
        <Metric label="ATR" value={pct(assessment.metrics.atr_pct)} detail="21 Tage" />
        <Metric label="Dollar-Volumen" value={mio(assessment.metrics.dollar_volume_mio)} detail="20 Tage Ø" />
        <Metric label="RS-Rating" value={numberOrDash(assessment.metrics.rs_rating)} detail={pct(assessment.metrics.rs_percentile)} />
        <Metric label="Beta" value={numberOrDash(assessment.metrics.beta)} detail="Fundamental-Cache" />
        <Metric
          label="Inst. gehalten"
          value={pctPlain(assessment.metrics.institutional_ownership_pct)}
          detail={assessment.fundamentals?.institutional_holders ? `${assessment.fundamentals.institutional_holders} Halter` : "13F/Fundamentals"}
        />
        <Metric
          label="Earnings"
          value={assessment.earnings?.trading_days !== undefined && assessment.earnings?.trading_days !== null ? `${assessment.earnings.trading_days} HT` : "-"}
          detail={assessment.earnings?.next_earnings_date ?? "kein Termin"}
        />
      </div>

      {assessment.earnings && (
        <div className={earningsBoxClass(assessment.earnings.tone)}>
          <CalendarClock className="mt-0.5 size-4 shrink-0" />
          <span>{assessment.earnings.message}</span>
        </div>
      )}

      <div className="grid gap-4 xl:grid-cols-2">
        <ReasonList title="Treiber" tone="good" items={assessment.drivers} empty="Noch keine starken Treiber im Cache." />
        <ReasonList title="Warnungen" tone="warning" items={assessment.warnings} empty="Keine harten Warnungen." />
      </div>

      <div className="grid gap-4 xl:grid-cols-[1.15fr_0.85fr]">
        <div className="rounded border border-[#2d333d] bg-[#171a20] p-5">
          <div className="mb-4 flex items-center justify-between gap-3">
            <div>
              <h3 className="text-base font-semibold">Regel-Checkliste</h3>
              <p className="mt-1 text-sm text-[#a0a7b4]">Aus den technischen Streamlit-Regeln extrahiert.</p>
            </div>
            <StatusChip tone="neutral">{assessment.checks.length} Regeln</StatusChip>
          </div>
          <div className="grid gap-3 lg:grid-cols-2">
            <CheckGroup title="Technisch" checks={checksByCategory.technical} />
            <CheckGroup title="Trend" checks={checksByCategory.trend} />
            <CheckGroup title="Risiko" checks={checksByCategory.risk} />
            <CheckGroup title="Fundamental" checks={checksByCategory.fundamental} />
          </div>
        </div>

        <div className="rounded border border-[#2d333d] bg-[#171a20] p-5">
          <div className="mb-4 flex items-center justify-between gap-3">
            <div>
              <h3 className="text-base font-semibold">Chartverhalten</h3>
              <p className="mt-1 text-sm text-[#a0a7b4]">Positive, negative und neutrale Signale.</p>
            </div>
            <StatusChip tone="neutral">{assessment.chart_signals.length} Signale</StatusChip>
          </div>
          <SignalGroup title="Positiv" tone="good" signals={signalsByCategory.positive} />
          <SignalGroup title="Negativ" tone="bad" signals={signalsByCategory.negative} />
          <SignalGroup title="Neutral" tone="neutral" signals={signalsByCategory.neutral} />
        </div>
      </div>
    </section>
  );
}

function ScoreCard({
  label,
  value,
  detail,
  tone = toneForScore(value)
}: {
  label: string;
  value: number;
  detail: string;
  tone?: Tone;
}) {
  return (
    <div className="rounded border border-[#242a33] bg-[#171a20] p-4">
      <div className="mb-3 flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-sm font-medium">
          <Gauge className="size-4 text-[#8ea4c8]" />
          {label}
        </div>
        <StatusChip tone={tone}>{toneLabel(tone)}</StatusChip>
      </div>
      <div className="text-3xl font-semibold tabular-nums">{Math.round(value)}</div>
      <ScoreBar value={value} tone={tone} />
      <div className="mt-2 text-xs text-[#a0a7b4]">{detail}</div>
    </div>
  );
}

function Metric({ label, value, detail }: { label: string; value: string; detail: string }) {
  return (
    <div className="rounded border border-[#242a33] bg-[#111419] p-4">
      <div className="mb-2 flex items-center gap-2 text-xs uppercase text-[#a0a7b4]">
        <TrendingUp className="size-3.5" />
        {label}
      </div>
      <div className="text-xl font-semibold tabular-nums">{value}</div>
      <div className="mt-1 text-xs text-[#7f8794]">{detail}</div>
    </div>
  );
}

function ReasonList({
  title,
  tone,
  items,
  empty
}: {
  title: string;
  tone: Tone;
  items: string[];
  empty: string;
}) {
  return (
    <div className="rounded border border-[#2d333d] bg-[#171a20] p-5">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-base font-semibold">{title}</h3>
        <StatusChip tone={tone}>{items.length}</StatusChip>
      </div>
      {items.length === 0 ? (
        <div className="text-sm text-[#a0a7b4]">{empty}</div>
      ) : (
        <div className="space-y-2">
          {items.map((item) => (
            <div key={item} className="flex gap-2 rounded border border-[#242a33] bg-[#111419] p-3 text-sm">
              {tone === "good" ? (
                <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-emerald-300" />
              ) : (
                <AlertTriangle className="mt-0.5 size-4 shrink-0 text-amber-300" />
              )}
              <span className="leading-5 text-[#c9d0da]">{item}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function CheckGroup({ title, checks }: { title: string; checks: StockAssessmentCheck[] }) {
  return (
    <div className="rounded border border-[#242a33] bg-[#111419] p-4">
      <div className="mb-3 text-sm font-medium">{title}</div>
      {checks.length === 0 ? (
        <div className="text-sm text-[#7f8794]">Noch keine Regeln.</div>
      ) : (
        <div className="space-y-2">
          {checks.map((check) => (
            <div key={check.label} className="flex gap-2 text-sm">
              {check.passed ? (
                <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-emerald-300" />
              ) : (
                <CircleDot className="mt-0.5 size-4 shrink-0 text-[#7f8794]" />
              )}
              <div>
                <div className={check.passed ? "text-[#dbe4ef]" : "text-[#a0a7b4]"}>{check.label}</div>
                <div className="text-xs leading-5 text-[#7f8794]">{check.detail}</div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function SignalGroup({ title, tone, signals }: { title: string; tone: Tone; signals: StockAssessmentSignal[] }) {
  return (
    <div className="mb-4 last:mb-0">
      <div className="mb-2 flex items-center justify-between text-sm font-medium">
        <span>{title}</span>
        <StatusChip tone={tone}>{signals.length}</StatusChip>
      </div>
      {signals.length === 0 ? (
        <div className="rounded border border-[#242a33] bg-[#111419] p-3 text-sm text-[#7f8794]">Keine Signale.</div>
      ) : (
        <div className="space-y-2">
          {signals.map((signal) => (
            <div key={`${signal.category}-${signal.label}`} className="rounded border border-[#242a33] bg-[#111419] p-3">
              <div className="text-sm text-[#dbe4ef]">{signal.label}</div>
              {signal.detail && <div className="mt-1 text-xs leading-5 text-[#7f8794]">{signal.detail}</div>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function ScoreBar({ value, tone }: { value: number; tone: Tone }) {
  const width = Math.max(0, Math.min(100, value));
  return (
    <div className="mt-3 h-2 overflow-hidden rounded bg-[#242a33]">
      <div className={barClass(tone)} style={{ width: `${width}%` }} />
    </div>
  );
}

function groupChecks(checks: StockAssessmentCheck[]) {
  return {
    technical: checks.filter((check) => check.category === "technical"),
    trend: checks.filter((check) => check.category === "trend"),
    risk: checks.filter((check) => check.category === "risk"),
    fundamental: checks.filter((check) => check.category === "fundamental")
  };
}

function groupSignals(signals: StockAssessmentSignal[]) {
  return {
    positive: signals.filter((signal) => signal.category === "positive"),
    negative: signals.filter((signal) => signal.category === "negative"),
    neutral: signals.filter((signal) => signal.category === "neutral")
  };
}

function toneForScore(value: number): Tone {
  if (value >= 75) return "good";
  if (value >= 55) return "warning";
  if (value >= 45) return "neutral";
  return "bad";
}

function toneLabel(tone: Tone) {
  return tone === "good" ? "stark" : tone === "warning" ? "watch" : tone === "bad" ? "schwach" : "neutral";
}

function barClass(tone: Tone) {
  if (tone === "good") return "h-full rounded bg-emerald-400";
  if (tone === "warning") return "h-full rounded bg-amber-300";
  if (tone === "bad") return "h-full rounded bg-rose-400";
  return "h-full rounded bg-sky-300";
}

function money(value?: number | null) {
  if (typeof value !== "number") return "-";
  return `$${value.toFixed(2)}`;
}

function pct(value?: number | null) {
  if (typeof value !== "number" || Number.isNaN(value)) return "-";
  return `${value >= 0 ? "+" : ""}${value.toFixed(1)}%`;
}

function pctPlain(value?: number | null) {
  if (typeof value !== "number" || Number.isNaN(value)) return "-";
  return `${value.toFixed(1)}%`;
}

function mio(value?: number | null) {
  if (typeof value !== "number" || Number.isNaN(value)) return "-";
  return `$${value.toFixed(0)} Mio.`;
}

function numberOrDash(value?: number | null) {
  if (typeof value !== "number" || Number.isNaN(value)) return "-";
  return `${Number.isInteger(value) ? value : value.toFixed(2)}`;
}

function earningsBoxClass(tone: Tone) {
  if (tone === "good") {
    return "flex gap-2 rounded border border-emerald-300/20 bg-emerald-950/20 p-3 text-sm text-emerald-100";
  }
  if (tone === "bad") {
    return "flex gap-2 rounded border border-rose-300/25 bg-rose-950/20 p-3 text-sm text-rose-100";
  }
  return "flex gap-2 rounded border border-amber-300/25 bg-amber-950/20 p-3 text-sm text-amber-100";
}
