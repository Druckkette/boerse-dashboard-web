"use client";

import { useMemo } from "react";
import type { ReactNode } from "react";
import { BarChart3, CalendarClock, Database, RefreshCw, TrendingUp } from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { StatusChip } from "@/components/ui/status-chip";
import { api } from "@/lib/api/client";
import type {
  StockFundamentalsAnnualEps,
  StockFundamentalsAnnualRevenue,
  StockFundamentalsEpsQuarter,
  StockFundamentalsItem,
  StockFundamentalsRevenueQuarter,
  Tone
} from "@/lib/types/api";

export function StockFundamentalsPanel({ ticker }: { ticker: string }) {
  const clean = ticker.toUpperCase();
  const queryClient = useQueryClient();

  const query = useQuery({
    queryKey: ["stock-fundamentals", clean],
    queryFn: () => api.stockFundamentals(clean),
    staleTime: 60_000
  });

  const item = query.data?.item ?? null;
  const scorePreview = useMemo(() => previewFundamentalScore(item), [item]);
  const earningsTone = useMemo(() => toneForEarnings(item?.next_earnings_date), [item?.next_earnings_date]);

  const refreshMutation = useMutation({
    mutationFn: () =>
      api.startJob({
        type: "refresh_fundamentals",
        payload: {
          tickers: [clean],
          include_holders: true,
          source: "stock_detail"
        }
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["jobs"] });
      window.setTimeout(() => {
        void queryClient.invalidateQueries({ queryKey: ["stock-fundamentals", clean] });
        void queryClient.invalidateQueries({ queryKey: ["stock-assessment", clean] });
        void queryClient.invalidateQueries({ queryKey: ["stock-assessment-ranking"] });
      }, 1200);
    }
  });

  return (
    <section className="rounded border border-[#2d333d] bg-[#171a20] p-5">
      <div className="mb-5 flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <Database className="size-5 text-[#8ea4c8]" />
            <h2 className="text-lg font-semibold">Fundamental-Cache</h2>
          </div>
          <p className="mt-1 text-sm text-[#a0a7b4]">
            {item
              ? `Stand ${item.as_of || "unbekannt"} · ${item.source || "Quelle unbekannt"}`
              : "Noch kein gespeicherter Fundamentals-Datensatz."}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <StatusChip tone={item ? "good" : "warning"}>{item ? "gespeichert" : "leer"}</StatusChip>
          <StatusChip tone={toneForScore(scorePreview)}>{Math.round(scorePreview)}/100</StatusChip>
          <button
            className="inline-flex h-9 items-center justify-center gap-2 rounded border border-sky-300/30 bg-sky-400/10 px-3 text-sm font-medium text-sky-100 transition hover:bg-sky-400/15 disabled:cursor-not-allowed disabled:opacity-50"
            disabled={refreshMutation.isPending}
            onClick={() => refreshMutation.mutate()}
            type="button"
          >
            <RefreshCw className={`size-4 ${refreshMutation.isPending ? "animate-spin" : ""}`} />
            {refreshMutation.isPending ? "Job startet" : "Fundamentals aktualisieren"}
          </button>
        </div>
      </div>

      {query.isError && (
        <div className="mb-4 rounded border border-rose-300/25 bg-rose-950/20 p-3 text-sm text-rose-100">
          Fundamentals konnten nicht geladen werden.
        </div>
      )}
      {refreshMutation.isError && (
        <div className="mb-4 rounded border border-rose-300/25 bg-rose-950/20 p-3 text-sm text-rose-100">
          Fundamental-Refresh konnte nicht gestartet werden. Prüfe Backend, Worker und Job-Seite.
        </div>
      )}
      {refreshMutation.isSuccess && (
        <div className="mb-4 rounded border border-emerald-300/20 bg-emerald-950/20 p-3 text-sm text-emerald-100">
          Fundamental-Refresh wurde als Worker-Job gestartet. Die Detaildaten aktualisieren sich nach Abschluss.
        </div>
      )}

      {!item && !query.isLoading ? (
        <EmptyFundamentals ticker={clean} />
      ) : (
        <div className="space-y-4">
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            <MetricTile label="Stichtag" value={item?.as_of || "n/a"} detail={item?.fiscal_period || "Keine Periode"} />
            <MetricTile label="ROE" value={formatPct(item?.roe_pct)} detail="Zielbereich ab 17%" tone={thresholdTone(item?.roe_pct, 17)} />
            <MetricTile label="Gewinnmarge" value={formatPct(item?.profit_margin_pct)} detail="Positiv ist Pflicht" tone={thresholdTone(item?.profit_margin_pct, 0, true)} />
            <MetricTile label="Summe EPS 4Q" value={formatNumber(item?.trailing_eps)} detail="Muss über 0 liegen" tone={(item?.trailing_eps ?? -Infinity) > 0 ? "good" : "warning"} />
            <MetricTile label="Institutionen" value={formatInteger(item?.institutional_holders)} detail={formatPct(item?.institutional_ownership_pct, "gehalten")} />
            <MetricTile label="Beta" value={formatNumber(item?.beta)} detail="Risikokontext" />
            <MetricTile label="Nächste Earnings" value={item?.next_earnings_date || "n/a"} detail={earningsHint(item?.next_earnings_date)} tone={earningsTone} />
            <MetricTile label="Kurzfelder" value={formatPct(item?.quarterly_eps_growth_pct)} detail={`EPS Q · Umsatz Q ${formatPct(item?.quarterly_revenue_growth_pct)}`} />
          </div>

          <div className="grid gap-4 xl:grid-cols-2">
            <HistoryPanel
              icon={<TrendingUp className="size-4" />}
              title="EPS letzte 3 Quartale"
              description="Das Quartalskriterium besteht nur, wenn jedes der letzten drei Quartale mindestens +20% YoY liefert."
              chip={epsHistorySummary(item?.eps_quarter_history ?? [])}
              tone={epsHistoryTone(item?.eps_quarter_history ?? [])}
            >
              <EpsQuarterTable history={item?.eps_quarter_history ?? []} />
            </HistoryPanel>

            <HistoryPanel
              icon={<TrendingUp className="size-4" />}
              title="EPS letzte 3 Jahre"
              description="Das jährliche EPS-Kriterium besteht nur, wenn jedes der letzten drei Jahre mindestens +20% YoY liefert."
              chip={annualEpsHistorySummary(item?.annual_eps_history ?? [])}
              tone={annualEpsHistoryTone(item?.annual_eps_history ?? [])}
            >
              <AnnualEpsTable history={item?.annual_eps_history ?? []} />
            </HistoryPanel>
          </div>

          <div className="grid gap-4 xl:grid-cols-2">
            <HistoryPanel
              icon={<BarChart3 className="size-4" />}
              title="Umsatz letzte 3 Quartale"
              description="Das Quartalskriterium folgt der EPS-Regel: alle drei Quartale müssen jeweils mindestens +20% YoY erreichen."
              chip={revenueHistorySummary(item?.revenue_quarter_history ?? [])}
              tone={revenueHistoryTone(item?.revenue_quarter_history ?? [])}
            >
              <RevenueQuarterTable history={item?.revenue_quarter_history ?? []} />
            </HistoryPanel>

            <HistoryPanel
              icon={<BarChart3 className="size-4" />}
              title="Umsatz letzte 3 Jahre"
              description="Das Jahreskriterium besteht nur, wenn jedes der letzten drei Jahre mindestens +20% Umsatzwachstum YoY liefert."
              chip={annualRevenueHistorySummary(item?.annual_revenue_history ?? [])}
              tone={annualRevenueHistoryTone(item?.annual_revenue_history ?? [])}
            >
              <AnnualRevenueTable history={item?.annual_revenue_history ?? []} />
            </HistoryPanel>
          </div>

          <div className="grid gap-3 md:grid-cols-3">
            <RuleTile
              label="EPS-Beschleunigung"
              tone={accelerationTone(epsAcceleration(item?.eps_quarter_history ?? [], item?.quarterly_eps_accelerating))}
              value={accelerationLabel(epsAcceleration(item?.eps_quarter_history ?? [], item?.quarterly_eps_accelerating))}
              detail="Bonus: EPS-Wachstum steigt über die letzten Quartale."
            />
            <RuleTile
              label="Umsatz-Beschleunigung"
              tone={accelerationTone(revenueAcceleration(item?.revenue_quarter_history ?? [], item?.quarterly_revenue_accelerating))}
              value={accelerationLabel(revenueAcceleration(item?.revenue_quarter_history ?? [], item?.quarterly_revenue_accelerating))}
              detail="Bonus: Umsatzwachstum steigt über die letzten Quartale."
            />
            <RuleTile
              label="Earnings-Risiko"
              tone={earningsTone}
              value={item?.next_earnings_date || "kein Termin"}
              detail={earningsHint(item?.next_earnings_date)}
            />
          </div>

          <div className="flex items-center gap-2 border-t border-[#242a33] pt-4 text-sm text-[#a0a7b4]">
            <CalendarClock className="size-4" />
            <span>Automatische Aktualisierung läuft über Smart-Refresh um 16:00 und 22:30 Uhr sowie über diesen gezielten Worker-Job.</span>
          </div>
        </div>
      )}
    </section>
  );
}

