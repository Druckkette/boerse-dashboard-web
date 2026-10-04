"use client";

import { AlertTriangle, CalendarClock, CheckCircle2, Gauge, TrendingUp, XCircle } from "lucide-react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { StatusChip } from "@/components/ui/status-chip";
import { assessmentCriterionLabel } from "./assessment-criteria";
import { AssessmentCriterionNote } from "./assessment-criterion-note";
import { api } from "@/lib/api/client";
import type { AssessmentV2Detail, StockAssessment, StockAssessmentCheck, StockAssessmentSignal, Tone } from "@/lib/types/api";

export function StockAssessmentPanel({ ticker, mode = "all" }: { ticker: string; mode?: "all" | "overview" | "technical" }) {
  const clean = ticker.toUpperCase();
  const query = useQuery({
    queryKey: ["stock-assessment", clean],
    queryFn: () => api.stockAssessment(clean),
    staleTime: 60_000
  });

  if (query.isLoading) {
    return (
      <section className="rounded-[24px] border border-[#e3e8ef] bg-white p-5 shadow-[0_10px_28px_rgba(15,23,42,0.06)]">
        <div className="h-5 w-44 animate-pulse rounded-full bg-[#e3e8ef]" />
        <div className="mt-5 grid gap-3 md:grid-cols-4">
          {[0, 1, 2, 3].map((item) => (
            <div key={item} className="h-28 animate-pulse rounded-[20px] border border-[#e3e8ef] bg-[#f9fbfd]" />
          ))}
        </div>
      </section>
    );
  }

  if (query.isError || !query.data) {
    return (
      <section className="rounded-[24px] border border-[#f0b9b5] bg-[#fff0ef] p-5 text-sm font-medium text-[#c2413b]">
        Aktienbewertung konnte nicht geladen werden.
      </section>
    );
  }

  return <AssessmentContent assessment={query.data} mode={mode} />;
}

