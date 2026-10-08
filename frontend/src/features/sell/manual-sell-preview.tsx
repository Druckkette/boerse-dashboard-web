"use client";

import { useBetaMode } from "@/components/beta-mode-provider";
import { useMutation } from "@tanstack/react-query";
import { api } from "@/lib/api/client";
import { formatPercent } from "@/lib/format";
import type { SellRuleFeature } from "@/lib/types/api";

export function ManualSellPreview() {
  const beta = useBetaMode();
  const preview = useMutation({ mutationFn: (body: Parameters<typeof api.sellPreview>[0]) => beta ? api.betaSellPreview(body) : api.sellPreview(body) });
  const result = preview.data;
  const inputClass = "mt-1 w-full rounded-[9px] border border-[#d8e1ea] bg-white px-3 py-2 text-sm text-[#172033]";
  return <section className="rounded-[14px] border border-[#e3e8ef] bg-white p-4">
    <h2 className="text-sm font-semibold text-[#172033]">Aktie frei prüfen</h2>
    <p className="mt-1 text-xs text-[#687386]">Bewerte eine Aktie mit eigenem Einstieg, auch ohne Depotposition. Der Einstiegskurs gilt in der ausgewählten Währung. Die Prüfung nutzt den vorhandenen Kursverlauf und speichert keine Position.</p>
    <form className="mt-4 grid items-end gap-3 sm:grid-cols-2 xl:grid-cols-5" onSubmit={(event) => {
      event.preventDefault();
      const form = new FormData(event.currentTarget);
      preview.mutate({ ticker: String(form.get("ticker")).trim().toUpperCase(), buy_price: Number(form.get("buy_price")), buy_date: String(form.get("buy_date")), currency: String(form.get("currency")) });
    }}>
      <label className="text-xs text-[#687386]">Aktie / Ticker<input className={inputClass} name="ticker" placeholder="z. B. AAPL" required maxLength={32} pattern="[A-Za-z0-9.^=_\-]+" /></label>
      <label className="text-xs text-[#687386]">Einstiegskurs<input className={inputClass} name="buy_price" type="number" min="0.000001" step="any" required /></label>
      <label className="text-xs text-[#687386]">Einstiegsdatum<input className={inputClass} name="buy_date" type="date" required max={new Date().toLocaleDateString("en-CA", { timeZone: "Europe/Berlin" })} /></label>
      <label className="text-xs text-[#687386]">Währung<select aria-label="Währung" className={inputClass} name="currency" defaultValue="USD">{["USD", "EUR", "GBP", "CHF", "CAD", "JPY", "HKD", "AUD"].map((currency) => <option key={currency}>{currency}</option>)}</select></label>
      <button className="rounded-[9px] bg-[#0f766e] px-4 py-2 text-sm font-semibold text-white disabled:opacity-55" disabled={preview.isPending} type="submit">{preview.isPending ? "Prüfung läuft …" : "Verkaufen bewerten"}</button>
    </form>
    {preview.isError && <p role="alert" className="mt-3 text-sm text-[#c2413b]">{preview.error.message}</p>}
    {result && !preview.isPending && !preview.isError && <div className="mt-4 space-y-3" aria-live="polite">
      <div className="rounded-[9px] bg-[#f6f8fb] p-3 text-sm text-[#172033]">
        <strong>{result.metrics.ticker} · {result.evaluation.display_label}</strong>
        <p className="mt-1">Einstieg: {result.metrics.raw_payload.buy_price} {result.metrics.raw_payload.currency} am {result.metrics.raw_payload.buy_date} · Kurs: {result.metrics.current_price} · P&amp;L: {formatPercent(result.metrics.pnl_pct ?? 0)} · Datenstand: {result.metrics.as_of}</p>
        <p className="mt-1">{result.evaluation.explanation_short}</p>
      </div>
      <div className="grid gap-3 lg:grid-cols-3">
        <FeatureList title="Nothalt" features={result.evaluation.emergency_features} />
        <FeatureList title="Offensives Verkaufen" features={result.evaluation.offensive_features} />
        <FeatureList title="Defensives Verkaufen" features={result.evaluation.defensive_features} />
      </div>
    </div>}
  </section>;
}

function FeatureList({ title, features }: { title: string; features: SellRuleFeature[] }) {
  return <div className="rounded-[9px] border border-[#e3e8ef] p-3">
    <h3 className="text-sm font-semibold text-[#172033]">{title}</h3>
    <ul className="mt-2 space-y-2">{features.map((feature) => <li key={feature.id} className="text-xs text-[#687386]">
      <div className="font-medium text-[#172033]">{feature.label} · {feature.active ? "Aktiv" : "Nicht aktiv"}</div>
      <div>{feature.value}{feature.threshold ? ` · Schwelle: ${feature.threshold}` : ""}</div>
      <div>{feature.detail}</div>
    </li>)}</ul>
  </div>;
}