function EmptyFundamentals({ ticker }: { ticker: string }) {
  return (
    <div className="rounded border border-dashed border-[#343b47] bg-[#111419] p-5">
      <h3 className="text-sm font-semibold">{ticker}: keine Fundamentals gespeichert</h3>
      <p className="mt-2 max-w-2xl text-sm leading-6 text-[#a0a7b4]">
        Starte den Fundamental-Refresh. Der Worker lädt yfinance/FMP/SEC-Daten und schreibt den Snapshot in den Cache;
        die Bewertung liest danach nur noch diese vorbereiteten Daten.
      </p>
    </div>
  );
}

function MetricTile({
  label,
  value,
  detail,
  tone = "neutral"
}: {
  label: string;
  value: string;
  detail: string;
  tone?: Tone;
}) {
  return (
    <div className="rounded border border-[#242a33] bg-[#111419] p-3">
      <div className="text-xs uppercase text-[#7f8794]">{label}</div>
      <div className={`mt-2 text-lg font-semibold ${toneText(tone)}`}>{value}</div>
      <div className="mt-1 min-h-5 text-xs leading-5 text-[#a0a7b4]">{detail}</div>
    </div>
  );
}

function RuleTile({
  label,
  value,
  detail,
  tone
}: {
  label: string;
  value: string;
  detail: string;
  tone: Tone;
}) {
  return (
    <div className="rounded border border-[#242a33] bg-[#111419] p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold">{label}</h3>
          <p className="mt-2 text-sm leading-6 text-[#a0a7b4]">{detail}</p>
        </div>
        <StatusChip tone={tone}>{value}</StatusChip>
      </div>
    </div>
  );
}

