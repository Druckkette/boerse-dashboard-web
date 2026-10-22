"use client";
import { useQuery } from "@tanstack/react-query";
import { QueryState } from "@/components/ui/query-state";
import { LineChartCard } from "@/components/ui/line-chart-card";
import { useViewState } from "@/lib/view-state";
import { deskApi, money, percent } from "@/lib/desk";
import { portfolioYearStart } from "@/features/portfolio/portfolio-year";
import { DeskLinks, Field, Metric, Panel, useDesk } from "./shared";

export function Performance() {
  const [view, setView] = useViewState("performance", {
    start: portfolioYearStart(),
    benchmark: "SPY",
    account: "main",
  });
  const desk = useDesk();
  const query = useQuery({
    queryKey: ["desk-performance", view.start, view.benchmark, view.account],
    queryFn: () =>
      deskApi.performance(view.start, view.benchmark, view.account),
    staleTime: 60_000,
  });
  const data = query.data;
  return (
    <div className="space-y-5">
      <DeskLinks />
      <Panel title="Depotperformance">
        <div className="flex flex-wrap gap-3">
          <Field label="Depot">
            <select
              className="input-dark"
              value={view.account}
              onChange={(e) => setView({ account: e.target.value })}
            >
              <option value="main">Bestehendes Depot</option>
              {desk.data?.accounts.map((row) => (
                <option key={row.id} value={row.id}>
                  {row.name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Ab Datum">
            <input
              type="date"
              className="input-dark"
              value={view.start}
              onChange={(e) => {
                if (e.target.value) setView({ start: e.target.value });
              }}
            />
          </Field>
          <Field label="Vergleichsmaßstab">
            <select
              className="input-dark"
              value={view.benchmark}
              onChange={(e) => setView({ benchmark: e.target.value })}
            >
              {[
                ["SPY", "S&P 500 ETF"],
                ["QQQ", "Nasdaq 100 ETF"],
                ["IWM", "Russell 2000 ETF"],
                ["RSP", "S&P 500 gleichgewichtet"],
                ["^GSPC", "S&P 500 Index"],
              ].map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </Field>
        </div>
        <QueryState
          loading={query.isLoading}
          error={query.error}
          hasData={Boolean(data)}
          onRetry={() => query.refetch()}
        />
        {data && (
          <>
            <p className="text-sm text-[#526174]">
              {data.start} bis {data.end} · Basiswährung {data.currency} ·{" "}
              {data.covered_points}/{data.total_points} Tage bewertbar
            </p>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              <Metric
                label="Zeitgewichtete Rendite (TWR)"
                value={percent(data.twr_pct)}
              />
              <Metric
                label="Persönliche Rendite (XIRR, jährlich)"
                value={percent(data.mwr_annual_pct)}
              />
              <Metric
                label="Größter Rückgang (Drawdown)"
                value={percent(data.max_drawdown_pct)}
              />
              <Metric
                label="Ergebnis nach externen Cashflows"
                value={money(data.period_result, data.currency)}
              />
              <Metric
                label="Einzahlungen minus Auszahlungen"
                value={money(data.external_flow, data.currency)}
              />
              <Metric
                label={`${data.benchmark} · Kursrendite`}
                value={percent(data.benchmark_return_pct)}
              />
            </div>
            <p className="text-sm">{data.note}</p>
            <p className="text-sm text-[#526174]">
              Die zeitgewichtete Rendite bereinigt Ein- und Auszahlungen. XIRR
              berücksichtigt deren Höhe und Zeitpunkt und ist auf ein Jahr
              hochgerechnet; bei kurzen Zeiträumen kann sie stark ausschlagen.
              Bei mehrdeutiger oder nicht berechenbarer Rendite wird kein Wert
              geschätzt.
            </p>
            <p className="text-sm text-[#526174]">
              {data.benchmark_note} Ausführungsdaten enthalten erfasste Gebühren
              und Steuern. Nicht importierte Buchungen können nicht
              berücksichtigt werden.
            </p>
          </>
        )}
      </Panel>
      {data && (
        <LineChartCard
          title="Depot und gewählter Vergleich"
          caption={`${data.start} bis ${data.end} · ${data.currency} · gleicher Basiswert 100`}
          points={data.points}
          series={[
            { key: "portfolio_index", label: "Depot", color: "#0f766e" },
            { key: "benchmark_index", label: data.benchmark, color: "#a855f7" },
          ]}
          isLoading={query.isLoading}
          error={query.error}
        />
      )}
    </div>
  );
}
