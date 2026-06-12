"use client";

import { Banknote, CircleDollarSign, Save, Trash2 } from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { StatusChip } from "@/components/ui/status-chip";
import { api } from "@/lib/api/client";
import type { PortfolioPosition } from "@/lib/types/api";
import { PositionSizeCalculator } from "./position-size-calculator";

export function PortfolioManagementPanel({ positions }: { positions: PortfolioPosition[] }) {
  return (
    <div className="space-y-4">
      <PositionSizeCalculator />
      <div className="grid gap-4 xl:grid-cols-[1fr_0.9fr]">
        <PositionEditor positions={positions} />
        <div className="space-y-4">
          <SellBooking positions={positions} />
          <CashFlowPanel />
        </div>
        <PortfolioActivity />
      </div>
    </div>
  );
}

function PositionEditor({ positions }: { positions: PortfolioPosition[] }) {
  const queryClient = useQueryClient();
  const [ticker, setTicker] = useState("");
  const selected = useMemo(
    () => positions.find((position) => position.ticker === ticker.toUpperCase()),
    [positions, ticker]
  );
  const [name, setName] = useState("");
  const [shares, setShares] = useState("0");
  const [entryPrice, setEntryPrice] = useState("0");
  const [currentPrice, setCurrentPrice] = useState("");
  const [buyDate, setBuyDate] = useState(today());
  const [pivotTag, setPivotTag] = useState(today());
  const [stopPct, setStopPct] = useState("7");
  const [currency, setCurrency] = useState("EUR");
  const [note, setNote] = useState("");

  const saveMutation = useMutation({
    mutationFn: () =>
      api.upsertPortfolioPosition({
        ticker,
        name,
        shares: Number(shares),
        entry_price: Number(entryPrice),
        current_price: currentPrice ? Number(currentPrice) : null,
        buy_date: buyDate,
        pivot_tag: pivotTag,
        stop_pct: stopPct ? Number(stopPct) : null,
        currency,
        note,
        record_transaction: true
      }),
    onSuccess: () => invalidatePortfolio(queryClient)
  });

  const deleteMutation = useMutation({
    mutationFn: () => api.deletePortfolioPosition(ticker),
    onSuccess: () => {
      setTicker("");
      invalidatePortfolio(queryClient);
    }
  });

  function fillFromSelected(nextTicker: string) {
    const clean = nextTicker.toUpperCase();
    setTicker(clean);
    const position = positions.find((item) => item.ticker === clean);
    if (!position) return;
    setName(position.name);
    setShares(String(position.shares));
    setEntryPrice(String(position.entry_price));
    setCurrentPrice(String(position.current_price));
    setBuyDate(position.buy_date ?? today());
    setPivotTag(position.pivot_tag ?? position.buy_date ?? today());
    setStopPct(String(position.stop_pct ?? 7));
    setCurrency(position.currency || "EUR");
    setNote(position.note || "");
  }

  const canSave = ticker.trim().length > 0 && Number(shares) > 0 && Number(entryPrice) > 0;

  return (
    <section className="rounded border border-[#2d333d] bg-[#171a20] p-5">
      <div className="mb-4 flex items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold">Position erfassen</h2>
          <p className="mt-1 text-sm text-[#a0a7b4]">Manuelle Pflege ohne CSV-Datei und ohne Seitenreload.</p>
        </div>
        <StatusChip tone={selected ? "warning" : "neutral"}>{selected ? "Update" : "Neu"}</StatusChip>
      </div>

      <div className="grid gap-3 md:grid-cols-2">
        <Field label="Ticker">
          <input
            className="input-dark"
            list="portfolio-tickers"
            placeholder="NVDA"
            value={ticker}
            onBlur={(event) => fillFromSelected(event.target.value)}
            onChange={(event) => setTicker(event.target.value.toUpperCase())}
          />
          <datalist id="portfolio-tickers">
            {positions.map((position) => (
              <option key={position.ticker} value={position.ticker} />
            ))}
          </datalist>
        </Field>
        <Field label="Name">
          <input className="input-dark" value={name} onChange={(event) => setName(event.target.value)} />
        </Field>
        <Field label="Stück">
          <input className="input-dark" min="0" step="0.0001" type="number" value={shares} onChange={(event) => setShares(event.target.value)} />
        </Field>
        <Field label="Einstand">
          <input className="input-dark" min="0" step="0.01" type="number" value={entryPrice} onChange={(event) => setEntryPrice(event.target.value)} />
        </Field>
        <Field label="Aktueller Kurs">
          <input className="input-dark" min="0" step="0.01" type="number" value={currentPrice} onChange={(event) => setCurrentPrice(event.target.value)} />
        </Field>
        <Field label="Stopp %">
          <input className="input-dark" min="0.1" step="0.1" type="number" value={stopPct} onChange={(event) => setStopPct(event.target.value)} />
        </Field>
        <Field label="Kaufdatum">
          <input className="input-dark" type="date" value={buyDate} onChange={(event) => setBuyDate(event.target.value)} />
        </Field>
        <Field label="Pivot-Tag">
          <input className="input-dark" type="date" value={pivotTag} onChange={(event) => setPivotTag(event.target.value)} />
        </Field>
        <Field label="Währung">
          <select className="input-dark" value={currency} onChange={(event) => setCurrency(event.target.value)}>
            <option value="EUR">EUR</option>
            <option value="USD">USD</option>
          </select>
        </Field>
        <Field label="Notiz">
          <input className="input-dark" value={note} onChange={(event) => setNote(event.target.value)} />
        </Field>
      </div>

      <div className="mt-4 flex flex-wrap gap-3">
        <button
          className="inline-flex items-center gap-2 rounded border border-emerald-300/40 bg-emerald-300/10 px-4 py-2 text-sm text-emerald-100 disabled:cursor-not-allowed disabled:opacity-50"
          disabled={!canSave || saveMutation.isPending}
          type="button"
          onClick={() => saveMutation.mutate()}
        >
          <Save size={16} />
          {saveMutation.isPending ? "Speichert" : "Position speichern"}
        </button>
        <button
          className="inline-flex items-center gap-2 rounded border border-rose-300/30 bg-rose-300/10 px-4 py-2 text-sm text-rose-100 disabled:cursor-not-allowed disabled:opacity-50"
          disabled={!selected || deleteMutation.isPending}
          type="button"
          onClick={() => deleteMutation.mutate()}
        >
          <Trash2 size={16} />
          Schließen
        </button>
      </div>
      {(saveMutation.error || deleteMutation.error) && (
        <div className="mt-4 rounded border border-rose-300/30 bg-rose-300/10 p-3 text-sm text-rose-100">
          {(saveMutation.error ?? deleteMutation.error) instanceof Error
            ? (saveMutation.error ?? deleteMutation.error)?.message
            : "Portfolio-Aktion fehlgeschlagen."}
        </div>
      )}
    </section>
  );
}