function HistoryPanel({
  icon,
  title,
  description,
  chip,
  tone,
  children
}: {
  icon: ReactNode;
  title: string;
  description: string;
  chip: string;
  tone: Tone;
  children: ReactNode;
}) {
  return (
    <div className="rounded border border-[#242a33] bg-[#111419] p-4">
      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div>
          <div className="flex items-center gap-2 text-sm font-semibold">
            <span className="text-[#8ea4c8]">{icon}</span>
            <h3>{title}</h3>
          </div>
          <p className="mt-2 text-xs leading-5 text-[#7f8794]">{description}</p>
        </div>
        <StatusChip tone={tone}>{chip}</StatusChip>
      </div>
      <div className="mt-4 overflow-x-auto">{children}</div>
    </div>
  );
}

function EpsQuarterTable({ history }: { history: StockFundamentalsEpsQuarter[] }) {
  const rows = padEpsHistory(history);
  return (
    <HistoryTable
      columns={["Quartal", "EPS", "Vorjahr", "YoY", "Status"]}
      rows={rows.map((item, index) => {
        const growth = computeEpsGrowth(item);
        return [
          item.fiscal_period || `Quartal ${index + 1}`,
          formatNumber(item.eps_current_quarter),
          formatNumber(item.eps_same_quarter_last_year),
          formatSignedPct(growth),
          growthStatus(growth)
        ];
      })}
    />
  );
}

