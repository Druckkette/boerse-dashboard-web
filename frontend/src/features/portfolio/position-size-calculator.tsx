"use client";

import { Calculator, ChevronDown, RefreshCw, ShieldCheck } from "lucide-react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { StatusChip } from "@/components/ui/status-chip";
import { api } from "@/lib/api/client";
import type { PortfolioPositionSizeRequest, PortfolioPositionSizeResult } from "@/lib/types/api";

const money = new Intl.NumberFormat("de-DE", { maximumFractionDigits: 0, style: "currency", currency: "EUR" });
const number = new Intl.NumberFormat("de-DE", { maximumFractionDigits: 2 });

export function PositionSizeCalculator() {
  const { data: snapshot } = useQuery({ queryKey: ["portfolio-snapshot"], queryFn: api.portfolioSnapshot });
  const { data: settings } = useQuery({ queryKey: ["settings"], queryFn: api.settings });
  const [depotValue, setDepotValue] = useState("");
  const [riskPct, setRiskPct] = useState("");
  const [targetRiskContribution, setTargetRiskContribution] = useState("");
  const [ticker, setTicker] = useState("");
  const [buyPrice, setBuyPrice] = useState("100");
  const [stopPct, setStopPct] = useState("7");
  const [currentPrice, setCurrentPrice] = useState("");
  const [atrPct, setAtrPct] = useState("");
  const [beta, setBeta] = useState("1");
  const [marketAtrPct, setMarketAtrPct] = useState("2");
  const effectiveDepotValue = depotValue || String(snapshot?.total_value ?? 0);
  const effectiveRiskPct = riskPct || String(settings?.risk_per_position_pct ?? 1);
  const effectiveTargetRiskContribution =
    targetRiskContribution || String(settings?.target_risk_contribution ?? 0.2);

  const request = useMemo<PortfolioPositionSizeRequest>(
    () => ({
      depot_value: positiveNumber(effectiveDepotValue),
      risk_per_position_pct: clamp(positiveNumber(effectiveRiskPct) || 1, 0.1, 5),
      target_risk_contribution: clamp(positiveNumber(effectiveTargetRiskContribution) || 0.2, 0.05, 0.5),
      buy_price: Math.max(positiveNumber(buyPrice), 0.01),
      stop_pct: clamp(positiveNumber(stopPct) || 7, 0.1, 50),
      current_price: optionalNumber(currentPrice),
      atr_pct: optionalNumber(atrPct),
      beta: optionalNumber(beta),
      market_atr_pct: optionalNumber(marketAtrPct)
    }),
    [
      atrPct,
      beta,
      buyPrice,
      currentPrice,
      effectiveDepotValue,
      effectiveRiskPct,
      effectiveTargetRiskContribution,
      marketAtrPct,
      stopPct
    ]
  );

  const localResult = useMemo(() => calculatePositionSize(request), [request]);

  const serverCheck = useMutation({
    mutationFn: () => api.portfolioPositionSize(request)
  });

  const assessment = useMutation({
    mutationFn: () => api.stockAssessment(ticker.trim().toUpperCase()),
    onSuccess: (data) => {
      if (data.metrics.last_close) {
        setBuyPrice(String(Number(data.metrics.last_close.toFixed(2))));
        setCurrentPrice(String(Number(data.metrics.last_close.toFixed(2))));
      }
      if (data.metrics.atr_pct) {
        setAtrPct(String(Number(data.metrics.atr_pct.toFixed(2))));
      }
    }
  });

  const displayResult = localResult;
  const limitingLabel = {
    loss_budget: "Verlustbudget",
    beta_balancer: "Beta-Balancer",
    insufficient_data: "Verlustbudget, BB-Daten fehlen"
  }[displayResult.limiting_factor];

  return (
    <details className="group rounded border border-[#2d333d] bg-[#171a20]">
      <summary className="flex cursor-pointer list-none flex-col gap-3 p-5 marker:hidden md:flex-row md:items-start md:justify-between">
        <div>
          <h2 className="text-base font-semibold">Stückzahl- und Positionsgrößen-Rechner</h2>
          <p className="mt-1 max-w-3xl text-sm leading-6 text-[#a0a7b4]">
            Verlustbudget und Beta-Balancer aus der Streamlit-App, aber ohne Seitenreload. Defaults kommen aus den
            gespeicherten Depot-Annahmen.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <StatusChip tone={serverCheck.isPending ? "warning" : serverCheck.data ? "good" : "neutral"}>
            {serverCheck.isPending ? "prüft" : serverCheck.data ? "API geprüft" : "lokal"}
          </StatusChip>
          <ChevronDown className="size-4 text-[#a0a7b4] transition group-open:rotate-180" />
        </div>
      </summary>

      <div className="grid gap-4 border-t border-[#2d333d] p-5 xl:grid-cols-[1fr_360px]">
        <div className="space-y-4">
          <div className="grid gap-3 md:grid-cols-3">
            <Field label="Depotwert EUR">
              <input className="input-dark" min="0" step="500" type="number" value={effectiveDepotValue} onChange={(event) => setDepotValue(event.target.value)} />
            </Field>
            <Field label="Max. Verlust je Idee %">
              <input className="input-dark" max="5" min="0.1" step="0.1" type="number" value={effectiveRiskPct} onChange={(event) => setRiskPct(event.target.value)} />
            </Field>
            <Field label="Ziel Risikobeitrag">
              <input
                className="input-dark"
                max="0.5"
                min="0.05"
                step="0.01"
                type="number"
                value={effectiveTargetRiskContribution}
                onChange={(event) => setTargetRiskContribution(event.target.value)}
              />
            </Field>
          </div>

          <div className="grid gap-3 md:grid-cols-4">
            <Field label="Ticker optional">
              <input className="input-dark" placeholder="NVDA" value={ticker} onChange={(event) => setTicker(event.target.value.toUpperCase())} />
            </Field>
            <Field label="Einstand">
              <input className="input-dark" min="0.01" step="0.01" type="number" value={buyPrice} onChange={(event) => setBuyPrice(event.target.value)} />
            </Field>
            <Field label="Aktueller Kurs">
              <input className="input-dark" min="0.01" step="0.01" type="number" value={currentPrice} onChange={(event) => setCurrentPrice(event.target.value)} />
            </Field>
            <Field label="Stoppabstand %">
              <input className="input-dark" max="50" min="0.1" step="0.5" type="number" value={stopPct} onChange={(event) => setStopPct(event.target.value)} />
            </Field>
          </div>

          <div className="grid gap-3 md:grid-cols-3">
            <Field label="ATR % Aktie">
              <input className="input-dark" min="0" step="0.1" type="number" value={atrPct} onChange={(event) => setAtrPct(event.target.value)} />
            </Field>
            <Field label="Beta">
              <input className="input-dark" min="0" step="0.1" type="number" value={beta} onChange={(event) => setBeta(event.target.value)} />
            </Field>
            <Field label="S&P 500 ATR %">
              <input className="input-dark" min="0.01" step="0.1" type="number" value={marketAtrPct} onChange={(event) => setMarketAtrPct(event.target.value)} />
            </Field>
          </div>

          <div className="flex flex-wrap gap-3">
            <button
              className="inline-flex items-center gap-2 rounded border border-[#2d333d] bg-[#111419] px-4 py-2 text-sm hover:border-emerald-300/60 disabled:cursor-not-allowed disabled:opacity-50"
              disabled={!ticker.trim() || assessment.isPending}
              type="button"
              onClick={() => assessment.mutate()}
            >
              <RefreshCw size={16} />
              {assessment.isPending ? "lädt" : "Ticker-Metriken laden"}
            </button>
            <button
              className="inline-flex items-center gap-2 rounded border border-emerald-300/40 bg-emerald-300/10 px-4 py-2 text-sm text-emerald-100 disabled:cursor-not-allowed disabled:opacity-50"
              disabled={serverCheck.isPending}
              type="button"
              onClick={() => serverCheck.mutate()}
            >
              <ShieldCheck size={16} />
              API-Check
            </button>
          </div>

          {(assessment.error || serverCheck.error) && (
            <div className="rounded border border-rose-300/30 bg-rose-300/10 p-3 text-sm text-rose-100">
              {(assessment.error ?? serverCheck.error) instanceof Error
                ? (assessment.error ?? serverCheck.error)?.message
                : "Aktion fehlgeschlagen."}
            </div>
          )}
        </div>

        <div className="rounded border border-[#2d333d] bg-[#111419] p-4">
          <div className="mb-4 flex items-center justify-between">
            <div>
              <p className="text-sm text-[#a0a7b4]">Empfehlung</p>
              <p className="text-3xl font-semibold tabular-nums">{displayResult.recommended_max_shares}</p>
            </div>
            <Calculator className="text-emerald-300" size={28} />
          </div>
          <div className="space-y-3 text-sm">
            <Metric label="Limitierender Faktor" value={limitingLabel} />
            <Metric label="Risikobudget / Idee" value={money.format(displayResult.risk_budget)} />
            <Metric label="Risiko pro Aktie" value={money.format(displayResult.risk_per_share)} />
            <Metric label="Stopkurs" value={money.format(displayResult.stop_price)} />
            <Metric label="Max. Wert Verlustbudget" value={money.format(displayResult.max_position_value_by_loss_budget)} />
            <Metric label="Max. Gewicht BB" value={formatPct(displayResult.max_weight_pct_by_balancer)} />
            <Metric label="Max. Stück BB" value={displayResult.max_shares_by_balancer == null ? "-" : String(displayResult.max_shares_by_balancer)} />
            <Metric label="Empfohlener Wert" value={money.format(displayResult.recommended_position_value)} />
          </div>
          {displayResult.warnings.length > 0 && (
            <div className="mt-4 rounded border border-amber-300/30 bg-amber-300/10 p-3 text-xs leading-5 text-amber-100">
              {displayResult.warnings[0]}
            </div>
          )}
        </div>
      </div>
    </details>
  );
}

