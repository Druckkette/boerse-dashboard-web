"use client";

import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api/client";
import { useJob } from "@/lib/use-job";
import { LineChartCard } from "@/components/ui/line-chart-card";
import { formatNumber } from "@/lib/format";
import { patternLabels, patternStatuses } from "@/lib/types/chart-analysis";
import type { ChartPattern, PatternConfig } from "@/lib/types/chart-analysis";

const panel = "rounded-2xl border border-[#e3e8ef] bg-white p-4 sm:p-6";
const control =
  "min-h-11 rounded-lg border border-[#cbd5e1] bg-white px-3 py-2 text-sm text-[#172033]";
const button =
  "min-h-11 rounded-lg bg-[#0f766e] px-4 py-2 text-sm font-semibold text-white disabled:opacity-50";
const dateText = (day: string) =>
  new Date(`${day}T12:00:00`).toLocaleDateString("de-DE");
const errorText = (error: Error | null) =>
  error?.message || "Daten konnten nicht geladen werden.";

function StockEntry() {
  const [input, setInput] = useState("");
  const [error, setError] = useState("");
  const router = useRouter();
  return (
    <form
      className="flex flex-wrap gap-2"
      onSubmit={(e) => {
        e.preventDefault();
        const ticker = input.trim().toUpperCase();
        if (!/^[A-Z0-9][A-Z0-9.=_^-]{0,31}$/.test(ticker)) {
          setError(
            "Bitte einen gültigen Börsenticker eingeben, zum Beispiel AAPL oder SAP.DE.",
          );
          return;
        }
        setError("");
        router.push(`/chart-analysis/${encodeURIComponent(ticker)}?refresh=1`);
      }}
    >
      <label className="sr-only" htmlFor="chart-ticker">
        Aktie im Chart öffnen
      </label>
      <input
        id="chart-ticker"
        autoComplete="off"
        className={`${control} min-w-0 flex-1`}
        placeholder="Ticker, z. B. AAPL oder SAP.DE"
        value={input}
        onChange={(e) => setInput(e.target.value)}
      />
      <button className={button}>Chart öffnen</button>
      {error && (
        <p role="alert" className="w-full text-sm text-red-700">
          {error}
        </p>
      )}
    </form>
  );
}