function AnnualEpsTable({ history }: { history: StockFundamentalsAnnualEps[] }) {
  const rows = padAnnualEpsHistory(history);
  return (
    <HistoryTable
      columns={["Jahr", "EPS", "Vorjahr", "YoY", "Status"]}
      rows={rows.map((item, index) => {
        const growth = computeAnnualEpsGrowth(item);
        return [
          item.fiscal_year || `Jahr ${index + 1}`,
          formatNumber(item.eps_current_year),
          formatNumber(item.eps_previous_year),
          formatSignedPct(growth),
          growthStatus(growth)
        ];
      })}
    />
  );
}

function RevenueQuarterTable({ history }: { history: StockFundamentalsRevenueQuarter[] }) {
  const rows = padRevenueHistory(history);
  return (
    <HistoryTable
      columns={["Quartal", "Umsatz", "Vorjahr", "YoY", "Status"]}
      rows={rows.map((item, index) => {
        const growth = computeRevenueGrowth(item);
        return [
          item.fiscal_period || `Quartal ${index + 1}`,
          formatLargeNumber(item.revenue_current_quarter),
          formatLargeNumber(item.revenue_same_quarter_last_year),
          formatSignedPct(growth),
          growthStatus(growth)
        ];
      })}
    />
  );
}

function AnnualRevenueTable({ history }: { history: StockFundamentalsAnnualRevenue[] }) {
  const rows = padAnnualRevenueHistory(history);
  return (
    <HistoryTable
      columns={["Jahr", "Umsatz", "Vorjahr", "YoY", "Status"]}
      rows={rows.map((item, index) => {
        const growth = computeAnnualRevenueGrowth(item);
        return [
          item.fiscal_year || `Jahr ${index + 1}`,
          formatLargeNumber(item.revenue_current_year),
          formatLargeNumber(item.revenue_previous_year),
          formatSignedPct(growth),
          growthStatus(growth)
        ];
      })}
    />
  );
}

