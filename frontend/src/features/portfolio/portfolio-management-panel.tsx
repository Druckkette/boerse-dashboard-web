"use client";

import { Banknote, ChevronDown, CircleDollarSign, Save, Trash2 } from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useRef, useState } from "react";
import { StatusChip } from "@/components/ui/status-chip";
import { api } from "@/lib/api/client";
import { berlinDate } from "@/lib/date";
import { createBookingId } from "@/lib/booking-id";
import type { PortfolioPosition } from "@/lib/types/api";
import { PositionSizeCalculator } from "./position-size-calculator";
import {
  IsinMappingMaintenancePanel,
  TradeRepublicTransactionImportPanel
} from "./trade-republic-import-panel";

export function PortfolioManagementPanel({ positions }: { positions: PortfolioPosition[] }) {
  return (
    <div className="min-w-0 space-y-4">
      <PositionSizeCalculator />
      <CollapsibleSection
        title="Positionen, Verkäufe und Cashflows"
        description="Manuelle Depotpflege nur bei Bedarf öffnen. Das Kaufdatum steuert den Stärke-nach-Kauf-Check."
        badge={`${positions.length} Positionen`}
      >
        <div className="grid gap-4 xl:grid-cols-[1fr_0.9fr]">
          <PositionEditor positions={positions} />
          <div className="min-w-0 space-y-4">
            <SellBooking positions={positions} />
            <CashFlowPanel />
          </div>
        </div>
      </CollapsibleSection>
      <CollapsibleSection
        title="Trade-Republic-Import und ISIN-Zuordnungen"
        description="TR-CSV direkt im Portfolio hochladen. Gespeicherte ISIN-Zuordnungen bleiben dauerhaft nutzbar."
        badge="eingeklappt"
      >
        <div className="min-w-0 space-y-4">
          <TradeRepublicTransactionImportPanel />
          <IsinMappingMaintenancePanel />
        </div>
      </CollapsibleSection>
    </div>
  );
}