function AssessmentContent({ assessment, mode }: { assessment: StockAssessment; mode: "all" | "overview" | "technical" }) {
  const checksByCategory = groupChecks(assessment.checks);
  const signalsByCategory = groupSignals(assessment.chart_signals);

  return (
    <section className="space-y-4">
      {mode !== "technical" ? <>
      {assessment.data_quality && Object.values(assessment.data_quality).some((item) => item.status !== "fresh") ? (
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900" role="status">
          <p className="font-semibold">Bewertung mit eingeschränkter Datenbasis</p>
          <ul className="mt-1 space-y-1">
            {Object.entries(assessment.data_quality).filter(([, item]) => item.status !== "fresh").map(([key, item]) => (
              <li key={key}>{item.label}: {item.status === "missing" ? "fehlt" : "nicht aktuell bestätigt"} · Stand {item.as_of ?? "unbekannt"}{item.expected ? ` · erwartet ${item.expected}` : ""}</li>
            ))}
          </ul>
        </div>
      ) : null}
      <div className="rounded-[14px] border border-[#e3e8ef] bg-white p-4 shadow-[0_5px_18px_rgba(15,23,42,0.05)]">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-lg font-semibold text-[#172033]">Aktienbewertung</h2>
              <StatusChip tone={assessment.verdict_tone}>{assessment.verdict_label}</StatusChip>
              {assessment.earnings && (
                <StatusChip tone={assessment.earnings.tone}>Earnings {assessment.earnings.trading_days ?? "-"}T</StatusChip>
              )}
            </div>
            <p className="mt-1.5 max-w-3xl text-sm leading-6 text-[#4b5565]">{assessment.verdict_text}</p>
            <p className="mt-1.5 text-[11px] font-medium text-[#687386]">
              Stand {assessment.as_of} · {friendlyAssessmentMessage(assessment.message)}
            </p>
          </div>
          <div className="flex min-w-[190px] items-center gap-3 rounded-[10px] border border-[#d7e8e4] bg-[#f3faf8] px-3 py-2.5">
            <div className="grid size-14 shrink-0 place-items-center rounded-full border-4 border-[#d5ece7] bg-white text-2xl font-semibold tabular-nums text-[#0f766e]">
              {assessment.scores.overall}
            </div>
            <div className="min-w-0 flex-1">
              <div className="text-[10px] font-semibold uppercase tracking-[0.1em] text-[#687386]">Gesamtscore</div>
              <ScoreBar value={assessment.scores.overall} tone={assessment.verdict_tone} />
            </div>
          </div>
        </div>
      </div>

      <div className="grid gap-2.5 md:grid-cols-2 xl:grid-cols-4">
        <ScoreCard label="Technical" value={assessment.scores.technical} detail="RS Leadership, Dynamics, Rating, Highs und Akkumulation" />
        <ScoreCard
          label="Fundamental"
          value={assessment.scores.fundamental}
          detail={assessment.fundamentals_available ? assessment.fundamentals?.source ?? "Fundamental-Cache" : "Noch neutral, Datenquelle offen"}
          tone={assessment.fundamentals_available ? toneForScore(assessment.scores.fundamental) : "neutral"}
        />
        <ScoreCard label="Moving Average" value={assessment.scores.moving_averages} detail="Position, Ordnung, Persistenz und Richtung" />
        <ScoreCard label="Chart" value={assessment.scores.chart_behavior} detail="Kurs-/Volumenverhalten, Verlustwochen und Wochen-Aufwärtstrend" />
      </div>

      <div className="grid gap-2.5 md:grid-cols-2 xl:grid-cols-5">
        <PriceMetric percent={assessment.metrics.change_pct} price={assessment.metrics.last_close} />
        <Metric label="ATR" value={pct(assessment.metrics.atr_pct)} detail={atrRegime(assessment.metrics.atr_pct)} />
        <Metric label="RS-Rating" value={numberOrDash(assessment.metrics.rs_rating)} detail="Bewertungszahl" />
        <Metric label="Beta" value={numberOrDash(assessment.metrics.beta)} detail={betaRegime(assessment.metrics.beta)} />
        {assessment.earnings && (
          <Metric
            label="Earnings"
            value={assessment.earnings.trading_days !== undefined && assessment.earnings.trading_days !== null ? `${assessment.earnings.trading_days} HT` : "-"}
            detail={assessment.earnings.next_earnings_date ?? "kein Termin"}
          />
        )}
      </div>

      {assessment.earnings && (
        <div className={earningsBoxClass(assessment.earnings.tone)}>
          <CalendarClock className="mt-0.5 size-4 shrink-0" />
          <span>{assessment.earnings.message}</span>
        </div>
      )}

      <div className="grid gap-3 xl:grid-cols-2">
        <ReasonList title="Treiber" tone="good" items={assessment.drivers} empty="Noch keine starken Treiber." />
        <ReasonList title="Warnungen" tone="warning" items={assessment.warnings} empty="Keine harten Warnungen." />
      </div>
      </> : null}

      <AssessmentV2Breakdown assessment={assessment} mode={mode} />

      {mode !== "overview" ?
      <div className="grid gap-3 xl:grid-cols-[1.15fr_0.85fr]">
        <div className="rounded-[14px] border border-[#e3e8ef] bg-white p-4 shadow-[0_5px_18px_rgba(15,23,42,0.05)]">
          <div className="mb-3 flex items-center justify-between gap-3">
            <div>
              <h3 className="text-base font-semibold text-[#172033]">Regel-Checkliste</h3>
              <p className="mt-0.5 text-xs text-[#687386]">Technische und fundamentale Kriterien im Überblick.</p>
            </div>
            <StatusChip tone="neutral">{assessment.checks.length} Regeln</StatusChip>
          </div>
          <div className="grid gap-3 lg:grid-cols-2">
            <CheckGroup title="Technisch" checks={checksByCategory.technical} />
            <CheckGroup title="Trend" checks={checksByCategory.trend} />
            <CheckGroup title="Überdehnung" checks={checksByCategory.risk} />
            {mode === "all" ? <CheckGroup title="Fundamental" checks={checksByCategory.fundamental} /> : null}
          </div>
        </div>

        <div className="rounded-[14px] border border-[#e3e8ef] bg-white p-4 shadow-[0_5px_18px_rgba(15,23,42,0.05)]">
          <div className="mb-3 flex items-center justify-between gap-3">
            <div>
              <h3 className="text-base font-semibold text-[#172033]">Chartverhalten</h3>
              <p className="mt-0.5 text-xs text-[#687386]">Positive, negative und neutrale Signale.</p>
            </div>
            <StatusChip tone="neutral">{assessment.chart_signals.length} Signale</StatusChip>
          </div>
          <SignalGroup title="Positiv" tone="good" signals={signalsByCategory.positive} />
          <SignalGroup title="Negativ" tone="bad" signals={signalsByCategory.negative} />
          <SignalGroup title="Neutral" tone="neutral" signals={signalsByCategory.neutral} />
        </div>
      </div>
      : null}
    </section>
  );
}

function AssessmentV2Breakdown({ assessment, mode }: { assessment: StockAssessment; mode: "all" | "overview" | "technical" }) {
  const groups = [
    { title: "Technical", detail: assessment.technical_v2 },
    { title: "Fundamental", detail: assessment.fundamental_v2 },
    { title: "Chart", detail: assessment.chart_v2 },
    { title: "Moving Average", detail: assessment.moving_average_v2 }
  ].filter((group) => mode !== "technical" || group.title !== "Fundamental");
  return (
    <div className="space-y-3">
      <div className="text-right"><Link href="/settings#assessment-weights" className="text-xs font-semibold text-[#0f766e]">Gewichtung in Settings bearbeiten →</Link></div>
      {assessment.overall_v2?.status === "limited" ? (
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
          Eingeschränkte Gesamtbewertung · verfügbare Gewichtung {Math.round((assessment.overall_v2.available_weight ?? 0) * 100)}%. Im Ranking wird sie nicht wie eine vollständige Bewertung behandelt.
        </div>
      ) : null}
      <div className="grid gap-3 xl:grid-cols-2">
        {groups.map((group) => <ComponentBreakdown key={group.title} title={group.title} detail={group.detail} />)}
      </div>
      <div className="grid gap-3 xl:grid-cols-2">
        <EligibilityCard eligibility={assessment.eligibility} />
        <SetupCard setup={assessment.setup} />
      </div>
    </div>
  );
}

function ComponentBreakdown({ title, detail }: { title: string; detail?: AssessmentV2Detail }) {
  const components = Object.entries(detail?.components ?? {});
  if (!detail || !components.length) return null;
  return (
    <div className="rounded-[14px] border border-[#e3e8ef] bg-white p-4 shadow-[0_5px_18px_rgba(15,23,42,0.045)]">
      <div className="mb-3 flex items-center justify-between gap-3">
        <h3 className="text-base font-semibold text-[#172033]">{title}</h3>
        <StatusChip tone={detail.status === "available" ? toneForScore(detail.score ?? 0) : "neutral"}>
          {typeof detail.score === "number" ? `${Math.round(detail.score)}/100` : statusLabel(detail.status)}
        </StatusChip>
      </div>
      <div className="space-y-1.5">
        {components.map(([key, component]) => (
          <div key={key} className="flex items-center justify-between gap-3 rounded-[9px] bg-[#f9fbfd] px-3 py-2 text-sm">
            <div>
              <div className="font-medium text-[#172033]">{assessmentCriterionLabel(key)}</div>
              <AssessmentCriterionNote criterion={key} />
              <div className="text-[11px] text-[#687386]">Basis {Math.round((component.base_weight ?? 0) * 1000) / 10}% · effektiv {Math.round((component.effective_weight ?? 0) * 1000) / 10}% · {statusLabel(component.status)}</div>
            </div>
            <span className="shrink-0 font-semibold tabular-nums text-[#172033]">{typeof component.score === "number" ? component.score.toFixed(1) : "–"}</span>
          </div>
        ))}
      </div>
      {title === "Fundamental" ? <K9Detail detail={detail} /> : null}
    </div>
  );
}

function K9Detail({ detail }: { detail: AssessmentV2Detail }) {
  const raw = detail.components?.k9_eps_sales_alignment?.raw as { matched_quarters?: Array<Record<string, unknown>>; research_trigger?: boolean } | undefined;
  const quarters = raw?.matched_quarters ?? [];
  if (!quarters.length) return null;
  return (
    <div className="mt-3 rounded-[9px] border border-[#e3e8ef] p-3 text-xs text-[#4b5565]">
      {quarters.map((quarter) => (
        <div key={String(quarter.period)} className="mb-1 last:mb-0">
          <strong>{String(quarter.period)}</strong> · EPS {signedPercent(quarter.eps_growth_yoy_pct)} · Sales {signedPercent(quarter.revenue_growth_yoy_pct)} · Divergenz {signedPp(quarter.divergence_pp)}
        </div>
      ))}
      {raw?.research_trigger ? <div className="mt-2 font-semibold text-amber-800">⚠ Research Trigger</div> : null}
    </div>
  );
}

function EligibilityCard({ eligibility }: { eligibility?: Record<string, unknown> }) {
  const rules = (eligibility?.rules ?? {}) as Record<string, { label?: string; passed?: boolean; available?: boolean; detail?: string }>;
  return (
    <div className="rounded-[14px] border border-[#e3e8ef] bg-white p-4">
      <h3 className="mb-2 text-base font-semibold text-[#172033]">Eligibility</h3>
      {Object.entries(rules).map(([key, rule]) => <div key={key} className="flex items-center justify-between gap-3 py-1 text-sm"><span>{rule.label}</span><span className={rule.passed ? "text-emerald-700" : "text-rose-700"}>{rule.available ? rule.passed ? "✓" : "✕" : "–"} {rule.detail}</span></div>)}
    </div>
  );
}

function SetupCard({ setup }: { setup?: Record<string, unknown> }) {
  const distances = (setup?.moving_average_distances ?? {}) as Record<string, { distance_pct?: number | null; threshold_pct?: number }>;
  return (
    <div className="rounded-[14px] border border-[#e3e8ef] bg-white p-4">
      <h3 className="mb-2 text-base font-semibold text-[#172033]">Setup / Kontext</h3>
      <div className="text-sm text-[#4b5565]">{setup?.overextended ? "⚠ Überdehnt" : "Keine MA-Überdehnung"} · Test 21 EMA: {yesNo(setup?.test_21_ema)} · Test 50 SMA: {yesNo(setup?.test_50_sma)} · Natural Reaction: {yesNo(setup?.natural_reaction)}</div>
      <div className="mt-2 text-xs text-[#687386]">{Object.entries(distances).map(([label, item]) => `${label} ${signedPercent(item.distance_pct)} (Limit ±${item.threshold_pct ?? "–"}%)`).join(" · ")}</div>
    </div>
  );
}

function statusLabel(status?: string) {
  return status === "available" ? "verfügbar" : status === "partial" ? "teilweise" : status === "neutral" ? "neutral" : status === "insufficient_history" ? "zu wenig Historie" : "fehlt";
}

function signedPercent(value: unknown) {
  return typeof value === "number" ? `${value >= 0 ? "+" : ""}${value.toFixed(1)}%` : "–";
}

function signedPp(value: unknown) {
  return typeof value === "number" ? `${value >= 0 ? "+" : ""}${value.toFixed(1)} PP` : "–";
}

function yesNo(value: unknown) {
  return value === true ? "ja" : value === false ? "nein" : "–";
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
    <div className="rounded-[14px] border border-[#e3e8ef] bg-white px-3.5 py-3 shadow-[0_5px_18px_rgba(15,23,42,0.045)]">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.06em] text-[#687386]">
          <Gauge className="size-3.5 text-[#2563eb]" />
          {label}
        </div>
        <StatusChip tone={tone}>{toneLabel(tone)}</StatusChip>
      </div>
      <div className="mt-2 text-2xl font-semibold leading-none tabular-nums text-[#172033]">{Math.round(value)}</div>
      <ScoreBar value={value} tone={tone} />
      <div className="mt-1.5 text-[11px] leading-4 text-[#687386]">{detail}</div>
    </div>
  );
}

