"use client";

import { useQuery } from "@tanstack/react-query";
import { BarChart3, Plus, RefreshCw, X } from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";
import { useMemo, useState } from "react";
import { CollapsiblePanel } from "@/components/ui/collapsible-panel";
import { StatusChip } from "@/components/ui/status-chip";
import { api } from "@/lib/api/client";
import type { StockAssessmentCompareItem, WorkspaceState } from "@/lib/types/api";

const defaultTickers = ["NVDA", "MSFT", "AAPL", "AMZN", "GOOGL"];
const categories = [
  "Gesamtscore",
  "Technisch",
  "Fundamental",
  "Gleitende Durchschnitte",
  "Chartverhalten"
] as const;

type CompareCategory = (typeof categories)[number];

export function StockComparePanel() {
  const [open, setOpen] = useState(false);
  const [tickers, setTickers] = useState<string[]>(defaultTickers);
  const [manualInput, setManualInput] = useState("");
  const [category, setCategory] = useState<CompareCategory>("Gesamtscore");
  const workspaceQuery = useQuery<WorkspaceState>({
    queryKey: ["workspace"],
    queryFn: api.workspace,
    enabled: open,
    staleTime: 30_000
  });
  const compareQuery = useQuery({
    queryKey: ["stock-assessment-compare", tickers],
    queryFn: () => api.stockAssessmentCompare(tickers),
    enabled: open && tickers.length >= 2,
    staleTime: 60_000
  });
  const rows = useMemo(() => sortRows(compareQuery.data?.rows ?? [], category), [compareQuery.data?.rows, category]);
  const suggestions = (workspaceQuery.data?.watchlist ?? []).filter((ticker) => !tickers.includes(ticker)).slice(0, 10);

  function addTickers(values: string[]) {
    const next = uniqueTickers([...tickers, ...values]);
    setTickers(next.slice(0, 12));
  }

  function submitManual() {
    const parsed = parseTickers(manualInput);
    if (!parsed.length) return;
    addTickers(parsed);
    setManualInput("");
  }

  return (
    <CollapsiblePanel
      title="Aktienvergleich"
      subtitle="Ticker auswählen, Kategorien lokal wechseln und direkt in die Detailanalyse springen. Lädt erst beim Öffnen."
      open={open}
      onOpenChange={setOpen}
      summary={
        <>
          <StatusChip tone={compareQuery.data?.source === "database" ? "good" : compareQuery.data?.source === "partial" ? "warning" : "neutral"}>
            {!compareQuery.isFetched ? "nicht geladen" : compareQuery.data?.source === "database" ? "Vollständig" : compareQuery.data?.source === "partial" ? "Teilweise" : "Assessment Cache"}
          </StatusChip>
          <StatusChip tone="neutral">{tickers.length}/12 Ticker</StatusChip>
        </>
      }
    >
      <div className="border-b border-[#2d333d] p-5">
        <div className="flex justify-end">
          <button
            className="inline-flex items-center justify-center gap-2 rounded border border-[#2d333d] bg-[#111419] px-3 py-2 text-sm transition hover:border-emerald-300/60"
            type="button"
            onClick={() => compareQuery.refetch()}
          >
            <RefreshCw size={15} className={compareQuery.isFetching ? "animate-spin text-emerald-300" : "text-[#a0a7b4]"} />
            Aktualisieren
          </button>
        </div>

        <div className="mt-4 grid gap-3 lg:grid-cols-[1fr_auto]">
          <input
            className="input-dark"
            placeholder="Weitere Ticker, z. B. AMD, AVGO, NFLX"
            value={manualInput}
            onChange={(event) => setManualInput(event.target.value.toUpperCase())}
            onKeyDown={(event) => {
              if (event.key === "Enter") submitManual();
            }}
          />
          <button
            className="inline-flex items-center justify-center gap-2 rounded border border-emerald-300/40 bg-emerald-300/10 px-4 py-2 text-sm text-emerald-100 disabled:cursor-not-allowed disabled:opacity-50"
            disabled={!parseTickers(manualInput).length || tickers.length >= 12}
            type="button"
            onClick={submitManual}
          >
            <Plus size={16} />
            Hinzufügen
          </button>
        </div>

        <div className="mt-4 flex flex-wrap gap-2">
          {tickers.map((ticker) => (
            <span key={ticker} className="inline-flex items-center overflow-hidden rounded border border-[#2d333d] bg-[#111419] text-sm">
              <Link className="px-3 py-2 text-emerald-100 hover:bg-[#1f242c]" href={`/stocks/${encodeURIComponent(ticker)}`}>
                {ticker}
              </Link>
              <button
                aria-label={`${ticker} entfernen`}
                className="border-l border-[#2d333d] px-2 py-2 text-[#a0a7b4] hover:bg-rose-300/10 hover:text-rose-100 disabled:cursor-not-allowed disabled:opacity-40"
                disabled={tickers.length <= 2}
                type="button"
                onClick={() => setTickers(tickers.filter((item) => item !== ticker))}
              >
                <X size={14} />
              </button>
            </span>
          ))}
        </div>

        {suggestions.length > 0 && (
          <div className="mt-4 flex flex-wrap items-center gap-2 text-sm">
            <span className="text-xs uppercase text-[#77808f]">Watchlist</span>
            {suggestions.map((ticker) => (
              <button
                key={ticker}
                className="rounded border border-[#2d333d] bg-[#111419] px-2.5 py-1.5 text-xs text-[#dbe4ef] hover:border-emerald-300/60 disabled:cursor-not-allowed disabled:opacity-50"
                disabled={tickers.length >= 12}
                type="button"
                onClick={() => addTickers([ticker])}
              >
                + {ticker}
              </button>
            ))}
          </div>
        )}

        <div className="mt-4 flex flex-wrap gap-2">
          {categories.map((item) => (
            <button
              key={item}
              className={[
                "rounded border px-3 py-2 text-sm transition",
                category === item
                  ? "border-emerald-300/60 bg-emerald-300/10 text-emerald-100"
                  : "border-[#2d333d] bg-[#111419] text-[#a0a7b4] hover:border-[#697386]"
              ].join(" ")}
              type="button"
              onClick={() => setCategory(item)}
            >
              {item}
            </button>
          ))}
        </div>
      </div>

      {compareQuery.isError && (
        <div className="border-b border-[#2d333d] px-5 py-3 text-sm text-rose-200">
          {compareQuery.error instanceof Error ? compareQuery.error.message : "Aktienvergleich konnte nicht geladen werden."}
        </div>
      )}

      {compareQuery.data?.missing_tickers.length ? (
        <div className="border-b border-[#2d333d] px-5 py-3 text-sm text-amber-100">
          Price Cache fehlt oder ist zu kurz für: {compareQuery.data.missing_tickers.join(", ")}.
        </div>
      ) : null}

      {compareQuery.isLoading ? (
        <div className="p-5 text-sm text-[#a0a7b4]">Aktienvergleich lädt...</div>
      ) : tickers.length < 2 ? (
        <div className="p-5 text-sm text-[#a0a7b4]">Bitte mindestens zwei Ticker auswählen.</div>
      ) : rows.length === 0 ? (
        <div className="p-5 text-sm text-[#a0a7b4]">Noch keine Vergleichsdaten. Lade zuerst Prices und RS Ratings.</div>
      ) : (
        <>
          <CompareTable category={category} rows={rows} />
          <details className="border-t border-[#2d333d]">
            <summary className="cursor-pointer px-5 py-3 text-sm text-[#a0a7b4] hover:text-[#dbe4ef]">
              Alle Kennzahlen im direkten Vergleich
            </summary>
            <RawMetricsTable rows={rows} />
          </details>
        </>
      )}
    </CollapsiblePanel>
  );
}

