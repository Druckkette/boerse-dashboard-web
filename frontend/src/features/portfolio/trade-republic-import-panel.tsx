"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, FileText, Save } from "lucide-react";
import { useRef, useState, type DragEvent } from "react";
import { StatusChip } from "@/components/ui/status-chip";
import { api } from "@/lib/api/client";
import type {
  PortfolioImportRow,
  TradeRepublicTransactionImportRequest,
  TradeRepublicTransactionImportResponse,
} from "@/lib/types/api";

const sourceLabels: Record<string, string> = {
  automatic: "Automatisch gefunden",
  manual: "Eigene Zuordnung",
  saved: "Gespeichert",
  static: "Bekannte ISIN",
  missing: "Zuordnung offen",
};
const buttonClass =
  "inline-flex min-h-11 items-center justify-center gap-2 rounded border border-[var(--border)] px-4 py-3 text-sm disabled:cursor-not-allowed disabled:opacity-50";

export function TradeRepublicTransactionImportPanel() {
  const client = useQueryClient();
  const [fileName, setFileName] = useState("");
  const [content, setContent] = useState("");
  const [replace, setReplace] = useState(true);
  const [dragActive, setDragActive] = useState(false);
  const [reading, setReading] = useState(false);
  const [fileError, setFileError] = useState("");
  const [overrides, setOverrides] = useState<Record<string, string>>({});
  const [edited, setEdited] = useState(false);
  const [showRecognized, setShowRecognized] = useState(false);
  const [result, setResult] =
    useState<TradeRepublicTransactionImportResponse | null>(null);
  const fileVersion = useRef(0);
  const preview = useMutation({
    mutationFn: (payload: TradeRepublicTransactionImportRequest) =>
      api.importTradeRepublicTransactions(payload),
    onSuccess: (next) => {
      setResult(next);
      setEdited(false);
    },
  });
  const save = useMutation({
    mutationFn: (payload: TradeRepublicTransactionImportRequest) =>
      api.importTradeRepublicTransactions(payload),
    onSuccess: (next) => {
      setResult(next);
      if (next.ok) invalidatePortfolio(client);
    },
  });
  const busy = reading || preview.isPending || save.isPending;
  function payload(
    dry_run: boolean,
    nextContent = content,
    nextName = fileName,
    nextOverrides = overrides,
  ): TradeRepublicTransactionImportRequest {
    return {
      content: nextContent,
      file_name: nextName || "trade-republic-transactions.csv",
      dry_run,
      replace_open_positions: replace,
      isin_overrides: nextOverrides,
    };
  }
  async function handleFile(file: File | null) {
    if (!file || busy) return;
    const version = ++fileVersion.current;
    setReading(true);
    setFileError("");
    setResult(null);
    setOverrides({});
    setEdited(false);
    setShowRecognized(false);
    preview.reset();
    save.reset();
    try {
      const text = await file.text();
      if (version !== fileVersion.current) return;
      setFileName(file.name);
      setContent(text);
      preview.mutate(payload(true, text, file.name, {}));
    } catch {
      setContent("");
      setFileError(
        "Datei konnte nicht gelesen werden. Bitte erneut auswählen.",
      );
    } finally {
      setReading(false);
    }
  }
  function handleDrop(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    setDragActive(false);
    void handleFile(event.dataTransfer.files?.[0] ?? null);
  }
  const missing =
    result?.mappings.filter(
      (row) => !(overrides[row.isin] ?? row.ticker).trim(),
    ).length ?? 0;
  const canSave =
    result?.ok &&
    result.dry_run &&
    result.transactions_total > 0 &&
    !edited &&
    !(replace && missing > 0);
  const error = preview.error ?? save.error;
  return (
    <section
      aria-label="Trade-Republic-Import"
      aria-busy={busy}
      className="min-w-0 space-y-5 rounded border border-[var(--border)] bg-[var(--panel)] p-3 sm:p-5"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1 basis-60">
          <h2 className="text-lg font-semibold">
            Trade-Republic-Transaktionsexport
          </h2>
          <p className="mt-1 text-sm leading-6 text-[var(--muted)]">
            Datei auswählen, automatisch erkannte Wertpapiere prüfen und den
            Import speichern.
          </p>
        </div>
        <StatusChip tone={result?.ok ? "good" : result ? "bad" : "neutral"}>
          {save.isPending
            ? "Speichert …"
            : busy
              ? "Wird geprüft …"
              : result?.ok
                ? result.dry_run
                  ? "Vorschau bereit"
                  : "Importiert"
                : result
                  ? "Fehler"
                  : "Datei auswählen"}
        </StatusChip>
      </div>
      <ol
        aria-label="Importschritte"
        className="grid grid-cols-3 gap-2 text-xs sm:text-sm"
      >
        {["Datei wählen", "Vorschau prüfen", "Speichern"].map((step, index) => (
          <li
            key={step}
            aria-current={
              (result?.ok && !result.dry_run ? 2 : result ? 1 : 0) === index
                ? "step"
                : undefined
            }
            className="min-w-0 rounded border border-[var(--border)] p-2 aria-[current=step]:border-emerald-500 aria-[current=step]:bg-[var(--green-soft)]"
          >
            <span className="mr-1 font-semibold">{index + 1}.</span>
            {step}
          </li>
        ))}
      </ol>
      <label
        onDragOver={(event) => {
          event.preventDefault();
          if (!busy) setDragActive(true);
        }}
        onDragLeave={() => setDragActive(false)}
        onDrop={handleDrop}
        className={`block min-w-0 cursor-pointer rounded border border-dashed p-5 text-center text-sm ${dragActive ? "border-emerald-500" : "border-[var(--border)]"} ${busy ? "opacity-60" : ""}`}
      >
        <input
          aria-label="TR-CSV auswählen"
          accept=".csv,text/csv,text/plain"
          className="sr-only"
          type="file"
          disabled={busy}
          onChange={(event) => {
            void handleFile(event.target.files?.[0] ?? null);
            event.target.value = "";
          }}
        />
        <FileText className="mx-auto mb-2 text-[var(--muted)]" />
        <span className="font-semibold">TR-CSV auswählen</span>
        <span className="mt-1 block break-all text-xs text-[var(--muted)]">
          {fileName ||
            "Antippen oder Datei hier ablegen. Die Prüfung startet automatisch."}
        </span>
      </label>
      <details className="min-w-0 rounded border border-[var(--border)] p-3">
        <summary className="cursor-pointer text-sm">
          CSV einfügen und Importoptionen
        </summary>
        <label className="mt-3 block text-sm">
          CSV-Inhalt
          <textarea
            className="input-dark mt-1 min-h-32 w-full font-mono text-base sm:text-xs"
            value={content}
            disabled={busy}
            onChange={(event) => {
              setFileError("");
              setContent(event.target.value);
              setResult(null);
              setOverrides({});
              preview.reset();
              save.reset();
            }}
          />
        </label>
        <label className="mt-3 flex items-start gap-3 text-sm">
          <input
            className="mt-1 size-4 shrink-0"
            type="checkbox"
            checked={replace}
            disabled={busy}
            onChange={(event) => {
              setReplace(event.target.checked);
              setEdited(true);
            }}
          />
          <span>
            Depotbestand synchronisieren
            <span className="mt-1 block text-xs text-[var(--muted)]">
              Bereits verkaufte Positionen werden geschlossen. Deaktiviert:
              bestehende offene Positionen bleiben erhalten.
            </span>
          </span>
        </label>
      </details>
      {(fileError || error) && (
        <p
          role="alert"
          className="break-words rounded bg-[var(--red-soft)] p-3 text-sm text-[var(--red)]"
        >
          {fileError ||
            (error instanceof Error ? error.message : "Import fehlgeschlagen.")}
        </p>
      )}
      <div
        role="status"
        aria-live="polite"
        className="text-sm text-[var(--muted)]"
      >
        {busy
          ? "CSV wird geprüft und unbekannte ISINs werden automatisch gesucht …"
          : result && !result.dry_run && result.ok
            ? "Import gespeichert. Hinweise zur Aktualisierung der Kurshistorie stehen unten."
            : edited
              ? "Zuordnungen oder Optionen geändert. Bitte Vorschau erneut prüfen."
              : result
                ? "Vorschau prüfen und anschließend speichern."
                : "Die Vorschau verändert dein Depot noch nicht."}
      </div>
      {result && (
        <div className="min-w-0 space-y-4">
          <div className="grid gap-2 sm:grid-cols-3">
            <MiniStat label="Buchungen" value={String(result.rows_total)} />
            <MiniStat
              label="Offene Positionen"
              value={String(result.positions.length)}
            />
            <MiniStat
              label="Cash-Schätzung"
              value={result.cash_balance_estimate.toLocaleString("de-DE", {
                style: "currency",
                currency: "EUR",
              })}
            />
          </div>
          {result.errors.map((message) => (
            <p
              role="alert"
              key={message}
              className="break-words rounded bg-[var(--red-soft)] p-3 text-sm text-[var(--red)]"
            >
              {message}
            </p>
          ))}
          {result.mappings.length > 0 && (
            <div className="space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h3 className="font-semibold">Wertpapiere zuordnen</h3>
                <StatusChip tone={missing ? "warning" : "good"}>
                  {missing ? `${missing} Zuordnungen offen` : "Alle zugeordnet"}
                </StatusChip>
              </div>
              <p className="text-sm text-[var(--muted)]">
                Eindeutige ISIN-Treffer werden automatisch übernommen und beim
                Speichern für künftige Importe hinterlegt.
              </p>
              {result.mappings.some((row) => row.ticker) && (
                <button
                  type="button"
                  className="min-h-11 text-sm text-[var(--teal)] underline"
                  onClick={() => setShowRecognized(!showRecognized)}
                >
                  {showRecognized
                    ? "Erkannte Zuordnungen ausblenden"
                    : `Erkannte Zuordnungen anzeigen (${result.mappings.filter((row) => row.ticker).length})`}
                </button>
              )}
              {[...result.mappings]
                .filter((row) => showRecognized || !row.ticker)
                .sort(
                  (a, b) =>
                    Number(Boolean(a.ticker)) - Number(Boolean(b.ticker)),
                )
                .map((row) => (
                  <div
                    key={row.isin}
                    className="grid min-w-0 gap-3 rounded border border-[var(--border)] p-3 sm:grid-cols-[minmax(0,1fr)_minmax(0,12rem)]"
                  >
                    <div className="min-w-0">
                      <div className="break-words font-medium">
                        {row.name || row.isin}
                      </div>
                      <div className="mt-1 break-all font-mono text-xs text-[var(--muted)]">
                        {row.isin}
                      </div>
                      <div className="mt-1 text-xs text-[var(--muted)]">
                        {overrides[row.isin] !== undefined
                          ? "Eigene Zuordnung"
                          : sourceLabels[row.source]}
                      </div>
                      {row.message && (
                        <p className="mt-1 text-xs text-[var(--muted)]">
                          {row.message}
                        </p>
                      )}
                    </div>
                    <label className="min-w-0 text-sm">
                      <span className="mb-1 block text-[var(--muted)]">
                        Ticker für {row.name || row.isin}
                      </span>
                      <input
                        aria-label={`Ticker für ${row.isin}`}
                        className="input-dark min-h-11 min-w-0 text-base sm:text-sm"
                        value={overrides[row.isin] ?? row.ticker}
                        disabled={busy || !result.dry_run}
                        placeholder="Yahoo-Ticker"
                        autoCapitalize="characters"
                        autoCorrect="off"
                        spellCheck={false}
                        onChange={(event) => {
                          setOverrides({
                            ...overrides,
                            [row.isin]: event.target.value.toUpperCase().trim(),
                          });
                          setEdited(true);
                        }}
                      />
                      {!row.ticker && Boolean(row.candidates?.length) && (
                        <select
                          aria-label={`Börsenplatz für ${row.isin}`}
                          className="input-dark mt-2 min-h-11 min-w-0 text-base sm:text-sm"
                          disabled={busy || !result.dry_run}
                          value={overrides[row.isin] || ""}
                          onChange={(event) => {
                            setOverrides({
                              ...overrides,
                              [row.isin]: event.target.value,
                            });
                            setEdited(true);
                          }}
                        >
                          <option value="">Börsenplatz auswählen</option>
                          {row.candidates?.map((candidate) => (
                            <option
                              key={candidate.ticker}
                              value={candidate.ticker}
                            >
                              {candidate.ticker} · {candidate.exchange} ·{" "}
                              {candidate.name}
                            </option>
                          ))}
                        </select>
                      )}
                    </label>
                  </div>
                ))}
            </div>
          )}
          {result.positions.length > 0 && (
            <details className="min-w-0 rounded border border-[var(--border)] p-3">
              <summary className="cursor-pointer text-sm font-semibold">
                {result.positions.length} offene Positionen ansehen
              </summary>
              <div className="mt-3">
                <ImportPreviewTable rows={result.positions} />
              </div>
            </details>
          )}
          {result.skipped_positions.length > 0 && (
            <details className="min-w-0 rounded border border-[var(--border)] p-3">
              <summary className="cursor-pointer text-sm">
                {result.skipped_positions.length} Positionen außerhalb der
                Aktien-/Fondsübersicht
              </summary>
              <p className="mt-2 text-xs text-[var(--muted)]">
                Alle Buchungen werden gespeichert. Derivate werden für die
                Depotkurve separat über ihre ISIN bewertet.
              </p>
              <ul className="mt-2 space-y-2 text-xs">
                {result.skipped_positions.map((row) => (
                  <li className="break-words" key={row.isin}>
                    {row.name} · {row.isin}: {row.reason}
                  </li>
                ))}
              </ul>
            </details>
          )}
          {result.warnings.length > 0 && (
            <details className="min-w-0 rounded border border-amber-300/40 p-3">
              <summary className="cursor-pointer text-sm">
                {result.warnings.length} Hinweise zum Import
              </summary>
              <ul className="mt-2 space-y-2 text-sm text-[var(--muted)]">
                {result.warnings.map((message) => (
                  <li className="break-words" key={message}>
                    {message}
                  </li>
                ))}
              </ul>
            </details>
          )}
        </div>
      )}
      <div className="space-y-3 border-t border-[var(--border)] pt-4">
        {result?.dry_run && missing > 0 && (
          <p className="text-sm text-[var(--yellow)]">
            {replace
              ? "Zum Synchronisieren bitte die offenen Zuordnungen ergänzen und erneut prüfen."
              : "Offene Positionen ohne Zuordnung werden in der Positionsübersicht übersprungen. Alle Buchungen bleiben erhalten."}
          </p>
        )}
        <div className="grid gap-3 sm:grid-cols-2">
          <button
            className={buttonClass}
            disabled={busy || !content.trim()}
            onClick={() => {
              save.reset();
              preview.mutate(payload(true));
            }}
            type="button"
          >
            <CheckCircle2 size={16} />
            {preview.isPending ? "Prüft …" : "Vorschau erneut prüfen"}
          </button>
          <button
            className={`${buttonClass} border-emerald-300/40 bg-[var(--green-soft)] text-[var(--green)]`}
            disabled={busy || !canSave}
            type="button"
            onClick={() =>
              save.mutate(
                payload(false, content, fileName, {
                  ...Object.fromEntries(
                    result?.mappings
                      .filter((row) => row.ticker)
                      .map((row) => [row.isin, row.ticker]) ?? [],
                  ),
                  ...overrides,
                }),
              )
            }
          >
            <Save size={16} />
            {save.isPending ? "Speichert …" : "TR-Import speichern"}
          </button>
        </div>
      </div>
    </section>
  );
}