export function ChartAnalysisOverview() {
  const [kind, setKind] = useState("");
  const [status, setStatus] = useState("");
  const [search, setSearch] = useState("");
  const [offset, setOffset] = useState(0);
  const [jobId, setJobId] = useState<string | null>(null);
  const queryClient = useQueryClient();
  const config = useQuery({
    queryKey: ["chart-pattern-config"],
    queryFn: api.chartPatternConfig,
  });
  const results = useQuery({
    queryKey: ["chart-pattern-results", kind, status, search, offset],
    queryFn: () =>
      api.chartPatternResults(
        new URLSearchParams({
          ...(kind ? { kind } : {}),
          ...(status ? { status } : {}),
          search,
          offset: String(offset),
        }).toString(),
      ),
  });
  const job = useJob(jobId, ["chart-pattern-results"]);
  const scan = useMutation({
    mutationFn: () => api.startJob({ type: "scan_chart_patterns" }),
    onSuccess: (result) => setJobId(result.job_id),
  });
  return (
    <div className="space-y-4">
      <section className={panel}>
        <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-xs font-semibold uppercase tracking-widest text-[#0f766e]">
              Kapitel 4.2 · Basismuster
            </p>
            <h1 className="mt-1 text-2xl font-semibold">Chartanalyse</h1>
            <p className="mt-2 max-w-3xl text-sm text-slate-600">
              Fünf Basismuster im Aktienuniversum erkennen und direkt im Chart
              prüfen. Jeder Treffer zeigt, ab wann seine Kriterien erfüllt
              waren.
            </p>
          </div>
          <button
            className={button}
            disabled={scan.isPending || job.running}
            onClick={() => scan.mutate()}
          >
            Universum nach Mustern scannen
          </button>
        </div>
        <StockEntry />
        {job.running && (
          <p role="status" className="mt-3 text-sm">
            Scan läuft: {job.data?.current_step || "Job wird vorbereitet…"}
          </p>
        )}
        {(scan.isError ||
          job.data?.status === "failed" ||
          job.data?.status === "cancelled") && (
          <p role="alert" className="mt-3 text-sm text-red-700">
            {scan.error?.message ||
              job.data?.error_message ||
              "Scan wurde abgebrochen. Vorherige Ergebnisse bleiben erhalten."}
          </p>
        )}
      </section>
      {config.data && (
        <ParameterEditor
          key={config.data.parameter_hash}
          config={config.data}
          onSaved={async () => {
            await queryClient.invalidateQueries({
              queryKey: ["chart-pattern-config"],
            });
            await queryClient.invalidateQueries({
              queryKey: ["chart-pattern-results"],
            });
          }}
        />
      )}
      {config.isError && (
        <p role="alert" className={panel}>
          {errorText(config.error)}
        </p>
      )}
      <section className={panel}>
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold">Erkannte Muster</h2>
            <p className="mt-1 text-sm text-slate-600">
              {results.data?.available
                ? `${results.data.analysed_count} von ${results.data.scanned_count} Aktien geprüft · ${results.data.skipped_count} mit unzureichenden Daten · Scan vom ${new Date(results.data.generated_at!).toLocaleString("de-DE")}`
                : "Den ersten Scan starten, um das gespeicherte Aktienuniversum zu prüfen."}
            </p>
          </div>
        </div>
        {results.data?.obsolete && (
          <p
            role="status"
            className="mt-4 rounded-lg bg-amber-50 p-3 text-sm text-amber-900"
          >
            Die Parameter wurden geändert. Diese Treffer verwenden noch die
            vorherigen Regeln. Bitte einen neuen Scan starten.
          </p>
        )}
        <div className="my-4 grid gap-2 sm:grid-cols-3">
          <input
            aria-label="Treffer nach Aktie filtern"
            className={control}
            value={search}
            placeholder="Ticker oder Aktienname filtern"
            onChange={(e) => {
              setSearch(e.target.value);
              setOffset(0);
            }}
          />
          <select
            aria-label="Muster filtern"
            className={control}
            value={kind}
            onChange={(e) => {
              setKind(e.target.value);
              setOffset(0);
            }}
          >
            <option value="">Alle Basismuster</option>
            {Object.entries(patternLabels).map(([key, label]) => (
              <option key={key} value={key}>
                {label}
              </option>
            ))}
          </select>
          <select
            aria-label="Musterstatus filtern"
            className={control}
            value={status}
            onChange={(e) => {
              setStatus(e.target.value);
              setOffset(0);
            }}
          >
            <option value="">Alle Zustände</option>
            {Object.entries(patternStatuses).map(([key, label]) => (
              <option key={key} value={key}>
                {label}
              </option>
            ))}
          </select>
        </div>
        {results.isLoading && <p role="status">Ergebnisse werden geladen…</p>}
        {results.isError && (
          <p role="alert" className="text-sm text-red-700">
            {errorText(results.error)}
          </p>
        )}
        {results.data && (
          <>
            <p className="mb-2 text-sm text-slate-500">
              {results.data.total} Treffer
            </p>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[780px] text-left text-sm">
                <thead className="border-b text-xs text-slate-500">
                  <tr>
                    {[
                      "Aktie / Muster",
                      "Basis seit",
                      "Erkannt am",
                      "Ausbruch am",
                      "Tiefe",
                      "Pivot",
                      "Zustand",
                    ].map((label) => (
                      <th key={label} className="p-3">
                        {label}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {results.data.rows.map((row) => (
                    <tr key={row.id} className="border-b border-slate-100">
                      <td className="p-3">
                        <Link
                          className="font-semibold text-[#0f766e] hover:underline"
                          href={`/chart-analysis/${encodeURIComponent(row.ticker)}?pattern=${encodeURIComponent(row.id)}&rules=${row.parameter_hash}`}
                        >
                          {row.ticker} · {row.label}
                        </Link>
                        <p className="text-xs text-slate-500">{row.name}</p>
                      </td>
                      <td className="p-3">{dateText(row.start_date)}</td>
                      <td className="p-3">{dateText(row.detected_on)}</td>
                      <td className="p-3">
                        {row.breakout_on ? dateText(row.breakout_on) : "–"}
                      </td>
                      <td className="p-3 tabular-nums">
                        {formatNumber(row.depth_pct, 1)} %
                      </td>
                      <td className="p-3 tabular-nums">
                        {formatNumber(row.pivot, 2)}
                      </td>
                      <td className="p-3">
                        {patternStatuses[row.status]}
                        {row.stale && (
                          <p className="text-xs text-amber-800">
                            Kurse veraltet · {row.price_as_of}
                          </p>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {results.data.available && results.data.total === 0 && (
              <p className="py-6 text-sm text-slate-600">
                Keine Muster für diese Auswahl erkannt.
              </p>
            )}
            <div className="mt-4 flex items-center justify-between gap-2">
              <button
                className={control}
                disabled={!offset}
                onClick={() => setOffset(Math.max(0, offset - 100))}
              >
                Zurück
              </button>
              <span className="text-sm">
                {results.data.total
                  ? `${offset + 1}–${Math.min(offset + 100, results.data.total)}`
                  : "0"}{" "}
                / {results.data.total}
              </span>
              <button
                className={control}
                disabled={offset + 100 >= results.data.total}
                onClick={() => setOffset(offset + 100)}
              >
                Weiter
              </button>
            </div>
            {!!results.data.skipped?.length && (
              <details className="mt-4 text-sm">
                <summary className="cursor-pointer">
                  Datenlücken ansehen ({results.data.skipped_count})
                </summary>
                <ul className="mt-2 max-h-60 space-y-1 overflow-y-auto">
                  {results.data.skipped.map((row) => (
                    <li key={row.ticker}>
                      {row.ticker}: {row.reason}
                    </li>
                  ))}
                </ul>
              </details>
            )}
          </>
        )}
      </section>
    </div>
  );
}

const parameterLabels: Record<string, string> = {
  cup_min_weeks: "Cup: Mindestdauer (Wochen)",
  base_max_weeks: "Basis: Höchstdauer (Wochen)",
  cup_min_depth_pct: "Cup: Mindesttiefe (%)",
  cup_max_depth_pct: "Cup: Maximale Tiefe (%)",
  cup_min_floor_fraction: "Cup: Mindestanteil am runden Boden (0–1)",
  cup_max_shape_error: "Cup: Maximaler Formfehler (0–1)",
  rim_tolerance_pct: "Cup: Maximaler Abstand des rechten Rands (%)",
  handle_min_days: "Handle: Mindestdauer (Handelstage)",
  handle_max_days: "Handle: Höchstdauer (Handelstage)",
  handle_min_depth_pct: "Handle: Mindesttiefe (%)",
  handle_max_depth_pct: "Handle: Maximale Tiefe (%)",
  double_bottom_min_weeks: "Double Bottom: Mindestdauer (Wochen)",
  double_bottom_max_depth_pct: "Double Bottom: Maximale Tiefe (%)",
  double_bottom_max_undercut_pct: "Double Bottom: Maximaler Unterschuss (%)",
  flag_min_gain_pct: "Flaggenmast: Mindestanstieg (%)",
  flag_max_gain_pct: "Flaggenmast: Maximaler Anstieg (%)",
  flag_min_depth_pct: "Flagge: Mindesttiefe (%)",
  flag_max_depth_pct: "Flagge: Maximale Tiefe (%)",
  box_min_weeks: "Box: Mindestdauer (Wochen)",
  box_max_depth_pct: "Box: Maximale Tiefe (%)",
  volume_dry_up_ratio: "Volumen: Maximaler Anteil zum Vergleichsvolumen",
  flag_volume_ratio: "Flagge: Maximaler Volumenanteil",
  breakout_volume_ratio: "Ausbruch: Mindestvolumen / 50-Tage-Mittel",
};

function ParameterEditor({
  config,
  onSaved,
}: {
  config: PatternConfig;
  onSaved: () => Promise<void>;
}) {
  const [draft, setDraft] = useState(config.parameters);
  const save = useMutation({
    mutationFn: () => api.saveChartPatternConfig(draft),
    onSuccess: onSaved,
  });
  return (
    <details className={panel}>
      <summary className="cursor-pointer font-semibold">
        Musterparameter anpassen
      </summary>
      <p className="my-3 text-sm text-slate-600">
        Die Einstellungen gelten für Chart und Universumscan und werden zentral
        gespeichert. Nach Änderungen den Scan erneut starten. Standardwerte
        folgen Kapitel 4.2; Form- und Volumenfilter konkretisieren die
        qualitativen Regeln.
      </p>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate();
        }}
      >
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {Object.entries(draft)
            .filter(([key]) => key !== "require_volume")
            .map(([key, value]) => (
              <label key={key} className="grid gap-1 text-sm">
                {parameterLabels[key] || key}
                <input
                  required
                  type="number"
                  step={
                    key.endsWith("weeks") || key.endsWith("days") ? "1" : "0.01"
                  }
                  className={control}
                  value={
                    typeof value === "number" && !Number.isFinite(value)
                      ? ""
                      : String(value)
                  }
                  onChange={(e) =>
                    setDraft({
                      ...draft,
                      [key]:
                        e.target.value === ""
                          ? Number.NaN
                          : Number(e.target.value),
                    })
                  }
                />
              </label>
            ))}
        </div>
        <label className="my-4 flex gap-2 text-sm">
          <input
            type="checkbox"
            checked={draft.require_volume}
            onChange={(e) =>
              setDraft({ ...draft, require_volume: e.target.checked })
            }
          />
          Austrocknendes Volumen als Pflichtkriterium
        </label>
        <div className="flex flex-wrap gap-2">
          <button
            className={button}
            disabled={
              save.isPending ||
              Object.values(draft).some(
                (v) => typeof v === "number" && !Number.isFinite(v),
              )
            }
          >
            Parameter speichern
          </button>
          <button
            type="button"
            className={control}
            onClick={() => setDraft(config.defaults)}
          >
            Buchstandard als Entwurf laden
          </button>
        </div>
        {save.isError && (
          <p role="alert" className="mt-3 text-sm text-red-700">
            {errorText(save.error)}
          </p>
        )}
      </form>
    </details>
  );
}

export function ChartAnalysisDetail({
  ticker,
  patternId,
  rules,
  autoRefresh = false,
}: {
  ticker: string;
  patternId?: string;
  rules?: string;
  autoRefresh?: boolean;
}) {
  const queryClient = useQueryClient();
  const config = useQuery({
    queryKey: ["chart-pattern-config"],
    queryFn: api.chartPatternConfig,
  });
  const [selectedId, setSelectedId] = useState(patternId || "");
  const [showPattern, setShowPattern] = useState(true);
  const [asOf, setAsOf] = useState("");
  const [jobId, setJobId] = useState<string | null>(null);
  const chart = useQuery({
    queryKey: ["chart-pattern-chart", ticker, asOf],
    queryFn: () => api.chartPatternChart(ticker, asOf),
  });
  const job = useJob(jobId, ["chart-pattern-chart"]);
  const refresh = useMutation({
    mutationFn: () =>
      api.startJob({
        type: "refresh_stock_detail",
        payload: { tickers: [ticker] },
      }),
    onSuccess: (result) => setJobId(result.job_id),
  });
  const automaticRequested = useRef(false);
  const requestRefresh = refresh.mutate;
  useEffect(() => {
    if (
      autoRefresh &&
      !asOf &&
      chart.data &&
      (!chart.data.points.length || chart.data.stale) &&
      !automaticRequested.current
    ) {
      automaticRequested.current = true;
      requestRefresh();
    }
  }, [autoRefresh, asOf, chart.data, requestRefresh]);
  const patterns = chart.data?.patterns || [];
  const selected = selectedId
    ? patterns.find((p) => p.id === selectedId)
    : patterns[0];
  // Show the complete selected pattern with context; pan/zoom remain available in the chart.
  const start = selected?.points[0]?.date;
  const startIndex =
    chart.data?.points.findIndex((p) => p.date === start) ?? -1;
  const points =
    chart.data?.points.slice(startIndex > 20 ? startIndex - 20 : 0) || [];
  return (
    <div className="space-y-4">
      <section className={panel}>
        <Link
          href="/chart-analysis"
          className="text-sm font-semibold text-[#0f766e]"
        >
          ← Alle Basismuster
        </Link>
        <h1 className="my-3 text-2xl font-semibold">Chartanalyse · {ticker}</h1>
        <StockEntry />
        <div className="mt-4 flex flex-wrap items-end gap-3">
          <label className="grid gap-1 text-sm">
            Historischer Prüfzeitpunkt
            <input
              type="date"
              className={control}
              value={asOf}
              onChange={(e) => setAsOf(e.target.value)}
            />
          </label>
          <button className={control} onClick={() => setAsOf("")}>
            Aktueller Stand
          </button>
          <button
            className={control}
            disabled={refresh.isPending || job.running}
            onClick={() => refresh.mutate()}
          >
            Kursdaten aktualisieren
          </button>
        </div>
        {job.running && (
          <p role="status" className="mt-2 text-sm">
            Kurse werden im Hintergrund aktualisiert…
          </p>
        )}
        {(refresh.isError || job.data?.status === "failed") && (
          <p role="alert" className="mt-2 text-sm text-red-700">
            {refresh.error?.message ||
              job.data?.error_message ||
              "Aktualisierung fehlgeschlagen."}
          </p>
        )}
        {chart.data && (
          <p className="mt-3 text-sm text-slate-500">
            Kursstand:{" "}
            {chart.data.price_as_of
              ? dateText(chart.data.price_as_of)
              : "Keine Kurse vorhanden"}{" "}
            · Geprüft bis: {dateText(chart.data.as_of)}
          </p>
        )}
        {chart.data?.stale && (
          <p role="status" className="mt-2 text-sm text-amber-800">
            Die gespeicherten Kurse sind veraltet. Für eine aktuelle Prüfung
            bitte aktualisieren.
          </p>
        )}
        {rules && chart.data && rules !== chart.data.parameter_hash && (
          <p role="status" className="mt-2 text-sm text-amber-800">
            Der Listentreffer verwendete andere Parameter. Der Chart wurde mit
            den aktuell gespeicherten Regeln neu geprüft.
          </p>
        )}
        {selectedId && chart.data && !selected && (
          <p role="status" className="mt-2 text-sm text-amber-800">
            Der ausgewählte Treffer ist mit diesem Datenstand und diesen
            Parametern nicht mehr vorhanden. Bitte ein anderes Muster auswählen
            oder den Scan erneuern.
          </p>
        )}
        {chart.data?.diagnostics.map((problem) => (
          <p
            key={problem}
            role="status"
            className="mt-2 text-sm text-amber-800"
          >
            {problem}
          </p>
        ))}
      </section>
      {config.data && (
        <ParameterEditor
          key={config.data.parameter_hash}
          config={config.data}
          onSaved={async () => {
            await Promise.all([
              queryClient.invalidateQueries({
                queryKey: ["chart-pattern-config"],
              }),
              queryClient.invalidateQueries({
                queryKey: ["chart-pattern-chart"],
              }),
              queryClient.invalidateQueries({
                queryKey: ["chart-pattern-results"],
              }),
            ]);
          }}
        />
      )}
      <section className={panel}>
        <div className="mb-4 flex flex-wrap items-center gap-3">
          <label className="grid gap-1 text-sm">
            Muster im Chart
            <select
              aria-label="Muster im Chart"
              className={`${control} max-w-full`}
              value={selected?.id || ""}
              onChange={(e) => setSelectedId(e.target.value)}
            >
              <option value="" disabled>
                Kein Basismuster erkannt
              </option>
              {patterns.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.label} · {dateText(p.detected_on)}
                </option>
              ))}
            </select>
          </label>
          <label className="flex gap-2 text-sm">
            <input
              type="checkbox"
              checked={showPattern}
              onChange={(e) => setShowPattern(e.target.checked)}
            />
            Muster einzeichnen
          </label>
        </div>
        <LineChartCard
          key={`${ticker}:${selected?.id || "none"}:${asOf}`}
          title={`${ticker} · Tageschart`}
          storageKey={`pattern-${ticker}`}
          caption="Tageskerzen und Volumen · Markierte Eckpunkte zeigen die erkannte Formation."
          points={points}
          series={[{ key: "close", label: "Schlusskurs", color: "#0f766e" }]}
          chartMode="candlestick"
          volumeKey="volume"
          isLoading={chart.isLoading}
          error={chart.error}
          overlays={
            selected && showPattern
              ? [
                  {
                    key: selected.id,
                    label: selected.label,
                    color: "#7c3aed",
                    cup: selected.kind.startsWith("cup_"),
                    points: selected.points,
                  },
                ]
              : []
          }
          levels={
            selected && showPattern
              ? [
                  {
                    key: "pivot",
                    label: "Pivot",
                    value: selected.pivot,
                    color: "#7c3aed",
                  },
                ]
              : []
          }
          markers={
            selected && showPattern
              ? [
                  {
                    key: "detected",
                    date: selected.detected_on,
                    label: "Basismuster erstmals erkannt",
                    code: "Basis",
                    color: "#7c3aed",
                  },
                  ...(selected.breakout_on
                    ? [
                        {
                          key: "breakout",
                          date: selected.breakout_on,
                          label: patternStatuses[selected.status],
                          code: "Ausb",
                          color: "#0f766e",
                        },
                      ]
                    : []),
                ]
              : []
          }
        />
        {!chart.isLoading &&
          !chart.isError &&
          !selected &&
          patterns.length === 0 && (
            <p className="mt-3 text-sm text-slate-600">
              Kein Basismuster erfüllt die eingestellten Regeln. Der Kurschart
              ist auch ohne Treffer verfügbar.
            </p>
          )}
        {selected && <PatternDetails pattern={selected} />}
      </section>
    </div>
  );
}

function PatternDetails({ pattern: p }: { pattern: ChartPattern }) {
  return (
    <div className="mt-5 border-t pt-4">
      <h2 className="text-lg font-semibold">
        {p.label} · {patternStatuses[p.status]}
      </h2>
      <dl className="my-4 grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
        {[
          ["Erkannt am", dateText(p.detected_on)],
          ["Basis seit", dateText(p.start_date)],
          ["Tiefe", `${formatNumber(p.depth_pct, 1)} %`],
          ["Pivot", formatNumber(p.pivot, 2)],
          ["Dauer", `${p.duration_days} Kalendertage`],
          [
            "Volumenverhältnis",
            p.volume_ratio === null
              ? "Nicht verfügbar"
              : `${formatNumber(p.volume_ratio, 2)}×`,
          ],
          ["Ausbruch", p.breakout_on ? dateText(p.breakout_on) : "Noch keiner"],
          [
            "Ausbruchsvolumen",
            p.breakout_volume_ratio === null
              ? "Nicht verfügbar"
              : `${formatNumber(p.breakout_volume_ratio, 2)}×`,
          ],
        ].map(([label, value]) => (
          <div key={label}>
            <dt className="text-slate-500">{label}</dt>
            <dd className="mt-1 font-medium">{value}</dd>
          </div>
        ))}
      </dl>
      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <h3 className="text-sm font-semibold text-[#0f766e]">
            Erfüllte Regeln
          </h3>
          <ul className="mt-2 space-y-1 text-sm">
            {p.checks.map((check) => (
              <li key={check}>✓ {check}</li>
            ))}
          </ul>
        </div>
        <div>
          <h3 className="text-sm font-semibold text-amber-800">
            Qualitative Prüfung
          </h3>
          <ul className="mt-2 space-y-1 text-sm text-slate-600">
            {p.warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        </div>
      </div>
      <p className="mt-4 text-xs text-slate-500">
        Regelbasierte Mustererkennung nach Kapitel 4.2. Die Erkennung beschreibt
        die Chartstruktur; ein späterer Kurserfolg wird damit nicht gemessen.
      </p>
    </div>
  );
}