function SellBooking({ positions }: { positions: PortfolioPosition[] }) {
  const queryClient = useQueryClient();
  const [ticker, setTicker] = useState(positions[0]?.ticker ?? "");
  const position = positions.find((item) => item.ticker === ticker);
  const [shares, setShares] = useState("");
  const [price, setPrice] = useState("");
  const [date, setDate] = useState(today());
  const [currency, setCurrency] = useState("EUR");

  const mutation = useMutation({
    mutationFn: () =>
      api.sellPortfolioPosition(ticker, {
        shares: Number(shares || position?.shares || 0),
        price: Number(price || position?.current_price || 0),
        date,
        currency
      }),
    onSuccess: () => invalidatePortfolio(queryClient)
  });

  function selectTicker(next: string) {
    setTicker(next);
    const nextPosition = positions.find((item) => item.ticker === next);
    setShares(nextPosition ? String(nextPosition.shares) : "");
    setPrice(nextPosition ? String(nextPosition.current_price) : "");
    setCurrency(nextPosition?.currency ?? "EUR");
  }

  return (
    <section className="rounded border border-[#2d333d] bg-[#171a20] p-5">
      <div className="mb-4 flex items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold">Verkauf buchen</h2>
          <p className="mt-1 text-sm text-[#a0a7b4]">Teil- oder Vollverkauf mit Transaktion und Cash-Wirkung.</p>
        </div>
        <CircleDollarSign className="text-emerald-300" size={20} />
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Position">
          <select className="input-dark" value={ticker} onChange={(event) => selectTicker(event.target.value)}>
            <option value="">-</option>
            {positions.map((item) => (
              <option key={item.ticker} value={item.ticker}>
                {item.ticker}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Stück">
          <input className="input-dark" max={position?.shares ?? 0} min="0" step="0.0001" type="number" value={shares} onChange={(event) => setShares(event.target.value)} />
        </Field>
        <Field label="Preis">
          <input className="input-dark" min="0" step="0.01" type="number" value={price} onChange={(event) => setPrice(event.target.value)} />
        </Field>
        <Field label="Datum">
          <input className="input-dark" type="date" value={date} onChange={(event) => setDate(event.target.value)} />
        </Field>
      </div>
      <button
        className="mt-4 inline-flex w-full items-center justify-center gap-2 rounded border border-[#2d333d] bg-[#111419] px-4 py-2 text-sm hover:border-emerald-300/60 disabled:cursor-not-allowed disabled:opacity-50"
        disabled={!ticker || Number(shares || 0) <= 0 || Number(price || 0) <= 0 || mutation.isPending}
        type="button"
        onClick={() => mutation.mutate()}
      >
        <Banknote size={16} />
        {mutation.isPending ? "Bucht" : "Verkauf buchen"}
      </button>
    </section>
  );
}

function CashFlowPanel() {
  const queryClient = useQueryClient();
  const flowsQuery = useQuery({ queryKey: ["portfolio-cash-flows"], queryFn: api.portfolioCashFlows, staleTime: 30_000 });
  const [amount, setAmount] = useState("0");
  const [flowType, setFlowType] = useState<"deposit" | "withdrawal">("deposit");
  const [date, setDate] = useState(today());
  const [note, setNote] = useState("");
  const mutation = useMutation({
    mutationFn: () =>
      api.createPortfolioCashFlow({
        amount: Number(amount),
        flow_type: flowType,
        date,
        note
      }),
    onSuccess: () => invalidatePortfolio(queryClient)
  });

  return (
    <section className="rounded border border-[#2d333d] bg-[#171a20] p-5">
      <div className="mb-4 flex items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold">Cashflows</h2>
          <p className="mt-1 text-sm text-[#a0a7b4]">Cash-Bestand: {money(flowsQuery.data?.cash_balance ?? 0)}</p>
        </div>
        <StatusChip tone="neutral">{flowsQuery.data?.cash_flows.length ?? 0}</StatusChip>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Typ">
          <select className="input-dark" value={flowType} onChange={(event) => setFlowType(event.target.value as "deposit" | "withdrawal")}>
            <option value="deposit">Einzahlung</option>
            <option value="withdrawal">Auszahlung</option>
          </select>
        </Field>
        <Field label="Betrag">
          <input className="input-dark" min="0" step="0.01" type="number" value={amount} onChange={(event) => setAmount(event.target.value)} />
        </Field>
        <Field label="Datum">
          <input className="input-dark" type="date" value={date} onChange={(event) => setDate(event.target.value)} />
        </Field>
        <Field label="Notiz">
          <input className="input-dark" value={note} onChange={(event) => setNote(event.target.value)} />
        </Field>
      </div>
      <button
        className="mt-4 inline-flex w-full items-center justify-center gap-2 rounded border border-[#2d333d] bg-[#111419] px-4 py-2 text-sm hover:border-emerald-300/60 disabled:cursor-not-allowed disabled:opacity-50"
        disabled={Number(amount) <= 0 || mutation.isPending}
        type="button"
        onClick={() => mutation.mutate()}
      >
        <Banknote size={16} />
        {mutation.isPending ? "Bucht" : "Cashflow buchen"}
      </button>
    </section>
  );
}

function PortfolioActivity() {
  const transactions = useQuery({ queryKey: ["portfolio-transactions"], queryFn: () => api.portfolioTransactions(12), staleTime: 30_000 });
  const imports = useQuery({ queryKey: ["portfolio-import-history"], queryFn: () => api.portfolioImportHistory(8), staleTime: 30_000 });
  return (
    <section className="rounded border border-[#2d333d] bg-[#171a20] p-5 xl:col-span-2">
      <div className="mb-4 flex items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold">Aktivität</h2>
          <p className="mt-1 text-sm text-[#a0a7b4]">Letzte Transaktionen und gespeicherte Importe.</p>
        </div>
        <StatusChip tone="neutral">History</StatusChip>
      </div>
      <div className="grid gap-4 xl:grid-cols-2">
        <div className="overflow-hidden rounded border border-[#242a33]">
          <table className="w-full text-sm">
            <thead className="bg-[#1f242c] text-left text-xs uppercase text-[#a0a7b4]">
              <tr>
                <th className="px-3 py-2">Datum</th>
                <th className="px-3 py-2">Ticker</th>
                <th className="px-3 py-2">Typ</th>
                <th className="px-3 py-2 text-right">Netto</th>
              </tr>
            </thead>
            <tbody>
              {(transactions.data ?? []).map((row) => (
                <tr key={row.id} className="border-t border-[#242a33]">
                  <td className="px-3 py-2 text-[#a0a7b4]">{row.date}</td>
                  <td className="px-3 py-2 font-medium">{row.ticker}</td>
                  <td className="px-3 py-2">{row.transaction_type}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{money(row.net_amount ?? 0)}</td>
                </tr>
              ))}
              {!transactions.data?.length && (
                <tr>
                  <td className="px-3 py-6 text-center text-[#7f8794]" colSpan={4}>
                    Keine Transaktionen.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        <div className="overflow-hidden rounded border border-[#242a33]">
          <table className="w-full text-sm">
            <thead className="bg-[#1f242c] text-left text-xs uppercase text-[#a0a7b4]">
              <tr>
                <th className="px-3 py-2">Zeit</th>
                <th className="px-3 py-2">Datei</th>
                <th className="px-3 py-2">Status</th>
                <th className="px-3 py-2 text-right">Zeilen</th>
              </tr>
            </thead>
            <tbody>
              {(imports.data ?? []).map((row) => (
                <tr key={row.id} className="border-t border-[#242a33]">
                  <td className="px-3 py-2 text-[#a0a7b4]">{new Date(row.created_at).toLocaleDateString("de-DE")}</td>
                  <td className="px-3 py-2">{row.file_name || row.source}</td>
                  <td className="px-3 py-2">{row.status}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{row.rows_imported}/{row.rows_total}</td>
                </tr>
              ))}
              {!imports.data?.length && (
                <tr>
                  <td className="px-3 py-6 text-center text-[#7f8794]" colSpan={4}>
                    Keine Importe.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block text-sm">
      <span className="mb-1 block text-[#a0a7b4]">{label}</span>
      {children}
    </label>
  );
}

function invalidatePortfolio(queryClient: ReturnType<typeof useQueryClient>) {
  queryClient.invalidateQueries({ queryKey: ["portfolio-snapshot"] });
  queryClient.invalidateQueries({ queryKey: ["portfolio-positions"] });
  queryClient.invalidateQueries({ queryKey: ["portfolio-curve"] });
  queryClient.invalidateQueries({ queryKey: ["portfolio-transactions"] });
  queryClient.invalidateQueries({ queryKey: ["portfolio-cash-flows"] });
  queryClient.invalidateQueries({ queryKey: ["portfolio-import-history"] });
  queryClient.invalidateQueries({ queryKey: ["sell-ranking"] });
}

function money(value: number) {
  return `${value.toLocaleString("de-DE", { maximumFractionDigits: 0 })} EUR`;
}

function today() {
  return new Date().toISOString().slice(0, 10);
}