function CompareTable({ category, rows }: { category: CompareCategory; rows: StockAssessmentCompareItem[] }) {
  const columns = columnsForCategory(category);
  return (
    <div className="max-h-[560px] overflow-auto">
      <table className="w-full min-w-[980px] border-collapse text-sm">
        <thead className="sticky top-0 bg-[#1f242c] text-left text-xs uppercase text-[#a0a7b4]">
          <tr>
            {columns.map((column) => (
              <th key={column.key} className="border-b border-[#2d333d] px-4 py-3 font-medium">
                {column.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.ticker} className="border-b border-[#242a33] transition hover:bg-[#20262f]">
              {columns.map((column) => (
                <td key={column.key} className="px-4 py-3">
                  {column.render(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function RawMetricsTable({ rows }: { rows: StockAssessmentCompareItem[] }) {
  return (
    <div className="max-h-[420px] overflow-auto">
      <table className="w-full min-w-[1180px] border-collapse text-sm">
        <thead className="sticky top-0 bg-[#1f242c] text-left text-xs uppercase text-[#a0a7b4]">
          <tr>
            {["Ticker", "Preis", "1M", "3M", "6M", "Drawdown", "ATR", "Beta", "RS", "10-SMA", "21-EMA", "50-SMA", "200-SMA", "MA-Ordnung"].map((label) => (
              <th key={label} className="border-b border-[#2d333d] px-4 py-3 font-medium">{label}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.ticker} className="border-b border-[#242a33]">
              <td className="px-4 py-3"><TickerCell row={row} /></td>
              <td className="px-4 py-3">{money(row.price)}</td>
              <td className="px-4 py-3"><PctCell value={row.perf_1m_pct} /></td>
              <td className="px-4 py-3"><PctCell value={row.perf_3m_pct} /></td>
              <td className="px-4 py-3"><PctCell value={row.perf_6m_pct} /></td>
              <td className="px-4 py-3"><PctCell value={row.drawdown_52w_pct} /></td>
              <td className="px-4 py-3">{pct(row.atr_pct)}</td>
              <td className="px-4 py-3">{number(row.beta, 2)}</td>
              <td className="px-4 py-3">{number(row.rs_rating, 0)}</td>
              <td className="px-4 py-3">{boolChip(row.above_sma10)}</td>
              <td className="px-4 py-3">{boolChip(row.above_ema21)}</td>
              <td className="px-4 py-3">{boolChip(row.above_sma50)}</td>
              <td className="px-4 py-3">{boolChip(row.above_sma200)}</td>
              <td className="px-4 py-3">{boolChip(row.ma_order)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

type Column = {
  key: string;
  label: string;
  render: (row: StockAssessmentCompareItem) => ReactNode;
};

function columnsForCategory(category: CompareCategory): Column[] {
  const base: Column[] = [
    { key: "rank", label: "Rang", render: (row) => <span className="tabular-nums">{row.rank}</span> },
    { key: "ticker", label: "Ticker", render: (row) => <TickerCell row={row} /> }
  ];
  if (category === "Technisch") {
    return [
      ...base,
      { key: "technical", label: "Technisch", render: (row) => scoreChip(row.technical_score, row.verdict_tone) },
      { key: "positive", label: "Positiv", render: (row) => number(row.technical_positive, 0) },
      { key: "negative", label: "Negativ", render: (row) => number(row.technical_negative, 0) },
      { key: "neutral", label: "Neutral", render: (row) => number(row.technical_neutral, 0) },
      { key: "rs", label: "RS", render: (row) => number(row.rs_rating, 0) },
      { key: "context", label: "Kontext", render: (row) => context(row) }
    ];
  }
  if (category === "Fundamental") {
    return [
      ...base,
      { key: "fundamental", label: "Fundamental", render: (row) => scoreChip(row.fundamental_score, row.verdict_tone) },
      { key: "criteria", label: "Kriterien", render: (row) => `${row.fundamental_criteria_passed}/${row.fundamental_criteria_total}` },
      { key: "positive", label: "Positiv", render: (row) => number(row.fundamental_positive, 0) },
      { key: "negative", label: "Negativ", render: (row) => number(row.fundamental_negative, 0) },
      { key: "neutral", label: "Neutral", render: (row) => number(row.fundamental_neutral, 0) },
      { key: "beta", label: "Beta", render: (row) => number(row.beta, 2) }
    ];
  }
  if (category === "Gleitende Durchschnitte") {
    return [
      ...base,
      { key: "ma_score", label: "MA-Score", render: (row) => scoreChip(row.moving_average_score, row.verdict_tone) },
      { key: "sma200", label: "> 200-SMA", render: (row) => boolChip(row.above_sma200) },
      { key: "sma50", label: "> 50-SMA", render: (row) => boolChip(row.above_sma50) },
      { key: "ema21", label: "> 21-EMA", render: (row) => boolChip(row.above_ema21) },
      { key: "sma10", label: "> 10-SMA", render: (row) => boolChip(row.above_sma10) },
      { key: "order", label: "MA-Ordnung", render: (row) => boolChip(row.ma_order) }
    ];
  }
  if (category === "Chartverhalten") {
    return [
      ...base,
      { key: "chart", label: "Chart", render: (row) => scoreChip(row.chart_behavior_score, row.verdict_tone) },
      { key: "positive", label: "Positiv", render: (row) => number(row.chart_positive, 0) },
      { key: "negative", label: "Negativ", render: (row) => number(row.chart_negative, 0) },
      { key: "neutral", label: "Neutral", render: (row) => number(row.chart_neutral, 0) },
      { key: "context", label: "Kontext", render: (row) => context(row) }
    ];
  }
  return [
    ...base,
    { key: "overall", label: "Gesamt", render: (row) => scoreChip(row.overall_score, row.verdict_tone) },
    { key: "technical", label: "Technisch", render: (row) => number(row.technical_score, 0) },
    { key: "fundamental", label: "Fundamental", render: (row) => number(row.fundamental_score, 0) },
    { key: "ma", label: "Trend", render: (row) => number(row.moving_average_score, 0) },
    { key: "chart", label: "Chart", render: (row) => number(row.chart_behavior_score, 0) },
    { key: "verdict", label: "Status", render: (row) => <StatusChip tone={row.verdict_tone}>{row.verdict_label}</StatusChip> }
  ];
}

function TickerCell({ row }: { row: StockAssessmentCompareItem }) {
  return (
    <Link className="group inline-flex items-center gap-2" href={`/stocks/${encodeURIComponent(row.ticker)}`}>
      <BarChart3 className="size-4 text-[#77808f] group-hover:text-emerald-300" />
      <span>
        <span className="block font-semibold text-emerald-100">{row.ticker}</span>
        <span className="block max-w-48 truncate text-xs text-[#77808f]">{row.name}</span>
      </span>
    </Link>
  );
}

function sortRows(rows: StockAssessmentCompareItem[], category: CompareCategory) {
  const scoreKey =
    category === "Technisch"
      ? "technical_score"
      : category === "Fundamental"
        ? "fundamental_score"
        : category === "Gleitende Durchschnitte"
          ? "moving_average_score"
          : category === "Chartverhalten"
            ? "chart_behavior_score"
            : "overall_score";
  return [...rows]
    .sort((a, b) => (Number(b[scoreKey]) || 0) - (Number(a[scoreKey]) || 0) || a.ticker.localeCompare(b.ticker))
    .map((row, index) => ({ ...row, rank: index + 1 }));
}

function parseTickers(value: string) {
  return uniqueTickers(value.replaceAll(";", ",").split(","));
}

function uniqueTickers(values: string[]) {
  return Array.from(
    new Set(
      values
        .map((value) =>
          value
            .trim()
            .toUpperCase()
            .split("")
            .filter((char) => /[A-Z0-9.-]/.test(char))
            .join("")
        )
        .filter(Boolean)
    )
  );
}

function scoreChip(value: number, tone: StockAssessmentCompareItem["verdict_tone"]) {
  return <StatusChip tone={tone}>{number(value, 0)}</StatusChip>;
}

function context(row: StockAssessmentCompareItem) {
  return <div className="max-w-96 truncate text-xs text-[#a0a7b4]">{row.top_warning || row.top_driver || row.verdict_label}</div>;
}

function boolChip(value?: boolean | null) {
  if (value === undefined || value === null) return <StatusChip tone="neutral">-</StatusChip>;
  return <StatusChip tone={value ? "good" : "warning"}>{value ? "Ja" : "Nein"}</StatusChip>;
}

function PctCell({ value }: { value?: number | null }) {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return <span className="text-[#697386]">-</span>;
  }
  return <span className={value >= 0 ? "text-emerald-300" : "text-rose-300"}>{formatPct(value)}</span>;
}

function money(value?: number | null) {
  if (typeof value !== "number" || Number.isNaN(value)) return "-";
  return new Intl.NumberFormat("de-DE", { style: "currency", currency: "USD", maximumFractionDigits: 2 }).format(value);
}

function pct(value?: number | null) {
  if (typeof value !== "number" || Number.isNaN(value)) return "-";
  return `${value.toFixed(1)}%`;
}

function formatPct(value?: number | null) {
  if (typeof value !== "number" || Number.isNaN(value)) return "-";
  return `${value >= 0 ? "+" : ""}${value.toFixed(1)}%`;
}

function number(value?: number | null, digits = 1) {
  if (typeof value !== "number" || Number.isNaN(value)) return "-";
  return value.toFixed(digits);
}