function calculatePositionSize(payload: PortfolioPositionSizeRequest): PortfolioPositionSizeResult {
  const riskBudget = payload.depot_value * (payload.risk_per_position_pct / 100);
  const riskPerShare = payload.buy_price * (payload.stop_pct / 100);
  const stopPrice = payload.buy_price * (1 - payload.stop_pct / 100);
  const maxSharesByLoss = riskBudget > 0 && riskPerShare > 0 ? Math.floor(riskBudget / riskPerShare) : 0;
  const maxPositionValueByLoss = maxSharesByLoss * payload.buy_price;
  const currentPrice = payload.current_price || payload.buy_price;
  let balancerScore: number | null = null;
  let maxWeightPctByBalancer: number | null = null;
  let maxPositionValueByBalancer: number | null = null;
  let maxSharesByBalancer: number | null = null;
  const warnings: string[] = [];

  if (payload.beta != null && payload.atr_pct != null && payload.market_atr_pct) {
    balancerScore = 0.6 * payload.beta + 0.4 * (payload.atr_pct / payload.market_atr_pct);
    if (balancerScore > 0) {
      const maxWeight = payload.target_risk_contribution / balancerScore;
      maxWeightPctByBalancer = maxWeight * 100;
      maxPositionValueByBalancer = payload.depot_value * maxWeight;
      maxSharesByBalancer = currentPrice > 0 ? Math.floor(maxPositionValueByBalancer / currentPrice) : 0;
    }
  } else {
    warnings.push("Beta-Balancer nicht berechnet: ATR%, Beta oder Markt-ATR fehlen.");
  }

  const limitingFactor =
    maxSharesByBalancer == null
      ? "insufficient_data"
      : maxSharesByLoss <= maxSharesByBalancer
        ? "loss_budget"
        : "beta_balancer";
  const recommended = maxSharesByBalancer == null ? maxSharesByLoss : Math.min(maxSharesByLoss, maxSharesByBalancer);

  return {
    risk_budget: round(riskBudget, 2),
    risk_per_share: round(riskPerShare, 4),
    stop_price: round(stopPrice, 4),
    max_shares_by_loss_budget: maxSharesByLoss,
    max_position_value_by_loss_budget: round(maxPositionValueByLoss, 2),
    balancer_score: nullableRound(balancerScore, 4),
    max_weight_pct_by_balancer: nullableRound(maxWeightPctByBalancer, 4),
    max_position_value_by_balancer: nullableRound(maxPositionValueByBalancer, 2),
    max_shares_by_balancer: maxSharesByBalancer,
    recommended_max_shares: recommended,
    recommended_position_value: round(recommended * currentPrice, 2),
    limiting_factor: limitingFactor,
    warnings
  };
}

function positiveNumber(value: string) {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 0;
}

function optionalNumber(value: string) {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
}

function clamp(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value));
}

function round(value: number, digits: number) {
  return Number(value.toFixed(digits));
}

function nullableRound(value: number | null, digits: number) {
  return value == null ? null : round(value, digits);
}

function formatPct(value?: number | null) {
  return value == null ? "-" : `${number.format(value)}%`;
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block text-sm">
      <span className="mb-1 block text-[#a0a7b4]">{label}</span>
      {children}
    </label>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-3 border-b border-[#242a33] pb-2 last:border-b-0">
      <span className="text-[#a0a7b4]">{label}</span>
      <span className="text-right font-medium tabular-nums">{value}</span>
    </div>
  );
}
