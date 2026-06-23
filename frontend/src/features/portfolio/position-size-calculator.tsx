"use client";

import { Calculator, ChevronDown, RefreshCw } from "lucide-react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import type { ReactNode } from "react";
import { StatusChip } from "@/components/ui/status-chip";
import { api } from "@/lib/api/client";
import type { PortfolioPositionSizeRequest, PortfolioPositionSizeResult } from "@/lib/types/api";

type CalculatorMode = "loss_budget" | "risk_contribution";
type StopUnit = "pct" | "usd";

const money = new Intl.NumberFormat("de-DE", { maximumFractionDigits: 0, style: "currency", currency: "USD" });
const preciseMoney = new Intl.NumberFormat("de-DE", { minimumFractionDigits: 2, maximumFractionDigits: 2, style: "currency", currency: "USD" });
const number = new Intl.NumberFormat("de-DE", { maximumFractionDigits: 2 });

export function PositionSizeCalculator() {
  const { data: snapshot } = useQuery({ queryKey: ["portfolio-snapshot"], queryFn: api.portfolioSnapshot });
  const { data: settings } = useQuery({ queryKey: ["settings"], queryFn: api.settings });
  const [mode, setMode] = useState<CalculatorMode>("loss_budget");
  const [stopUnit, setStopUnit] = useState<StopUnit>("pct");
  const [depotValue, setDepotValue] = useState("");
  const [riskPct, setRiskPct] = useState("");
  const [targetRiskContribution, setTargetRiskContribution] = useState("");
  const [ticker, setTicker] = useState("");
  const [buyPrice, setBuyPrice] = useState("100");
  const [stopPct, setStopPct] = useState("7");
  const [stopUsd, setStopUsd] = useState("7");
  const [currentPrice, setCurrentPrice] = useState("");
  const [atrPct, setAtrPct] = useState("");
  const [beta, setBeta] = useState("");
  const [marketAtrPct, setMarketAtrPct] = useState("");

  const effectiveDepotValue = depotValue || String(Math.trunc(snapshot?.total_value ?? 0));
  const effectiveRiskPct = riskPct || String(settings?.risk_per_position_pct ?? 1);
  const effectiveTargetRiskContribution =
    targetRiskContribution || String(settings?.target_risk_contribution ?? 0.2);
  const effectiveMarketAtrPct = marketAtrPct || (snapshot?.market_atr_pct ? String(snapshot.market_atr_pct) : "");

  const request = useMemo<PortfolioPositionSizeRequest>(
    () => ({
      depot_value: positiveNumber(effectiveDepotValue),
      risk_per_position_pct: clamp(positiveNumber(effectiveRiskPct) || 1, 0.1, 5),
      target_risk_contribution: clamp(positiveNumber(effectiveTargetRiskContribution) || 0.2, 0.05, 0.5),
      buy_price: Math.max(positiveNumber(buyPrice), 0.01),
      stop_unit: stopUnit,
      stop_amount: stopUnit === "usd" ? Math.max(positiveNumber(stopUsd), 0.01) : null,
      stop_pct: clamp(positiveNumber(stopPct) || 7, 0.1, 50),
      current_price: optionalNumber(currentPrice),
      atr_pct: optionalNumber(atrPct),
      beta: optionalNumber(beta),
      market_atr_pct: optionalNumber(effectiveMarketAtrPct)
    }),
    [
      atrPct,
      beta,
      buyPrice,
      currentPrice,
      effectiveDepotValue,
      effectiveMarketAtrPct,
      effectiveRiskPct,
      effectiveTargetRiskContribution,
      stopPct,
      stopUnit,
      stopUsd
    ]
  );

  const localResult = useMemo(() => calculatePositionSize(request, mode), [mode, request]);

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
      const tickerBeta = data.metrics.beta ?? data.fundamentals?.beta;
      if (tickerBeta) {
        setBeta(String(Number(tickerBeta.toFixed(2))));
      }
    }
  });

  return (
    <details className="group rounded border border-[#2d333d] bg-[#171a20]">
      <summary className="flex cursor-pointer list-none flex-col gap-3 p-5 marker:hidden md:flex-row md:items-start md:justify-between">
        <div>
          <h2 className="text-base font-semibold">Stückzahl- und Positionsgrößen-Rechner</h2>
          <p className="mt-1 max-w-3xl text-sm leading-6 text-[#a0a7b4]">
            Berechnet die Stückzahl entweder aus einem festen Verlustbudget oder aus dem gewünschten Risikobeitrag der Aktie.
            Ticker-Metriken kommen aus dem gespeicherten Price- und Fundamental-Cache.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <StatusChip tone={assessment.isPending ? "warning" : assessment.data ? "good" : "neutral"}>
            {assessment.isPending ? "lädt" : assessment.data ? "Ticker geladen" : "lokal"}
          </StatusChip>
          <ChevronDown className="size-4 text-[#a0a7b4] transition group-open:rotate-180" />
        </div>
      </summary>

      <div className="grid gap-4 border-t border-[#2d333d] p-5 xl:grid-cols-[1fr_360px]">
        <div className="space-y-4">
          <div className="grid gap-2 rounded border border-[#2d333d] bg-[#111419] p-2 sm:grid-cols-2">
            <ModeButton
              active={mode === "loss_budget"}
              description="Maximaler Verlustbetrag bestimmt die Stückzahl."
              label="Maximaler Verlust"
              onClick={() => setMode("loss_budget")}
            />
            <ModeButton
              active={mode === "risk_contribution"}
              description="Gewünschter Risikobeitrag geteilt durch Beta-Balancer."
              label="Risikobeitrag"
              onClick={() => setMode("risk_contribution")}
            />
          </div>

          <div className="grid gap-3 md:grid-cols-3">
            <Field label="Depotwert USD">
              <input className="input-dark" min="0" step="500" type="number" value={effectiveDepotValue} onChange={(event) => setDepotValue(integerInput(event.target.value))} />
            </Field>
            <Field label="Ticker optional">
              <input className="input-dark" placeholder="NVDA" value={ticker} onChange={(event) => setTicker(event.target.value.toUpperCase())} />
            </Field>
            <Field label="Einstiegspreis">
              <input className="input-dark" min="0.01" step="0.01" type="number" value={buyPrice} onChange={(event) => setBuyPrice(event.target.value)} />
            </Field>
          </div>

          {mode === "loss_budget" ? (
            <div className="grid gap-3 md:grid-cols-3">
              <Field label="Max. Depotverlust %">
                <input className="input-dark" max="5" min="0.1" step="0.1" type="number" value={effectiveRiskPct} onChange={(event) => setRiskPct(event.target.value)} />
              </Field>
              <Field label="Stoppabstand">
                <div className="grid grid-cols-[1fr_92px] gap-2">
                  <input
                    className="input-dark"
                    max={stopUnit === "pct" ? 50 : undefined}
                    min="0.01"
                    step={stopUnit === "pct" ? 0.5 : 0.01}
                    type="number"
                    value={stopUnit === "pct" ? stopPct : stopUsd}
                    onChange={(event) => (stopUnit === "pct" ? setStopPct(event.target.value) : setStopUsd(event.target.value))}
                  />
                  <select className="input-dark" value={stopUnit} onChange={(event) => setStopUnit(event.target.value as StopUnit)}>
                    <option value="pct">%</option>
                    <option value="usd">USD</option>
                  </select>
                </div>
              </Field>
              <div className="rounded border border-[#2d333d] bg-[#111419] p-3 text-sm leading-5 text-[#a0a7b4]">
                Max. Verlust pro Aktie = Einstiegspreis x Stoppabstand. Die Stückzahl wird aus dem Verlustbudget geteilt durch diesen Betrag berechnet.
              </div>
            </div>
          ) : (
            <div className="space-y-3">
              <div className="grid gap-3 md:grid-cols-4">
                <Field label="Risikobeitrag">
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
                <Field label="ATR % Aktie">
                  <input className="input-dark" min="0" step="0.1" type="number" value={atrPct} onChange={(event) => setAtrPct(event.target.value)} />
                </Field>
                <Field label="Beta Aktie">
                  <input className="input-dark" min="0" step="0.1" type="number" value={beta} onChange={(event) => setBeta(event.target.value)} />
                </Field>
                <Field label="S&P 500 ATR %">
                  <input
                    className="input-dark"
                    min="0.01"
                    step="0.1"
                    type="number"
                    value={effectiveMarketAtrPct}
                    onChange={(event) => setMarketAtrPct(event.target.value)}
                  />
                </Field>
              </div>
              <div className="rounded border border-[#2d333d] bg-[#111419] p-3 text-sm leading-6 text-[#a0a7b4]">
                <span className="font-medium text-[#d8dde6]">Risikobeitrag:</span> 0,15 defensiver oder sehr diversifiziert · 0,20 Standard für 8-12 Positionen · 0,30 konzentrierter Stil mit mehr Einzeltitel-Risiko.
              </div>
            </div>
          )}

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
          </div>

          {assessment.error && (
            <div className="rounded border border-rose-300/30 bg-rose-300/10 p-3 text-sm text-rose-100">
              {assessment.error instanceof Error ? assessment.error.message : "Ticker-Metriken konnten nicht geladen werden."}
            </div>
          )}
        </div>

        <ResultCard mode={mode} result={localResult} />
      </div>
    </details>
  );
}

