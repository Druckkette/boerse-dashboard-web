"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, FileText, Save, Upload } from "lucide-react";
import { useMemo, useState, type DragEvent } from "react";
import { StatusChip } from "@/components/ui/status-chip";
import { api } from "@/lib/api/client";
import type {
  PortfolioImportRequest,
  PortfolioImportResponse,
  PortfolioImportRow,
  TradeRepublicTransactionImportRequest,
  TradeRepublicTransactionImportResponse
} from "@/lib/types/api";

const positionCsvPlaceholder = `Ticker,Name,Shares,Entry_Price,Current_Price,Currency,Buy_Date
NVDA,NVIDIA,12,91.20,126.80,USD,2025-01-15
MSFT,Microsoft,6,382.10,449.40,USD,2025-02-01
`;

const tradeRepublicCsvPlaceholder = `date,datetime,type,asset_class,name,symbol,shares,price,currency,amount,fee,tax
2025-01-02,2025-01-02T10:00:00Z,BUY,STOCK,NVIDIA,US67066G1040,10,100,USD,-1000,-1,0
2025-01-10,2025-01-10T10:00:00Z,SELL,STOCK,NVIDIA,US67066G1040,2,120,USD,240,-1,-10
`;

export default function PortfolioImportsPage() {
  const queryClient = useQueryClient();
  const [fileName, setFileName] = useState("");
  const [content, setContent] = useState("");
  const [replaceOpenPositions, setReplaceOpenPositions] = useState(true);
  const [dragActive, setDragActive] = useState(false);
  const [lastResult, setLastResult] = useState<PortfolioImportResponse | null>(null);

  const previewMutation = useMutation({
    mutationFn: (payload: PortfolioImportRequest) => api.importPortfolioPositions(payload),
    onSuccess: setLastResult
  });

  const saveMutation = useMutation({
    mutationFn: (payload: PortfolioImportRequest) => api.importPortfolioPositions(payload),
    onSuccess: (result) => {
      setLastResult(result);
      queryClient.invalidateQueries({ queryKey: ["portfolio-snapshot"] });
      queryClient.invalidateQueries({ queryKey: ["portfolio-positions"] });
      queryClient.invalidateQueries({ queryKey: ["sell-ranking"] });
    }
  });

  const result = lastResult;
  const parsedValue = useMemo(() => {
    const positions = result?.positions ?? [];
    return positions.reduce((sum, row) => sum + row.shares * (row.current_price ?? row.entry_price), 0);
  }, [result]);
  const canSave = Boolean(result?.ok && result.positions.length > 0 && result.dry_run);

  function positionPayload({
    dryRun,
    nextContent = content,
    nextFileName = fileName
  }: {
    dryRun: boolean;
    nextContent?: string;
    nextFileName?: string;
  }): PortfolioImportRequest {
    return {
      file_name: nextFileName || "positions.csv",
      content: nextContent,
      dry_run: dryRun,
      replace_open_positions: replaceOpenPositions
    };
  }

  async function handleFile(file: File | null) {
    if (!file) return;
    const nextContent = await file.text();
    setFileName(file.name);
    setContent(nextContent);
    setLastResult(null);
    previewMutation.mutate(positionPayload({ dryRun: true, nextContent, nextFileName: file.name }));
  }

  function handleDrop(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    setDragActive(false);
    handleFile(event.dataTransfer.files?.[0] ?? null);
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-col justify-between gap-4 rounded border border-[#2d333d] bg-[#171a20] p-5 md:flex-row md:items-start">
        <div>
          <h1 className="text-2xl font-semibold">Portfolio Imports</h1>
          <p className="mt-1 max-w-3xl text-sm leading-6 text-[#a0a7b4]">
            Daten direkt im Browser hochladen. Es wird keine Datei auf der NAS manuell abgelegt.
          </p>
        </div>
        <StatusChip tone={result?.ok ? "good" : result ? "bad" : "neutral"}>
          {result?.ok ? (result.dry_run ? "Vorschau ok" : "Importiert") : result ? "Fehler" : "bereit"}
        </StatusChip>
      </div>

      <ImportModeGuide />

      <div className="grid gap-5 xl:grid-cols-[0.95fr_1.25fr]">
        <section className="rounded border border-[#2d333d] bg-[#171a20] p-5">
          <div className="mb-4 flex items-center justify-between gap-3">
            <div>
              <h2 className="text-base font-semibold">Positions-CSV direkt</h2>
              <div className="text-sm text-[#a0a7b4]">Für fertige Positionslisten mit Ticker, Shares und Entry_Price.</div>
            </div>
            <Upload className="text-emerald-300" size={20} />
          </div>

          <label
            className={[
              "block rounded border border-dashed bg-[#111419] p-5 text-center text-sm transition",
              dragActive ? "border-emerald-300 bg-emerald-300/10" : "border-[#4b5563] hover:border-emerald-300/50"
            ].join(" ")}
            onDragEnter={(event) => {
              event.preventDefault();
              setDragActive(true);
            }}
            onDragLeave={(event) => {
              event.preventDefault();
              setDragActive(false);
            }}
            onDragOver={(event) => event.preventDefault()}
            onDrop={handleDrop}
          >
            <input
              accept=".csv,text/csv,text/plain"
              className="sr-only"
              type="file"
              onChange={(event) => handleFile(event.target.files?.[0] ?? null)}
            />
            <FileText className="mx-auto mb-3 text-[#a0a7b4]" />
            <span className="font-medium">CSV auswählen oder hier ablegen</span>
            <span className="mt-1 block text-xs text-[#a0a7b4]">
              {fileName || "Upload prüft automatisch eine Vorschau."}
            </span>
          </label>

          <label className="mt-4 block text-sm">
            <span className="mb-1 block text-[#a0a7b4]">Dateiname</span>
            <input
              className="w-full rounded border border-[#2d333d] bg-[#111419] px-3 py-2"
              value={fileName}
              onChange={(event) => setFileName(event.target.value)}
            />
          </label>

          <label className="mt-4 block text-sm">
            <span className="mb-1 block text-[#a0a7b4]">CSV Inhalt</span>
            <textarea
              className="min-h-64 w-full rounded border border-[#2d333d] bg-[#111419] px-3 py-2 font-mono text-xs leading-5"
              placeholder={positionCsvPlaceholder}
              value={content}
              onChange={(event) => {
                setContent(event.target.value);
                setLastResult(null);
              }}
            />
          </label>

          <label className="mt-4 flex items-center justify-between gap-3 rounded border border-[#2d333d] bg-[#111419] px-3 py-2 text-sm">
            <span>
              <span className="block font-medium">Depotbestand synchronisieren</span>
              <span className="mt-1 block text-xs leading-5 text-[#a0a7b4]">
                Aktiv: offene Positionen, die nicht in der CSV stehen, werden geschlossen.
              </span>
            </span>
            <input
              checked={replaceOpenPositions}
              className="size-4 accent-emerald-300"
              type="checkbox"
              onChange={(event) => setReplaceOpenPositions(event.target.checked)}
            />
          </label>

          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            <button
              className="inline-flex items-center justify-center gap-2 rounded border border-[#2d333d] bg-[#111419] px-4 py-3 text-sm transition hover:border-emerald-300/60 disabled:cursor-not-allowed disabled:opacity-50"
              disabled={previewMutation.isPending || saveMutation.isPending || !content.trim()}
              type="button"
              onClick={() => previewMutation.mutate(positionPayload({ dryRun: true }))}
            >
              <CheckCircle2 size={16} />
              {previewMutation.isPending ? "Prüft" : "Vorschau prüfen"}
            </button>
            <button
              className="inline-flex items-center justify-center gap-2 rounded border border-emerald-300/40 bg-emerald-300/10 px-4 py-3 text-sm text-emerald-100 transition hover:border-emerald-200 disabled:cursor-not-allowed disabled:opacity-50"
              disabled={!canSave || saveMutation.isPending}
              type="button"
              onClick={() => saveMutation.mutate(positionPayload({ dryRun: false }))}
            >
              <Save size={16} />
              {saveMutation.isPending ? "Speichert" : "Import speichern"}
            </button>
          </div>

          {(previewMutation.error || saveMutation.error) && (
            <div className="mt-4 rounded border border-rose-300/30 bg-rose-300/10 p-3 text-sm text-rose-100">
              {(previewMutation.error ?? saveMutation.error) instanceof Error
                ? (previewMutation.error ?? saveMutation.error)?.message
                : "Import fehlgeschlagen."}
            </div>
          )}
        </section>

        <section className="rounded border border-[#2d333d] bg-[#171a20] p-5">
          <div className="mb-4 flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
            <div>
              <h2 className="text-base font-semibold">Vorschau</h2>
              <div className="text-sm text-[#a0a7b4]">
                {result
                  ? `${result.positions.length} Positionen erkannt, ca. ${parsedValue.toLocaleString("de-DE", { maximumFractionDigits: 0 })} Bewertungswert`
                  : "Noch keine Vorschau geprüft."}
              </div>
            </div>
            {result && <StatusChip tone={result.ok ? "good" : "bad"}>{result.ok ? `${result.rows_total} Zeilen` : "prüfen"}</StatusChip>}
          </div>

          {result?.errors.map((error) => (
            <div key={error} className="mb-3 rounded border border-rose-300/30 bg-rose-300/10 p-3 text-sm text-rose-100">
              {error}
            </div>
          ))}
          {result?.warnings.map((warning) => (
            <div key={warning} className="mb-3 rounded border border-amber-300/30 bg-amber-300/10 p-3 text-sm text-amber-100">
              {warning}
            </div>
          ))}

          {result?.positions.length ? (
            <ImportPreviewTable rows={result.positions} />
          ) : (
            <div className="rounded border border-dashed border-[#4b5563] bg-[#111419] p-8 text-center text-sm text-[#a0a7b4]">
              CSV einfügen oder Datei auswählen und Vorschau prüfen.
            </div>
          )}
        </section>
      </div>

      <TradeRepublicTransactionImportPanel />
      <IsinMappingMaintenancePanel />
    </div>
  );
}

function ImportModeGuide() {
  return (
    <section className="grid gap-4 lg:grid-cols-2">
      <div className="rounded border border-[#2d333d] bg-[#171a20] p-4">
        <h2 className="text-base font-semibold">Positions-CSV</h2>
        <p className="mt-2 text-sm leading-6 text-[#a0a7b4]">
          Nutze diesen Weg, wenn die Datei bereits offene Positionen enthält. Pflichtfelder: Ticker, Shares,
          Entry_Price. Die App speichert daraus direkt offene Positionen.
        </p>
      </div>
      <div className="rounded border border-[#2d333d] bg-[#171a20] p-4">
        <h2 className="text-base font-semibold">Trade-Republic-Transaktionsexport</h2>
        <p className="mt-2 text-sm leading-6 text-[#a0a7b4]">
          Nutze diesen Weg für den TR-Export mit Käufen, Verkäufen, Dividenden und Cashflows. Daraus werden offene
          Positionen rekonstruiert; ISINs werden dabei dauerhaft auf Yahoo-Ticker gemappt.
        </p>
      </div>
    </section>
  );
}

function TradeRepublicTransactionImportPanel() {
  const queryClient = useQueryClient();
  const [fileName, setFileName] = useState("");
  const [content, setContent] = useState("");
  const [replaceOpenPositions, setReplaceOpenPositions] = useState(true);
  const [dragActive, setDragActive] = useState(false);
  const [overrides, setOverrides] = useState<Record<string, string>>({});
  const [lastResult, setLastResult] = useState<TradeRepublicTransactionImportResponse | null>(null);

  const previewMutation = useMutation({
    mutationFn: (payload: TradeRepublicTransactionImportRequest) => api.importTradeRepublicTransactions(payload),
    onSuccess: (result) => {
      setLastResult(result);
      setOverrides((current) => {
        const next = { ...current };
        for (const mapping of result.mappings) {
          if (mapping.ticker && !next[mapping.isin]) next[mapping.isin] = mapping.ticker;
        }
        return next;
      });
    }
  });

  const saveMutation = useMutation({
    mutationFn: (payload: TradeRepublicTransactionImportRequest) => api.importTradeRepublicTransactions(payload),
    onSuccess: (result) => {
      setLastResult(result);
      queryClient.invalidateQueries({ queryKey: ["portfolio-snapshot"] });
      queryClient.invalidateQueries({ queryKey: ["portfolio-positions"] });
      queryClient.invalidateQueries({ queryKey: ["portfolio-curve"] });
      queryClient.invalidateQueries({ queryKey: ["portfolio-transactions"] });
      queryClient.invalidateQueries({ queryKey: ["portfolio-cash-flows"] });
      queryClient.invalidateQueries({ queryKey: ["sell-ranking"] });
    }
  });

  function tradeRepublicPayload({
    dryRun,
    nextContent = content,
    nextFileName = fileName
  }: {
    dryRun: boolean;
    nextContent?: string;
    nextFileName?: string;
  }): TradeRepublicTransactionImportRequest {
    return {
      file_name: nextFileName || "trade-republic-transactions.csv",
      content: nextContent,
      dry_run: dryRun,
      replace_open_positions: replaceOpenPositions,
      isin_overrides: overrides
    };
  }

  async function handleFile(file: File | null) {
    if (!file) return;
    const nextContent = await file.text();
    setFileName(file.name);
    setContent(nextContent);
    setLastResult(null);
    previewMutation.mutate(tradeRepublicPayload({ dryRun: true, nextContent, nextFileName: file.name }));
  }

  function handleDrop(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    setDragActive(false);
    handleFile(event.dataTransfer.files?.[0] ?? null);
  }

  const result = lastResult;
  const missingMappingCount = result?.mappings.filter((mapping) => !mapping.ticker && !(overrides[mapping.isin] || "").trim()).length ?? 0;
  const canSave = Boolean(
    result?.ok &&
      result.dry_run &&
      result.transactions_total > 0 &&
      content.trim() &&
      !(replaceOpenPositions && missingMappingCount > 0)
  );
  const saveHint = !result
    ? "CSV hochladen oder einfügen. Nach Upload wird automatisch geprüft."
    : !result.ok
      ? "Vorschau enthält Fehler."
      : !result.dry_run
        ? "Dieser Import wurde bereits gespeichert."
        : result.transactions_total === 0
          ? "Keine Buchungen erkannt."
          : missingMappingCount > 0 && replaceOpenPositions
            ? `${missingMappingCount} offene ISINs ohne Yahoo-Ticker. Bitte Zuordnung ergänzen, damit der Depotbestand sicher synchronisiert werden kann.`
            : missingMappingCount > 0
              ? `${missingMappingCount} ISINs ohne Yahoo-Ticker. Speichern ist im Anhänge-Modus möglich; diese offenen Positionen werden übersprungen, bis die Zuordnung ergänzt ist.`
              : replaceOpenPositions
                ? "Synchronisiert dein Depot: nicht mehr enthaltene offene Positionen werden geschlossen, vorhandene Positionen aktualisiert."
                : "Anhänge-Modus: neue/erkannte Positionen werden aktualisiert, nicht mehr enthaltene Positionen bleiben offen.";
  const cashLabel = result
    ? result.cash_balance_estimate.toLocaleString("de-DE", { maximumFractionDigits: 2, style: "currency", currency: "EUR" })
    : "-";

  return (
    <section className="rounded border border-[#2d333d] bg-[#171a20] p-5">
      <div className="mb-5 flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div>
          <h2 className="text-lg font-semibold">Trade-Republic-Transaktionsexport</h2>
          <p className="mt-1 max-w-3xl text-sm leading-6 text-[#a0a7b4]">
            CSV direkt hochladen; die Vorschau startet automatisch. Danach kannst du offene Positionen plus
            Transaktionen speichern. Es muss nichts manuell auf der NAS abgelegt werden.
          </p>
        </div>
        <StatusChip tone={result?.ok ? "good" : result ? "bad" : "neutral"}>
          {result?.ok ? (result.dry_run ? "Vorschau ok" : "Importiert") : result ? "Fehler" : "bereit"}
        </StatusChip>
      </div>

      <div className="grid gap-5 xl:grid-cols-[0.95fr_1.25fr]">
        <div>
          <label
            className={[
              "block rounded border border-dashed bg-[#111419] p-5 text-center text-sm transition",
              dragActive ? "border-emerald-300 bg-emerald-300/10" : "border-[#4b5563] hover:border-emerald-300/50"
            ].join(" ")}
            onDragEnter={(event) => {
              event.preventDefault();
              setDragActive(true);
            }}
            onDragLeave={(event) => {
              event.preventDefault();
              setDragActive(false);
            }}
            onDragOver={(event) => event.preventDefault()}
            onDrop={handleDrop}
          >
            <input
              accept=".csv,text/csv,text/plain"
              className="sr-only"
              type="file"
              onChange={(event) => handleFile(event.target.files?.[0] ?? null)}
            />
            <FileText className="mx-auto mb-3 text-[#a0a7b4]" />
            <span className="font-medium">TR-CSV auswählen oder hier ablegen</span>
            <span className="mt-1 block text-xs text-[#a0a7b4]">
              {fileName || "Upload prüft automatisch eine Vorschau."}
            </span>
          </label>

          <label className="mt-4 block text-sm">
            <span className="mb-1 block text-[#a0a7b4]">CSV Inhalt</span>
            <textarea
              className="min-h-56 w-full rounded border border-[#2d333d] bg-[#111419] px-3 py-2 font-mono text-xs leading-5"
              placeholder={tradeRepublicCsvPlaceholder}
              value={content}
              onChange={(event) => {
                setContent(event.target.value);
                setLastResult(null);
              }}
            />
          </label>

          <label className="mt-4 flex items-center justify-between gap-3 rounded border border-[#2d333d] bg-[#111419] px-3 py-2 text-sm">
            <span>
              <span className="block font-medium">Depotbestand synchronisieren</span>
              <span className="mt-1 block text-xs leading-5 text-[#a0a7b4]">
                Aktiv: Positionen, die im neuen TR-Export nicht mehr offen sind, werden geschlossen.
              </span>
            </span>
            <input
              checked={replaceOpenPositions}
              className="size-4 accent-emerald-300"
              type="checkbox"
              onChange={(event) => setReplaceOpenPositions(event.target.checked)}
            />
          </label>

          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            <button
              className="inline-flex items-center justify-center gap-2 rounded border border-[#2d333d] bg-[#111419] px-4 py-3 text-sm transition hover:border-emerald-300/60 disabled:cursor-not-allowed disabled:opacity-50"
              disabled={previewMutation.isPending || saveMutation.isPending || !content.trim()}
              type="button"
              onClick={() => previewMutation.mutate(tradeRepublicPayload({ dryRun: true }))}
            >
              <CheckCircle2 size={16} />
              {previewMutation.isPending ? "Prüft" : "TR-Vorschau prüfen"}
            </button>
            <button
              className="inline-flex items-center justify-center gap-2 rounded border border-emerald-300/40 bg-emerald-300/10 px-4 py-3 text-sm text-emerald-100 transition hover:border-emerald-200 disabled:cursor-not-allowed disabled:opacity-50"
              disabled={!canSave || saveMutation.isPending}
              type="button"
              onClick={() => saveMutation.mutate(tradeRepublicPayload({ dryRun: false }))}
            >
              <Save size={16} />
              {saveMutation.isPending ? "Speichert" : "TR-Import speichern"}
            </button>
          </div>
          <div className="mt-3 rounded border border-[#2d333d] bg-[#111419] p-3 text-xs leading-5 text-[#a0a7b4]">
            {saveHint}
          </div>

          {(previewMutation.error || saveMutation.error) && (
            <div className="mt-4 rounded border border-rose-300/30 bg-rose-300/10 p-3 text-sm text-rose-100">
              {(previewMutation.error ?? saveMutation.error) instanceof Error
                ? (previewMutation.error ?? saveMutation.error)?.message
                : "TR-Import fehlgeschlagen."}
            </div>
          )}
        </div>

        <div className="space-y-4">
          <div className="grid gap-3 md:grid-cols-3">
            <MiniStat label="Buchungen" value={result ? String(result.rows_total) : "-"} />
            <MiniStat label="Offene Positionen" value={result ? String(result.positions.length) : "-"} />
            <MiniStat label="Cash-Schätzung" value={cashLabel} />
          </div>

          {result?.errors.map((error) => (
            <div key={error} className="rounded border border-rose-300/30 bg-rose-300/10 p-3 text-sm text-rose-100">
              {error}
            </div>
          ))}
          {result?.warnings.map((warning) => (
            <div key={warning} className="rounded border border-amber-300/30 bg-amber-300/10 p-3 text-sm text-amber-100">
              {warning}
            </div>
          ))}

          <MappingEditor result={result} overrides={overrides} onChange={setOverrides} />

          {result?.positions.length ? (
            <ImportPreviewTable rows={result.positions} />
          ) : (
            <div className="rounded border border-dashed border-[#4b5563] bg-[#111419] p-8 text-center text-sm text-[#a0a7b4]">
              TR-CSV einfügen oder Datei auswählen und Vorschau prüfen.
            </div>
          )}

          {result?.skipped_positions.length ? (
            <div className="rounded border border-[#2d333d] bg-[#111419] p-4 text-sm">
              <h3 className="mb-3 font-semibold">Nicht automatisch importiert</h3>
              <div className="space-y-2">
                {result.skipped_positions.map((item) => (
                  <div key={item.isin} className="flex items-start justify-between gap-3 border-b border-[#242a33] pb-2 last:border-b-0">
                    <div>
                      <div className="font-medium">{item.name || item.isin}</div>
                      <div className="text-xs text-[#a0a7b4]">
                        {item.isin} · {item.asset_class}
                      </div>
                    </div>
                    <div className="max-w-sm text-right text-xs text-[#a0a7b4]">{item.reason}</div>
                  </div>
                ))}
              </div>
            </div>
          ) : null}
        </div>
      </div>
    </section>
  );
}

function MappingEditor({
  result,
  overrides,
  onChange
}: {
  result: TradeRepublicTransactionImportResponse | null;
  overrides: Record<string, string>;
  onChange: (value: Record<string, string>) => void;
}) {
  if (!result?.mappings.length) return null;
  const missingCount = result.mappings.filter((mapping) => !mapping.ticker && !(overrides[mapping.isin] || "").trim()).length;
  const recognizedCount = result.mappings.length - missingCount;
  return (
    <div className="rounded border border-[#2d333d] bg-[#111419] p-4">
      <div className="mb-3 flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
        <div>
          <h3 className="font-semibold">ISIN zu Yahoo-Ticker</h3>
          <p className="mt-1 text-sm leading-6 text-[#a0a7b4]">
            Trade Republic liefert ISINs. Für Kursdaten und Sell-Monitor braucht die Web-App Yahoo-Ticker. Erkannte
            Zuordnungen werden beim Speichern dauerhaft übernommen und beim nächsten Import automatisch genutzt.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <StatusChip tone={recognizedCount > 0 ? "good" : "neutral"}>{recognizedCount} erkannt</StatusChip>
          <StatusChip tone={missingCount > 0 ? "warning" : "good"}>{missingCount} offen</StatusChip>
        </div>
      </div>
      <div className="max-h-72 space-y-2 overflow-auto pr-1">
        {result.mappings.map((mapping) => (
          <label key={mapping.isin} className="grid gap-2 rounded border border-[#242a33] p-3 text-sm md:grid-cols-[1fr_160px]">
            <span>
              <span className="flex flex-wrap items-center gap-2">
                <span className="block font-medium">{mapping.name || mapping.isin}</span>
                <StatusChip tone={(overrides[mapping.isin] || mapping.ticker) ? "good" : "warning"}>
                  {(overrides[mapping.isin] || mapping.ticker) ? "importfähig" : "Ticker fehlt"}
                </StatusChip>
              </span>
              <span className="text-xs text-[#a0a7b4]">
                {mapping.isin} · {mapping.asset_class} · {mapping.source}
              </span>
            </span>
            <input
              className="input-dark"
              placeholder="NVDA"
              value={overrides[mapping.isin] ?? mapping.ticker}
              onChange={(event) => onChange({ ...overrides, [mapping.isin]: event.target.value.toUpperCase() })}
            />
          </label>
        ))}
      </div>
    </div>
  );
}

function MiniStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded border border-[#2d333d] bg-[#111419] p-3">
      <div className="text-xs uppercase text-[#a0a7b4]">{label}</div>
      <div className="mt-1 font-semibold tabular-nums">{value}</div>
    </div>
  );
}