export function IsinMappingMaintenancePanel() {
  const client = useQueryClient();
  const query = useQuery({
    queryKey: ["isin-mappings"],
    queryFn: api.isinMappings,
    staleTime: 60_000,
  });
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [newIsin, setNewIsin] = useState("");
  const [newTicker, setNewTicker] = useState("");
  const rows = query.data?.mappings ?? [];
  const save = useMutation({
    mutationFn: () =>
      api.patchIsinMappings({
        mappings: [
          ...rows.map((row) => ({
            isin: row.isin,
            ticker: draft[row.isin] ?? row.ticker,
          })),
          ...(newIsin.trim() && newTicker.trim()
            ? [{ isin: newIsin.trim(), ticker: newTicker.trim() }]
            : []),
        ],
      }),
    onSuccess: (result) => {
      client.setQueryData(["isin-mappings"], result);
      setDraft({});
      setNewIsin("");
      setNewTicker("");
    },
  });
  return (
    <details className="min-w-0 rounded border border-[var(--border)] bg-[var(--panel)] p-3 sm:p-5">
      <summary className="cursor-pointer font-semibold">
        Gespeicherte ISIN-Zuordnungen ({rows.length})
      </summary>
      <p className="my-3 text-sm text-[var(--muted)]">
        Automatisch erkannte und eigene Zuordnungen werden beim nächsten Import
        wiederverwendet.
      </p>
      {query.error && (
        <p role="alert" className="mb-3 text-sm text-[var(--red)]">
          Zuordnungen konnten nicht geladen werden.
        </p>
      )}
      <div className="grid min-w-0 gap-3 md:grid-cols-2 xl:grid-cols-3">
        {rows.map((row) => (
          <label
            className="min-w-0 rounded border border-[var(--border)] p-3 text-sm"
            key={`${row.isin}-${row.source}-${row.ticker}`}
          >
            <span className="mb-2 block break-all font-mono text-xs">
              {row.isin} · {sourceLabels[row.source]}
            </span>
            <input
              aria-label={`Gespeicherter Ticker für ${row.isin}`}
              className="input-dark min-h-11 text-base sm:text-sm"
              disabled={save.isPending}
              value={draft[row.isin] ?? row.ticker}
              onChange={(event) =>
                setDraft({
                  ...draft,
                  [row.isin]: event.target.value.toUpperCase(),
                })
              }
            />
          </label>
        ))}
      </div>
      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        <label className="min-w-0 text-sm">
          Neue ISIN
          <input
            className="input-dark mt-1 min-h-11 text-base sm:text-sm"
            disabled={save.isPending}
            placeholder="US67066G1040"
            value={newIsin}
            onChange={(event) => setNewIsin(event.target.value.toUpperCase())}
          />
        </label>
        <label className="min-w-0 text-sm">
          Neuer Ticker
          <input
            className="input-dark mt-1 min-h-11 text-base sm:text-sm"
            disabled={save.isPending}
            placeholder="NVDA"
            value={newTicker}
            onChange={(event) => setNewTicker(event.target.value.toUpperCase())}
          />
        </label>
      </div>
      <button
        className={`${buttonClass} mt-4 w-full sm:w-auto`}
        disabled={
          save.isPending ||
          !query.data ||
          (!Object.keys(draft).length && !(newIsin.trim() && newTicker.trim()))
        }
        type="button"
        onClick={() => save.mutate()}
      >
        <Save size={16} />
        Zuordnungen speichern
      </button>
      {save.error && (
        <p role="alert" className="mt-3 break-words text-sm text-[var(--red)]">
          {save.error.message}
        </p>
      )}
    </details>
  );
}