function ResultCard({ mode, result }: { mode: CalculatorMode; result: PortfolioPositionSizeResult }) {
  return (
    <div className="rounded border border-[#2d333d] bg-[#111419] p-4">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <p className="text-sm text-[#a0a7b4]">Stückzahl</p>
          <p className="text-3xl font-semibold tabular-nums">{result.recommended_max_shares}</p>
        </div>
        <Calculator className="text-emerald-300" size={28} />
      </div>
      {mode === "loss_budget" ? (
        <div className="space-y-3 text-sm">
          <Metric label="Max. Verlust Depot" value={money.format(result.risk_budget)} />
          <Metric label="Max. Verlust pro Aktie" value={preciseMoney.format(result.risk_per_share)} />
          <Metric label="Stopkurs" value={preciseMoney.format(result.stop_price)} />
          <Metric label="Anzahl Aktien" value={String(result.max_shares_by_loss_budget)} />
          <Metric label="Größe der Position" value={money.format(result.max_position_value_by_loss_budget)} />
        </div>
      ) : (
        <div className="space-y-3 text-sm">
          <Metric label="Beta-Balancer Score" value={result.balancer_score == null ? "-" : number.format(result.balancer_score)} />
          <Metric label="Max. Positionsgewicht" value={formatPct(result.max_weight_pct_by_balancer)} />
          <Metric label="Max. Positionsgröße" value={result.max_position_value_by_balancer == null ? "-" : money.format(result.max_position_value_by_balancer)} />
          <Metric label="Max. Stück" value={result.max_shares_by_balancer == null ? "-" : String(result.max_shares_by_balancer)} />
          <Metric label="Risikobeitrag-Limit" value={result.limiting_factor === "insufficient_data" ? "Daten fehlen" : "berechnet"} />
        </div>
      )}
      {result.warnings.length > 0 && (
        <div className="mt-4 rounded border border-amber-300/30 bg-amber-300/10 p-3 text-xs leading-5 text-amber-100">
          {result.warnings[0]}
        </div>
      )}
    </div>
  );
}

