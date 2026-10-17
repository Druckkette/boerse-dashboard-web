"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, FileText, Save, Upload } from "lucide-react";
import { useMemo, useState, type DragEvent } from "react";
import { StatusChip } from "@/components/ui/status-chip";
import { api } from "@/lib/api/client";
import type {
  PortfolioImportRequest,
  PortfolioImportResponse,
} from "@/lib/types/api";

import {
  TradeRepublicTransactionImportPanel,
  IsinMappingMaintenancePanel,
  ImportPreviewTable,
} from "@/features/portfolio/trade-republic-import-panel";

const positionCsvPlaceholder = `Ticker,Name,Shares,Entry_Price,Current_Price,Currency,Buy_Date
NVDA,NVIDIA,12,91.20,126.80,USD,2025-01-15
MSFT,Microsoft,6,382.10,449.40,USD,2025-02-01
`;

export default function PortfolioImportsPage() {
  const queryClient = useQueryClient();
  const [fileName, setFileName] = useState("");
  const [content, setContent] = useState("");
  const [replaceOpenPositions, setReplaceOpenPositions] = useState(true);
  const [dragActive, setDragActive] = useState(false);
  const [lastResult, setLastResult] = useState<PortfolioImportResponse | null>(
    null,
  );

  const previewMutation = useMutation({
    mutationFn: (payload: PortfolioImportRequest) =>
      api.importPortfolioPositions(payload),
    onSuccess: setLastResult,
  });

  const saveMutation = useMutation({
    mutationFn: (payload: PortfolioImportRequest) =>
      api.importPortfolioPositions(payload),
    onSuccess: (result) => {
      setLastResult(result);
      queryClient.invalidateQueries({ queryKey: ["portfolio-snapshot"] });
      queryClient.invalidateQueries({ queryKey: ["portfolio-positions"] });
      queryClient.invalidateQueries({ queryKey: ["sell-ranking"] });
    },
  });

  const result = lastResult;
  const parsedValue = useMemo(() => {
    const positions = result?.positions ?? [];
    return positions.reduce(
      (sum, row) => sum + row.shares * (row.current_price ?? row.entry_price),
      0,
    );
  }, [result]);
  const canSave = Boolean(
    result?.ok && result.positions.length > 0 && result.dry_run,
  );

  function positionPayload({
    dryRun,
    nextContent = content,
    nextFileName = fileName,
  }: {
    dryRun: boolean;
    nextContent?: string;
    nextFileName?: string;
  }): PortfolioImportRequest {
    return {
      file_name: nextFileName || "positions.csv",
      content: nextContent,
      dry_run: dryRun,
      replace_open_positions: replaceOpenPositions,
    };
  }

  async function handleFile(file: File | null) {
    if (!file) return;
    const nextContent = await file.text();
    setFileName(file.name);
    setContent(nextContent);
    setLastResult(null);
    previewMutation.mutate(
      positionPayload({ dryRun: true, nextContent, nextFileName: file.name }),
    );
  }

  function handleDrop(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    setDragActive(false);
    handleFile(event.dataTransfer.files?.[0] ?? null);
  }

  return (
    <div className="min-w-0 space-y-4">
      <TradeRepublicTransactionImportPanel />
      <IsinMappingMaintenancePanel />
      <details className="min-w-0 rounded border border-[var(--border)] p-3 sm:p-5">
        <summary className="cursor-pointer text-sm font-semibold">
          Andere Quelle: fertige Positions-CSV
        </summary>
        <div className="mt-4 space-y-4">
          <ImportModeGuide />

          <div className="grid gap-5 xl:grid-cols-[minmax(0,0.95fr)_minmax(0,1.25fr)]">
            <section className="rounded border border-[var(--border)] bg-[var(--panel)] p-5">
              <div className="mb-4 flex items-center justify-between gap-3">
                <div>
                  <h2 className="text-base font-semibold">
                    Positions-CSV direkt
                  </h2>
                  <div className="text-sm text-[var(--muted)]">
                    Für fertige Positionslisten mit Ticker, Shares und
                    Entry_Price.
                  </div>
                </div>
                <Upload className="text-[var(--green)]" size={20} />
              </div>

              <label
                className={[
                  "block rounded border border-dashed bg-[var(--panel)] p-5 text-center text-sm transition",
                  dragActive
                    ? "border-emerald-300 bg-[var(--green-soft)]"
                    : "border-[var(--border)] hover:border-emerald-300/50",
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
                  onChange={(event) =>
                    handleFile(event.target.files?.[0] ?? null)
                  }
                />
                <FileText className="mx-auto mb-3 text-[var(--muted)]" />
                <span className="font-medium">
                  CSV auswählen oder hier ablegen
                </span>
                <span className="mt-1 block text-xs text-[var(--muted)]">
                  {fileName || "Upload prüft automatisch eine Vorschau."}
                </span>
              </label>

              <label className="mt-4 block text-sm">
                <span className="mb-1 block text-[var(--muted)]">
                  Dateiname
                </span>
                <input
                  className="w-full rounded border border-[var(--border)] bg-[var(--panel)] px-3 py-2"
                  value={fileName}
                  onChange={(event) => setFileName(event.target.value)}
                />
              </label>

              <label className="mt-4 block text-sm">
                <span className="mb-1 block text-[var(--muted)]">
                  CSV Inhalt
                </span>
                <textarea
                  className="min-h-64 w-full rounded border border-[var(--border)] bg-[var(--panel)] px-3 py-2 font-mono text-xs leading-5"
                  placeholder={positionCsvPlaceholder}
                  value={content}
                  onChange={(event) => {
                    setContent(event.target.value);
                    setLastResult(null);
                  }}
                />
              </label>

              <label className="mt-4 flex items-center justify-between gap-3 rounded border border-[var(--border)] bg-[var(--panel)] px-3 py-2 text-sm">
                <span>
                  <span className="block font-medium">
                    Depotbestand synchronisieren
                  </span>
                  <span className="mt-1 block text-xs leading-5 text-[var(--muted)]">
                    Aktiv: offene Positionen, die nicht in der CSV stehen,
                    werden geschlossen.
                  </span>
                </span>
                <input
                  checked={replaceOpenPositions}
                  className="size-4 accent-emerald-300"
                  type="checkbox"
                  onChange={(event) =>
                    setReplaceOpenPositions(event.target.checked)
                  }
                />
              </label>

              <div className="mt-4 grid gap-3 sm:grid-cols-2">
                <button
                  className="inline-flex items-center justify-center gap-2 rounded border border-[var(--border)] bg-[var(--panel)] px-4 py-3 text-sm transition hover:border-emerald-300/60 disabled:cursor-not-allowed disabled:opacity-50"
                  disabled={
                    previewMutation.isPending ||
                    saveMutation.isPending ||
                    !content.trim()
                  }
                  type="button"
                  onClick={() =>
                    previewMutation.mutate(positionPayload({ dryRun: true }))
                  }
                >
                  <CheckCircle2 size={16} />
                  {previewMutation.isPending ? "Prüft" : "Vorschau prüfen"}
                </button>
                <button
                  className="inline-flex items-center justify-center gap-2 rounded border border-emerald-300/40 bg-[var(--green-soft)] px-4 py-3 text-sm text-[var(--green)] transition hover:border-emerald-200 disabled:cursor-not-allowed disabled:opacity-50"
                  disabled={!canSave || saveMutation.isPending}
                  type="button"
                  onClick={() =>
                    saveMutation.mutate(positionPayload({ dryRun: false }))
                  }
                >
                  <Save size={16} />
                  {saveMutation.isPending ? "Speichert" : "Import speichern"}
                </button>
              </div>

              {(previewMutation.error || saveMutation.error) && (
                <div className="mt-4 rounded border border-rose-300/30 bg-[var(--red-soft)] p-3 text-sm text-[var(--red)]">
                  {(previewMutation.error ?? saveMutation.error) instanceof
                  Error
                    ? (previewMutation.error ?? saveMutation.error)?.message
                    : "Import fehlgeschlagen."}
                </div>
              )}
            </section>

            <section className="rounded border border-[var(--border)] bg-[var(--panel)] p-5">
              <div className="mb-4 flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                <div>
                  <h2 className="text-base font-semibold">Vorschau</h2>
                  <div className="text-sm text-[var(--muted)]">
                    {result
                      ? `${result.positions.length} Positionen erkannt, ca. ${parsedValue.toLocaleString("de-DE", { maximumFractionDigits: 0 })} Bewertungswert`
                      : "Noch keine Vorschau geprüft."}
                  </div>
                </div>
                {result && (
                  <StatusChip tone={result.ok ? "good" : "bad"}>
                    {result.ok ? `${result.rows_total} Zeilen` : "prüfen"}
                  </StatusChip>
                )}
              </div>

              {result?.errors.map((error) => (
                <div
                  key={error}
                  className="mb-3 rounded border border-rose-300/30 bg-[var(--red-soft)] p-3 text-sm text-[var(--red)]"
                >
                  {error}
                </div>
              ))}
              {result?.warnings.map((warning) => (
                <div
                  key={warning}
                  className="mb-3 rounded border border-amber-300/30 bg-[var(--yellow-soft)] p-3 text-sm text-[var(--yellow)]"
                >
                  {warning}
                </div>
              ))}

              {result?.positions.length ? (
                <ImportPreviewTable rows={result.positions} />
              ) : (
                <div className="rounded border border-dashed border-[var(--border)] bg-[var(--panel)] p-8 text-center text-sm text-[var(--muted)]">
                  CSV einfügen oder Datei auswählen und Vorschau prüfen.
                </div>
              )}
            </section>
          </div>
        </div>
      </details>
    </div>
  );
}

function ImportModeGuide() {
  return (
    <section className="grid gap-4 lg:grid-cols-2">
      <div className="rounded border border-[var(--border)] bg-[var(--panel)] p-4">
        <h2 className="text-base font-semibold">Positions-CSV</h2>
        <p className="mt-2 text-sm leading-6 text-[var(--muted)]">
          Nutze diesen Weg, wenn die Datei bereits offene Positionen enthält.
          Pflichtfelder: Ticker, Shares, Entry_Price. Die App speichert daraus
          direkt offene Positionen.
        </p>
      </div>
      <div className="rounded border border-[var(--border)] bg-[var(--panel)] p-4">
        <h2 className="text-base font-semibold">
          Trade-Republic-Transaktionsexport
        </h2>
        <p className="mt-2 text-sm leading-6 text-[var(--muted)]">
          Nutze diesen Weg für den TR-Export mit Käufen, Verkäufen, Dividenden
          und Cashflows. Daraus werden offene Positionen rekonstruiert; ISINs
          werden dabei dauerhaft auf Yahoo-Ticker gemappt.
        </p>
      </div>
    </section>
  );
}