function CollapsibleSection({
  title,
  description,
  badge,
  children
}: {
  title: string;
  description: string;
  badge: string;
  children: React.ReactNode;
}) {
  return (
    <details className="group rounded border border-[var(--border)] bg-[var(--panel)]">
      <summary className="flex cursor-pointer list-none items-start justify-between gap-2 p-3 sm:p-5 marker:hidden">
        <div className="min-w-0">
          <h2 className="text-base font-semibold">{title}</h2>
          <p className="mt-1 text-sm text-[var(--muted)]">{description}</p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <span className="hidden sm:inline"><StatusChip tone="neutral">{badge}</StatusChip></span>
          <ChevronDown className="size-4 text-[var(--muted)] transition group-open:rotate-180" />
        </div>
      </summary>
      <div className="min-w-0 border-t border-[var(--border)] p-2 sm:p-5">{children}</div>
    </details>
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
  const [stopMode, setStopMode] = useState<"pct" | "price" | "none">("pct");
  const [stopPrice, setStopPrice] = useState("");
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
        stop_mode: stopMode,
        stop_pct: stopMode === "pct" && stopPct ? Number(stopPct) : null,
        stop_price: stopMode === "price" && stopPrice ? Number(stopPrice) : null,
        currency,
        note,
        broker: selected?.broker ?? "",
        account: selected?.account ?? "",
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
    setStopMode(position.stop_pct != null ? "pct" : position.stop_price != null ? "price" : "none");
    setStopPrice(position.stop_price != null ? String(position.stop_price) : "");
    setCurrency(position.currency || "EUR");
    setNote(position.note || "");
  }

  const canSave = ticker.trim().length > 0 && Number(shares) > 0 && Number(entryPrice) > 0
    && (stopMode !== "price" || Number(stopPrice) > 0)
    && (stopMode !== "pct" || (Number(stopPct) > 0 && Number(stopPct) <= 50));

  return (
    <section className="rounded border border-[var(--border)] bg-[var(--panel)] p-5">
      <div className="mb-4 flex items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold">Position erfassen</h2>
          <p className="mt-1 text-sm text-[var(--muted)]">
            Das Kaufdatum macht frische Käufe automatisch im Stärke-nach-Kauf-Check sichtbar.
          </p>
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
        <Field label="Stoppart">
          <select aria-label="Stoppart" className="input-dark" value={stopMode} onChange={(event) => setStopMode(event.target.value as typeof stopMode)}>
            <option value="pct">Prozent vom Einstand</option>
            <option value="price">Fester Stoppkurs</option>
            <option value="none">Kein Stopp</option>
          </select>
        </Field>
        {stopMode === "pct" && <Field label="Stopp %"><input aria-label="Stopp %" className="input-dark" min="0.1" max="50" step="0.1" type="number" value={stopPct} onChange={(event) => setStopPct(event.target.value)} /><p className="mt-1 text-xs text-[var(--muted)]">Wirksamer Stopp: {(Number(entryPrice) * (1 - Number(stopPct) / 100)).toFixed(2)} {currency}. Ein bisheriger fester Stoppkurs wird beim Speichern ersetzt.</p></Field>}
        {stopMode === "price" && <Field label={`Stoppkurs (${currency})`}><input className="input-dark" min="0.01" step="0.01" type="number" value={stopPrice} onChange={(event) => setStopPrice(event.target.value)} /></Field>}
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
          className="inline-flex items-center gap-2 rounded border border-emerald-300/40 bg-[var(--green-soft)] px-4 py-2 text-sm text-[var(--green)] disabled:cursor-not-allowed disabled:opacity-50"
          disabled={!canSave || saveMutation.isPending}
          type="button"
          onClick={() => saveMutation.mutate()}
        >
          <Save size={16} />
          {saveMutation.isPending ? "Speichert" : "Position speichern"}
        </button>
        <button
          className="inline-flex items-center gap-2 rounded border border-rose-300/30 bg-[var(--red-soft)] px-4 py-2 text-sm text-[var(--red)] disabled:cursor-not-allowed disabled:opacity-50"
          disabled={!selected || deleteMutation.isPending}
          type="button"
          onClick={() => deleteMutation.mutate()}
        >
          <Trash2 size={16} />
          Schließen
        </button>
      </div>
      {(saveMutation.error || deleteMutation.error) && (
        <div className="mt-4 rounded border border-rose-300/30 bg-[var(--red-soft)] p-3 text-sm text-[var(--red)]">
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
  const [currency, setCurrency] = useState(positions[0]?.currency ?? "EUR");
  const booking = useRef<{ fingerprint: string; id: string } | null>(null);

  const mutation = useMutation({
    mutationFn: () => {
      const body = {
        shares: Number(shares || position?.shares || 0),
        price: Number(price || position?.current_price || 0),
        date,
        currency
      };
      const fingerprint = JSON.stringify({ ticker, ...body });
      if (booking.current?.fingerprint !== fingerprint) booking.current = { fingerprint, id: createBookingId() };
      return api.sellPortfolioPosition(ticker, { ...body, booking_id: booking.current.id });
    },
    onSuccess: () => { booking.current = null; invalidatePortfolio(queryClient); }
  });

  function selectTicker(next: string) {
    setTicker(next);
    const nextPosition = positions.find((item) => item.ticker === next);
    setShares(nextPosition ? String(nextPosition.shares) : "");
    setPrice(nextPosition ? String(nextPosition.current_price) : "");
    setCurrency(nextPosition?.currency ?? "EUR");
  }

  return (
    <section className="rounded border border-[var(--border)] bg-[var(--panel)] p-5">
      <div className="mb-4 flex items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold">Verkauf buchen</h2>
          <p className="mt-1 text-sm text-[var(--muted)]">Teil- oder Vollverkauf mit Transaktion und Cash-Wirkung.</p>
          <p className="mt-1 text-sm text-[var(--muted)]">Buchungswährung: {currency}</p>
        </div>
        <CircleDollarSign className="text-[var(--green)]" size={20} />
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
        className="mt-4 inline-flex w-full items-center justify-center gap-2 rounded border border-[var(--border)] bg-[var(--panel)] px-4 py-2 text-sm hover:border-emerald-300/60 disabled:cursor-not-allowed disabled:opacity-50"
        disabled={!ticker || Number(shares || 0) <= 0 || Number(price || 0) <= 0 || mutation.isPending}
        type="button"
        onClick={() => mutation.mutate()}
      >
        <Banknote size={16} />
        {mutation.isPending ? "Bucht" : "Verkauf buchen"}
      </button>
      {mutation.error && <p role="alert" className="mt-3 text-sm text-[var(--red)]">{mutation.error instanceof Error ? mutation.error.message : "Verkauf konnte nicht gebucht werden."}</p>}
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
    <section className="rounded border border-[var(--border)] bg-[var(--panel)] p-5">
      <div className="mb-4 flex items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold">Cashflows</h2>
          <p className="mt-1 text-sm text-[var(--muted)]">Cash-Bestand: {flowsQuery.isPending ? "wird geladen" : !flowsQuery.isError && typeof flowsQuery.data?.cash_balance === "number" && Number.isFinite(flowsQuery.data.cash_balance) ? money(flowsQuery.data.cash_balance) : "nicht verfügbar"}</p>
        </div>
        <StatusChip tone="neutral">{flowsQuery.isError ? "n/a" : flowsQuery.data?.cash_flows.length ?? "…"}</StatusChip>
      </div>
      {flowsQuery.isError && <p role="alert" className="mb-3 text-sm text-[var(--red)]">Cashbestand konnte nicht geladen werden. Bitte erneut versuchen.</p>}
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
        className="mt-4 inline-flex w-full items-center justify-center gap-2 rounded border border-[var(--border)] bg-[var(--panel)] px-4 py-2 text-sm hover:border-emerald-300/60 disabled:cursor-not-allowed disabled:opacity-50"
        disabled={Number(amount) <= 0 || mutation.isPending}
        type="button"
        onClick={() => mutation.mutate()}
      >
        <Banknote size={16} />
        {mutation.isPending ? "Bucht" : "Cashflow buchen"}
      </button>
      {mutation.error && <p role="alert" className="mt-3 text-sm text-[var(--red)]">{mutation.error instanceof Error ? mutation.error.message : "Cashflow konnte nicht gebucht werden."}</p>}
    </section>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block text-sm">
      <span className="mb-1 block text-[var(--muted)]">{label}</span>
      {children}
    </label>
  );
}

function invalidatePortfolio(queryClient: ReturnType<typeof useQueryClient>) {
  queryClient.invalidateQueries({ queryKey: ["home-dashboard"] });
  queryClient.invalidateQueries({ queryKey: ["portfolio-snapshot"] });
  queryClient.invalidateQueries({ queryKey: ["portfolio-positions"] });
  queryClient.invalidateQueries({ queryKey: ["portfolio-curve"] });
  queryClient.invalidateQueries({ queryKey: ["portfolio-transactions"] });
  queryClient.invalidateQueries({ queryKey: ["portfolio-cash-flows"] });
  queryClient.invalidateQueries({ queryKey: ["portfolio-import-history"] });
  queryClient.invalidateQueries({ queryKey: ["portfolio-buy-strength"] });
  queryClient.invalidateQueries({ queryKey: ["portfolio-analysis"] });
  queryClient.invalidateQueries({ queryKey: ["sell-ranking"] });
}

function money(value: number) {
  return `${value.toLocaleString("de-DE", { maximumFractionDigits: 0 })} EUR`;
}

function today() {
  return berlinDate();
}