function Metric({ label, value, detail }: { label: string; value: string; detail: string }) {
  return (
    <div className="rounded-[10px] border border-[#e3e8ef] bg-white px-3 py-2.5">
      <div className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-[0.08em] text-[#687386]">
        <TrendingUp className="size-3.5" />
        {label}
      </div>
      <div className="mt-1.5 text-lg font-semibold leading-none tabular-nums text-[#172033]">{value}</div>
      <div className="mt-1 text-[11px] leading-4 text-[#687386]">{detail}</div>
    </div>
  );
}

function PriceMetric({ percent, price }: { percent?: number | null; price?: number | null }) {
  return (
    <div className="rounded-[10px] border border-[#e3e8ef] bg-white px-3 py-2.5">
      <div className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-[0.08em] text-[#687386]">
        <TrendingUp className="size-3.5" />
        Aktueller Preis
      </div>
      <div className="mt-1.5 text-lg font-semibold leading-none tabular-nums text-[#172033]">{money(price)}</div>
      <div className={`mt-1 text-[11px] font-medium ${priceMoveToneClass(percent)}`}>Veränderung {pct(percent)}</div>
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
    <div className="rounded-[14px] border border-[#e3e8ef] bg-white p-4 shadow-[0_5px_18px_rgba(15,23,42,0.045)]">
      <div className="mb-2.5 flex items-center justify-between">
        <h3 className="text-base font-semibold text-[#172033]">{title}</h3>
        <StatusChip tone={tone}>{items.length}</StatusChip>
      </div>
      {items.length === 0 ? (
        <div className="text-sm text-[#687386]">{empty}</div>
      ) : (
        <div className="space-y-1.5">
          {items.map((item) => (
            <div key={item} className="flex gap-2 rounded-[10px] border border-[#e3e8ef] bg-[#f9fbfd] px-3 py-2 text-sm">
              {tone === "good" ? (
                <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-[#138a57]" />
              ) : (
                <AlertTriangle className="mt-0.5 size-4 shrink-0 text-[#b7791f]" />
              )}
              <span className="leading-5 text-[#172033]">{item}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function CheckGroup({ title, checks }: { title: string; checks: StockAssessmentCheck[] }) {
  const visibleChecks = title === "Fundamental" ? checks.filter((check) => check.label !== "Fundamental-Datenquelle") : checks;
  return (
    <div className="rounded-[10px] border border-[#e3e8ef] bg-[#f9fbfd] p-3">
      <div className="mb-2 text-sm font-semibold text-[#172033]">{title}</div>
      {visibleChecks.length === 0 ? (
        <div className="text-sm text-[#687386]">Noch keine Regeln.</div>
      ) : (
        <div className="space-y-1.5">
          {visibleChecks.map((check) => (
            <div key={check.label} className="flex gap-2 rounded-[10px] border border-[#e3e8ef] bg-white px-3 py-2 text-sm">
              {check.passed ? (
                <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-[#138a57]" />
              ) : (
                <XCircle className="mt-0.5 size-4 shrink-0 text-[#c2413b]" />
              )}
              <div>
                <div className={check.passed ? "font-medium text-[#138a57]" : "font-medium text-[#c2413b]"}>{check.label}</div>
                <div className="text-xs leading-5 text-[#687386]">
                  {check.detail}
                </div>
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
        <span className="text-[#172033]">{title}</span>
        <StatusChip tone={tone}>{signals.length}</StatusChip>
      </div>
      {signals.length === 0 ? (
        <div className="rounded-[10px] border border-[#e3e8ef] bg-[#f9fbfd] px-3 py-2 text-sm text-[#687386]">Keine Signale.</div>
      ) : (
        <div className="space-y-1.5">
          {signals.map((signal) => (
            <div key={`${signal.category}-${signal.label}`} className="rounded-[10px] border border-[#e3e8ef] bg-[#f9fbfd] px-3 py-2">
              <div className="text-sm font-medium text-[#172033]">{signal.label}</div>
              {signal.detail && <div className="mt-1 text-xs leading-5 text-[#687386]">{signal.detail}</div>}
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
    <div className="mt-3 h-2 overflow-hidden rounded-full bg-[#e3e8ef]">
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
  return tone === "good" ? "Stark" : tone === "warning" ? "Wachsam" : tone === "bad" ? "Schwach" : "Neutral";
}

function friendlyAssessmentMessage(message: string) {
  return message.replaceAll("Price Cache", "Kursdaten").replaceAll("Price-Cache", "Kursdaten");
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

function priceMoveToneClass(value?: number | null) {
  if (typeof value !== "number" || Number.isNaN(value)) return "text-[#687386]";
  if (value > 0) return "text-[#138a57]";
  if (value < 0) return "text-[#c2413b]";
  return "text-[#687386]";
}

function atrRegime(value?: number | null) {
  if (typeof value !== "number" || Number.isNaN(value)) return "21 Tage";
  if (value < 2.5) return "Ruhig (<2,5%)";
  if (value <= 4) return "Lebhaft (2,5-4%)";
  if (value <= 8) return "Stürmisch (4-8%)";
  return "Explosiv (>8%)";
}

function betaRegime(value?: number | null) {
  if (typeof value !== "number" || Number.isNaN(value)) return "Fundamental-Cache";
  if (value < 0.98) return "Defensiv (<0,98)";
  if (value <= 1.02) return "Marktnah (0,98-1,02)";
  if (value <= 2) return "Wachstumsorientiert (>1,03-2)";
  return "Hochdynamisch (>2)";
}

function numberOrDash(value?: number | null) {
  if (typeof value !== "number" || Number.isNaN(value)) return "-";
  return `${Number.isInteger(value) ? value : value.toFixed(2)}`;
}

function earningsBoxClass(tone: Tone) {
  if (tone === "good") {
    return "flex gap-2 rounded-[20px] border border-[#b7e2cf] bg-[#eaf7ef] p-3 text-sm font-medium text-[#138a57]";
  }
  if (tone === "bad") {
    return "flex gap-2 rounded-[20px] border border-[#f0b9b5] bg-[#fff0ef] p-3 text-sm font-medium text-[#c2413b]";
  }
  return "flex gap-2 rounded-[20px] border border-[#efd58f] bg-[#fff7df] p-3 text-sm font-medium text-[#9a650f]";
}