function HistoryTable({ columns, rows }: { columns: string[]; rows: string[][] }) {
  return (
    <table className="min-w-full border-separate border-spacing-0 text-left text-sm">
      <thead>
        <tr>
          {columns.map((column) => (
            <th key={column} className="border-b border-[#2d333d] px-3 py-2 text-xs font-medium uppercase text-[#7f8794]">
              {column}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((row, rowIndex) => (
          <tr key={rowIndex} className="border-b border-[#242a33]">
            {row.map((cell, cellIndex) => (
              <td key={`${rowIndex}-${cellIndex}`} className={`px-3 py-3 ${cellClass(cell, cellIndex, row.length)}`}>
                {cell}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function cellClass(cell: string, index: number, length: number) {
  if (index === length - 1) {
    if (cell === "bestanden") return "font-medium text-emerald-200";
    if (cell === "unter 20%") return "font-medium text-amber-200";
    return "text-[#7f8794]";
  }
  if (cell.startsWith("+") && index === length - 2) return "font-medium text-emerald-200";
  if (cell.startsWith("-") && index === length - 2) return "font-medium text-rose-200";
  return index === 0 ? "font-medium text-[#e8ecf3]" : "text-[#c3c9d4]";
}

function previewFundamentalScore(item: StockFundamentalsItem | null) {
  if (!item) return 0;
  const checks = [
    epsHistoryScore(item.eps_quarter_history),
    epsAcceleration(item.eps_quarter_history, item.quarterly_eps_accelerating) === true ? 1 : 0,
    annualEpsHistoryScore(item.annual_eps_history),
    (item.trailing_eps ?? -Infinity) > 0 ? 1 : 0,
    revenueHistoryScore(item.revenue_quarter_history),
    revenueAcceleration(item.revenue_quarter_history, item.quarterly_revenue_accelerating) === true ? 1 : 0,
    annualRevenueHistoryScore(item.annual_revenue_history),
    (item.roe_pct ?? -Infinity) >= 17 ? 1 : 0,
    (item.profit_margin_pct ?? -Infinity) > 0 ? 1 : 0
  ];
  return (checks.reduce((sum, value) => sum + value, 0) / checks.length) * 100;
}

function padEpsHistory(history: StockFundamentalsEpsQuarter[]) {
  const rows = history.slice(0, 3).map((item) => ({
    fiscal_period: item.fiscal_period ?? "",
    eps_current_quarter: item.eps_current_quarter ?? null,
    eps_same_quarter_last_year: item.eps_same_quarter_last_year ?? null,
    eps_growth_yoy_pct: item.eps_growth_yoy_pct ?? null,
    flag: item.flag ?? null
  }));
  while (rows.length < 3) {
    rows.push({
      fiscal_period: "",
      eps_current_quarter: null,
      eps_same_quarter_last_year: null,
      eps_growth_yoy_pct: null,
      flag: null
    });
  }
  return rows;
}

function epsHistoryScore(history: StockFundamentalsEpsQuarter[]) {
  const values = padEpsHistory(history).map(computeEpsGrowth);
  if (values.some((value) => value === null)) return 0;
  return values.filter((value) => value !== null && value >= 20).length / 3;
}

function epsHistoryTone(history: StockFundamentalsEpsQuarter[]): Tone {
  const values = padEpsHistory(history).map(computeEpsGrowth);
  if (values.every((value) => value !== null && value >= 20)) return "good";
  if (values.some((value) => value !== null && value >= 20)) return "warning";
  return "neutral";
}

function epsHistorySummary(history: StockFundamentalsEpsQuarter[]) {
  const values = padEpsHistory(history).map(computeEpsGrowth);
  const valid = values.filter((value) => value !== null);
  const passed = valid.filter((value) => value >= 20).length;
  if (valid.length < 3) return `${valid.length}/3 verfügbar`;
  return `${passed}/3 >=20%`;
}

function padAnnualEpsHistory(history: StockFundamentalsAnnualEps[]) {
  const rows = history.slice(0, 3).map((item) => ({
    fiscal_year: item.fiscal_year ?? "",
    eps_current_year: item.eps_current_year ?? null,
    eps_previous_year: item.eps_previous_year ?? null,
    eps_growth_yoy_pct: item.eps_growth_yoy_pct ?? null,
    flag: item.flag ?? null
  }));
  while (rows.length < 3) {
    rows.push({
      fiscal_year: "",
      eps_current_year: null,
      eps_previous_year: null,
      eps_growth_yoy_pct: null,
      flag: null
    });
  }
  return rows;
}

function annualEpsHistoryScore(history: StockFundamentalsAnnualEps[]) {
  const values = padAnnualEpsHistory(history).map(computeAnnualEpsGrowth);
  if (values.some((value) => value === null)) return 0;
  return values.filter((value) => value !== null && value >= 20).length / 3;
}

function annualEpsHistoryTone(history: StockFundamentalsAnnualEps[]): Tone {
  const values = padAnnualEpsHistory(history).map(computeAnnualEpsGrowth);
  if (values.every((value) => value !== null && value >= 20)) return "good";
  if (values.some((value) => value !== null && value >= 20)) return "warning";
  return "neutral";
}

function annualEpsHistorySummary(history: StockFundamentalsAnnualEps[]) {
  const values = padAnnualEpsHistory(history).map(computeAnnualEpsGrowth);
  const valid = values.filter((value) => value !== null);
  const passed = valid.filter((value) => value >= 20).length;
  if (valid.length < 3) return `${valid.length}/3 verfügbar`;
  return `${passed}/3 >=20%`;
}

function padRevenueHistory(history: StockFundamentalsRevenueQuarter[]) {
  const rows = history.slice(0, 3).map((item) => ({
    fiscal_period: item.fiscal_period ?? "",
    revenue_current_quarter: item.revenue_current_quarter ?? null,
    revenue_same_quarter_last_year: item.revenue_same_quarter_last_year ?? null,
    revenue_growth_yoy_pct: item.revenue_growth_yoy_pct ?? null,
    flag: item.flag ?? null
  }));
  while (rows.length < 3) {
    rows.push({
      fiscal_period: "",
      revenue_current_quarter: null,
      revenue_same_quarter_last_year: null,
      revenue_growth_yoy_pct: null,
      flag: null
    });
  }
  return rows;
}

function revenueHistoryScore(history: StockFundamentalsRevenueQuarter[]) {
  const values = padRevenueHistory(history).map(computeRevenueGrowth);
  if (values.some((value) => value === null)) return 0;
  return values.filter((value) => value !== null && value >= 20).length / 3;
}

function revenueHistoryTone(history: StockFundamentalsRevenueQuarter[]): Tone {
  const values = padRevenueHistory(history).map(computeRevenueGrowth);
  if (values.every((value) => value !== null && value >= 20)) return "good";
  if (values.some((value) => value !== null && value >= 20)) return "warning";
  return "neutral";
}

function revenueHistorySummary(history: StockFundamentalsRevenueQuarter[]) {
  const values = padRevenueHistory(history).map(computeRevenueGrowth);
  const valid = values.filter((value) => value !== null);
  const passed = valid.filter((value) => value >= 20).length;
  if (valid.length < 3) return `${valid.length}/3 verfügbar`;
  return `${passed}/3 >=20%`;
}

function padAnnualRevenueHistory(history: StockFundamentalsAnnualRevenue[]) {
  const rows = history.slice(0, 3).map((item) => ({
    fiscal_year: item.fiscal_year ?? "",
    revenue_current_year: item.revenue_current_year ?? null,
    revenue_previous_year: item.revenue_previous_year ?? null,
    revenue_growth_yoy_pct: item.revenue_growth_yoy_pct ?? null,
    flag: item.flag ?? null
  }));
  while (rows.length < 3) {
    rows.push({
      fiscal_year: "",
      revenue_current_year: null,
      revenue_previous_year: null,
      revenue_growth_yoy_pct: null,
      flag: null
    });
  }
  return rows;
}

function annualRevenueHistoryScore(history: StockFundamentalsAnnualRevenue[]) {
  const values = padAnnualRevenueHistory(history).map(computeAnnualRevenueGrowth);
  if (values.some((value) => value === null)) return 0;
  return values.filter((value) => value !== null && value >= 20).length / 3;
}

function annualRevenueHistoryTone(history: StockFundamentalsAnnualRevenue[]): Tone {
  const values = padAnnualRevenueHistory(history).map(computeAnnualRevenueGrowth);
  if (values.every((value) => value !== null && value >= 20)) return "good";
  if (values.some((value) => value !== null && value >= 20)) return "warning";
  return "neutral";
}

function annualRevenueHistorySummary(history: StockFundamentalsAnnualRevenue[]) {
  const values = padAnnualRevenueHistory(history).map(computeAnnualRevenueGrowth);
  const valid = values.filter((value) => value !== null);
  const passed = valid.filter((value) => value >= 20).length;
  if (valid.length < 3) return `${valid.length}/3 verfügbar`;
  return `${passed}/3 >=20%`;
}

function computeEpsGrowth(item: StockFundamentalsEpsQuarter) {
  const current = item.eps_current_quarter;
  const previous = item.eps_same_quarter_last_year;
  if (typeof current !== "number" || typeof previous !== "number" || previous <= 0) {
    return item.eps_growth_yoy_pct ?? null;
  }
  return Math.round((current / previous - 1) * 1000) / 10;
}

function computeAnnualEpsGrowth(item: StockFundamentalsAnnualEps) {
  const current = item.eps_current_year;
  const previous = item.eps_previous_year;
  if (typeof current !== "number" || typeof previous !== "number" || previous <= 0) {
    return item.eps_growth_yoy_pct ?? null;
  }
  return Math.round((current / previous - 1) * 1000) / 10;
}

function computeRevenueGrowth(item: StockFundamentalsRevenueQuarter) {
  const current = item.revenue_current_quarter;
  const previous = item.revenue_same_quarter_last_year;
  if (typeof current !== "number" || typeof previous !== "number" || previous <= 0) {
    return item.revenue_growth_yoy_pct ?? null;
  }
  return Math.round((current / previous - 1) * 1000) / 10;
}

function computeAnnualRevenueGrowth(item: StockFundamentalsAnnualRevenue) {
  const current = item.revenue_current_year;
  const previous = item.revenue_previous_year;
  if (typeof current !== "number" || typeof previous !== "number" || previous <= 0) {
    return item.revenue_growth_yoy_pct ?? null;
  }
  return Math.round((current / previous - 1) * 1000) / 10;
}

function epsAcceleration(history: StockFundamentalsEpsQuarter[], fallback?: boolean | null) {
  const values = padEpsHistory(history).map(computeEpsGrowth);
  if (values.every((value) => value !== null)) {
    return Boolean(values[0] !== null && values[1] !== null && values[2] !== null && values[0] > values[1] && values[1] > values[2]);
  }
  return fallback ?? null;
}

function revenueAcceleration(history: StockFundamentalsRevenueQuarter[], fallback?: boolean | null) {
  const values = padRevenueHistory(history).map(computeRevenueGrowth);
  if (values.every((value) => value !== null)) {
    return Boolean(values[0] !== null && values[1] !== null && values[2] !== null && values[0] > values[1] && values[1] > values[2]);
  }
  return fallback ?? null;
}

function accelerationTone(value: boolean | null): Tone {
  if (value === true) return "good";
  if (value === false) return "warning";
  return "neutral";
}

function accelerationLabel(value: boolean | null) {
  if (value === true) return "ja";
  if (value === false) return "nein";
  return "n/a";
}

function growthStatus(value: number | null) {
  if (value === null) return "nicht verfügbar";
  return value >= 20 ? "bestanden" : "unter 20%";
}

function formatSignedPct(value: number | null) {
  if (value === null || Number.isNaN(value)) return "n/a";
  return `${value >= 0 ? "+" : ""}${value.toFixed(1)}%`;
}

function formatPct(value?: number | null, suffix = "") {
  if (value === null || value === undefined || Number.isNaN(value)) return "n/a";
  return `${value.toFixed(1)}%${suffix ? ` ${suffix}` : ""}`;
}

function formatNumber(value?: number | null) {
  if (value === null || value === undefined || Number.isNaN(value)) return "n/a";
  return new Intl.NumberFormat("de-DE", { maximumFractionDigits: 2 }).format(value);
}

function formatInteger(value?: number | null) {
  if (value === null || value === undefined || Number.isNaN(value)) return "n/a";
  return new Intl.NumberFormat("de-DE", { maximumFractionDigits: 0 }).format(value);
}

function formatLargeNumber(value?: number | null) {
  if (value === null || value === undefined || Number.isNaN(value)) return "n/a";
  const abs = Math.abs(value);
  if (abs >= 1_000_000_000) return `${formatNumber(value / 1_000_000_000)} Mrd.`;
  if (abs >= 1_000_000) return `${formatNumber(value / 1_000_000)} Mio.`;
  return formatNumber(value);
}

function thresholdTone(value: number | null | undefined, threshold: number, strict = false): Tone {
  if (value === null || value === undefined) return "neutral";
  return strict ? (value > threshold ? "good" : "warning") : value >= threshold ? "good" : "warning";
}

function toneForScore(value: number): Tone {
  if (value >= 75) return "good";
  if (value >= 55) return "warning";
  if (value >= 45) return "neutral";
  return "bad";
}

function toneForEarnings(value?: string | null): Tone {
  if (!value) return "neutral";
  const days = daysUntil(value);
  if (days === null) return "neutral";
  if (days <= 7) return "bad";
  if (days <= 21) return "warning";
  return "good";
}

function earningsHint(value?: string | null) {
  if (!value) return "Kein Earnings-Termin gespeichert.";
  const days = daysUntil(value);
  if (days === null) return "Earnings-Termin ist nicht lesbar.";
  if (days < 0) return `Earnings-Termin liegt ${Math.abs(days)} Kalendertage zurück.`;
  if (days === 0) return "Earnings-Termin ist heute.";
  return `Earnings in ${days} Kalendertagen.`;
}

function daysUntil(value: string) {
  const target = new Date(`${value}T00:00:00`);
  if (Number.isNaN(target.getTime())) return null;
  const today = new Date();
  const localToday = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  return Math.round((target.getTime() - localToday.getTime()) / 86_400_000);
}

function toneText(tone: Tone) {
  if (tone === "good") return "text-emerald-100";
  if (tone === "warning") return "text-amber-100";
  if (tone === "bad") return "text-rose-100";
  return "text-[#f3f6fb]";
}