function calculatePositionSize(payload: PortfolioPositionSizeRequest, mode: CalculatorMode): PortfolioPositionSizeResult {
  const riskBudget = payload.depot_value * (payload.risk_per_position_pct / 100);
  const riskPerShare =
    payload.stop_unit === "usd" && payload.stop_amount
      ? payload.stop_amount
      : payload.buy_price * (payload.stop_pct / 100);
  const stopPrice = Math.max(payload.buy_price - riskPerShare, 0);
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
  } else if (mode === "risk_contribution") {
    warnings.push("Beta-Balancer nicht berechnet: ATR%, Beta oder Markt-ATR fehlen.");
  }

  const recommended =
    mode === "risk_contribution"
      ? maxSharesByBalancer ?? 0
      : maxSharesByLoss;
  const limitingFactor =
    mode === "risk_contribution"
      ? maxSharesByBalancer == null
        ? "insufficient_data"
        : "beta_balancer"
      : "loss_budget";

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

function ModeButton({
  active,
  description,
  label,
  onClick
}: {
  active: boolean;
  description: string;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      className={[
        "rounded border p-3 text-left transition",
        active
          ? "border-emerald-300/60 bg-emerald-300/10 text-emerald-100"
          : "border-[#2d333d] bg-[#171a20] text-[#d8dde6] hover:border-[#4a5362]"
      ].join(" ")}
      type="button"
      onClick={onClick}
    >
      <span className="block text-sm font-semibold">{label}</span>
      <span className="mt-1 block text-xs leading-5 text-[#a0a7b4]">{description}</span>
    </button>
  );
}

function positiveNumber(value: string) {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 0;
}

function optionalNumber(value: string) {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
}

function integerInput(value: string) {
  if (!value.trim()) return "";
  const parsed = Number(value);
  if (!Number.isFinite(parsed) || parsed < 0) return "";
  return String(Math.trunc(parsed));
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

function Field({ label, children }: { label: string; children: ReactNode }) {
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