function IsinMappingMaintenancePanel() {
  const queryClient = useQueryClient();
  const query = useQuery({ queryKey: ["isin-mappings"], queryFn: api.isinMappings, staleTime: 60_000 });
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [newIsin, setNewIsin] = useState("");
  const [newTicker, setNewTicker] = useState("");
  const rows = query.data?.mappings ?? [];
  const saveMutation = useMutation({
    mutationFn: () =>
      api.patchIsinMappings({
        mappings: [
          ...rows.map((row) => ({ isin: row.isin, ticker: draft[row.isin] ?? row.ticker })),
          ...(newIsin.trim() && newTicker.trim()
            ? [{ isin: newIsin.trim().toUpperCase(), ticker: newTicker.trim().toUpperCase() }]
            : [])
        ]
      }),
    onSuccess: (result) => {
      queryClient.setQueryData(["isin-mappings"], result);
      setDraft({});
      setNewIsin("");
      setNewTicker("");
    }
  });

  return (
    <section className="rounded border border-[#2d333d] bg-[#171a20] p-5">
      <div className="mb-4 flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div>
          <h2 className="text-lg font-semibold">Gespeicherte ISIN-Zuordnungen</h2>
          <p className="mt-1 max-w-3xl text-sm leading-6 text-[#a0a7b4]">
            Permanentes Wörterbuch für Trade-Republic-ISINs. Was hier gespeichert ist, muss beim nächsten TR-Import
            nicht erneut eingetragen werden.
          </p>
        </div>
        <StatusChip tone={saveMutation.isPending ? "warning" : "neutral"}>
          {saveMutation.isPending ? "speichert" : `${rows.length} Mappings`}
        </StatusChip>
      </div>

      <div className="overflow-hidden rounded border border-[#2d333d]">
        <div className="max-h-80 overflow-auto">
          <table className="w-full min-w-[680px] border-collapse text-sm">
            <thead className="sticky top-0 bg-[#1f242c] text-left text-xs uppercase text-[#a0a7b4]">
              <tr>
                <th className="border-b border-[#2d333d] px-4 py-3">ISIN</th>
                <th className="border-b border-[#2d333d] px-4 py-3">Yahoo-Ticker</th>
                <th className="border-b border-[#2d333d] px-4 py-3">Quelle</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={`${row.isin}-${row.source}`} className="border-b border-[#242a33]">
                  <td className="px-4 py-3 font-mono text-xs">{row.isin}</td>
                  <td className="px-4 py-3">
                    <input
                      className="input-dark max-w-48"
                      value={draft[row.isin] ?? row.ticker}
                      onChange={(event) => setDraft({ ...draft, [row.isin]: event.target.value.toUpperCase() })}
                    />
                  </td>
                  <td className="px-4 py-3 text-xs text-[#a0a7b4]">{row.source}</td>
                </tr>
              ))}
              <tr className="border-b border-[#242a33]">
                <td className="px-4 py-3">
                  <input
                    className="input-dark font-mono text-xs"
                    placeholder="US67066G1040"
                    value={newIsin}
                    onChange={(event) => setNewIsin(event.target.value.toUpperCase())}
                  />
                </td>
                <td className="px-4 py-3">
                  <input
                    className="input-dark max-w-48"
                    placeholder="NVDA"
                    value={newTicker}
                    onChange={(event) => setNewTicker(event.target.value.toUpperCase())}
                  />
                </td>
                <td className="px-4 py-3 text-xs text-[#a0a7b4]">neu</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-3">
        <button
          className="inline-flex items-center justify-center gap-2 rounded border border-emerald-300/40 bg-emerald-300/10 px-4 py-2 text-sm text-emerald-100 transition hover:border-emerald-200 disabled:cursor-not-allowed disabled:opacity-50"
          disabled={saveMutation.isPending || query.isLoading}
          type="button"
          onClick={() => saveMutation.mutate()}
        >
          <Save size={16} />
          Mappings speichern
        </button>
        {query.isLoading && <span className="text-sm text-[#a0a7b4]">Mappings werden geladen...</span>}
      </div>
      {saveMutation.error && (
        <div className="mt-4 rounded border border-rose-300/30 bg-rose-300/10 p-3 text-sm text-rose-100">
          {saveMutation.error instanceof Error ? saveMutation.error.message : "Mappings konnten nicht gespeichert werden."}
        </div>
      )}
    </section>
  );
}