export function ImportPreviewTable({ rows }: { rows: PortfolioImportRow[] }) {
  return (
    <ul className="grid min-w-0 gap-3 md:grid-cols-2">
      {rows.map((row) => (
        <li
          key={`${row.ticker}-${row.account}`}
          className="min-w-0 rounded border border-[var(--border)] p-3 text-sm"
        >
          <div className="break-words font-semibold">
            {row.ticker} · {row.name}
          </div>
          <dl className="mt-2 grid grid-cols-2 gap-2 text-xs">
            <div>
              <dt className="text-[var(--muted)]">Stück</dt>
              <dd>{row.shares.toLocaleString("de-DE")}</dd>
            </div>
            <div>
              <dt className="text-[var(--muted)]">Einstand</dt>
              <dd>
                {row.entry_price.toFixed(2)} {row.currency}
              </dd>
            </div>
            <div>
              <dt className="text-[var(--muted)]">Kaufdatum</dt>
              <dd>{row.buy_date ?? "–"}</dd>
            </div>
          </dl>
          {row.warnings.length > 0 && (
            <p className="mt-2 break-words text-xs text-[var(--muted)]">
              {row.warnings.join(" ")}
            </p>
          )}
        </li>
      ))}
    </ul>
  );
}
function MiniStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0 rounded border border-[var(--border)] p-3">
      <div className="text-xs text-[var(--muted)]">{label}</div>
      <div className="mt-1 break-words font-semibold tabular-nums">{value}</div>
    </div>
  );
}
function invalidatePortfolio(client: ReturnType<typeof useQueryClient>) {
  for (const key of [
    "home-dashboard",
    "portfolio-snapshot",
    "portfolio-positions",
    "portfolio-curve",
    "portfolio-transactions",
    "portfolio-cash-flows",
    "portfolio-import-history",
    "portfolio-buy-strength",
    "sell-ranking",
    "isin-mappings",
    "trade-journal",
    "trade-journal-entry",
    "trade-journal-analytics",
  ])
    void client.invalidateQueries({ queryKey: [key] });
}