function ImportPreviewTable({ rows }: { rows: PortfolioImportRow[] }) {
  return (
    <div className="overflow-hidden rounded border border-[#2d333d]">
      <div className="max-h-[520px] overflow-auto">
        <table className="w-full min-w-[760px] border-collapse text-sm">
          <thead className="sticky top-0 bg-[#1f242c] text-left text-xs uppercase text-[#a0a7b4]">
            <tr>
              <th className="border-b border-[#2d333d] px-4 py-3">Ticker</th>
              <th className="border-b border-[#2d333d] px-4 py-3">Stück</th>
              <th className="border-b border-[#2d333d] px-4 py-3">Einstand</th>
              <th className="border-b border-[#2d333d] px-4 py-3">Kurs</th>
              <th className="border-b border-[#2d333d] px-4 py-3">Währung</th>
              <th className="border-b border-[#2d333d] px-4 py-3">Hinweise</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={`${row.ticker}-${row.account}`} className="border-b border-[#242a33]">
                <td className="px-4 py-3">
                  <div className="font-semibold">{row.ticker}</div>
                  <div className="text-xs text-[#a0a7b4]">{row.name}</div>
                </td>
                <td className="px-4 py-3 tabular-nums">{row.shares.toLocaleString("de-DE")}</td>
                <td className="px-4 py-3 tabular-nums">{row.entry_price.toFixed(2)}</td>
                <td className="px-4 py-3 tabular-nums">{row.current_price?.toFixed(2) ?? "-"}</td>
                <td className="px-4 py-3">{row.currency}</td>
                <td className="px-4 py-3 text-xs text-[#a0a7b4]">{row.warnings.join(" ") || "-"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
