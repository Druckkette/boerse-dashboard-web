"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, FileText, Save, Upload } from "lucide-react";
import { useMemo, useState } from "react";
import { StatusChip } from "@/components/ui/status-chip";
import { api } from "@/lib/api/client";
import type { PortfolioImportResponse, PortfolioImportRow } from "@/lib/types/api";

const sampleCsv = `Ticker,Name,Shares,Entry_Price,Current_Price,Currency,Buy_Date
NVDA,NVIDIA,12,91.20,126.80,USD,2025-01-15
MSFT,Microsoft,6,382.10,449.40,USD,2025-02-01
`;

export default function PortfolioImportsPage() {
  const queryClient = useQueryClient();
  const [fileName, setFileName] = useState("positions.csv");
  const [content, setContent] = useState(sampleCsv);
  const [replaceOpenPositions, setReplaceOpenPositions] = useState(false);
  const [lastResult, setLastResult] = useState<PortfolioImportResponse | null>(null);

  const previewMutation = useMutation({
    mutationFn: () =>
      api.importPortfolioPositions({
        file_name: fileName || "positions.csv",
        content,
        dry_run: true,
        replace_open_positions: replaceOpenPositions
      }),
    onSuccess: setLastResult
  });

  const saveMutation = useMutation({
    mutationFn: () =>
      api.importPortfolioPositions({
        file_name: fileName || "positions.csv",
        content,
        dry_run: false,
        replace_open_positions: replaceOpenPositions
      }),
    onSuccess: (result) => {
      setLastResult(result);
      queryClient.invalidateQueries({ queryKey: ["portfolio-snapshot"] });
      queryClient.invalidateQueries({ queryKey: ["portfolio-positions"] });
    }
  });

  const result = saveMutation.data ?? lastResult;
  const parsedValue = useMemo(() => {
    const positions = result?.positions ?? [];
    return positions.reduce((sum, row) => sum + row.shares * (row.current_price ?? row.entry_price), 0);
  }, [result]);
  const canSave = Boolean(result?.ok && result.positions.length > 0 && result.dry_run);

  async function handleFile(file: File | null) {
    if (!file) return;
    setFileName(file.name);
    setContent(await file.text());
    setLastResult(null);
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-col justify-between gap-4 rounded border border-[#2d333d] bg-[#171a20] p-5 md:flex-row md:items-start">
        <div>
          <h1 className="text-2xl font-semibold">Portfolio Imports</h1>
          <p className="mt-1 max-w-3xl text-sm leading-6 text-[#a0a7b4]">
            CSV-Positionen als bewusstes Snapshot-Update importieren. Vorschau und Speichern sind getrennt.
          </p>
        </div>
        <StatusChip tone={result?.ok ? "good" : result ? "bad" : "neutral"}>
          {result?.ok ? (result.dry_run ? "Vorschau ok" : "Importiert") : result ? "Fehler" : "bereit"}
        </StatusChip>
      </div>

      <div className="grid gap-5 xl:grid-cols-[0.95fr_1.25fr]">
        <section className="rounded border border-[#2d333d] bg-[#171a20] p-5">
          <div className="mb-4 flex items-center justify-between gap-3">
            <div>
              <h2 className="text-base font-semibold">CSV Quelle</h2>
              <div className="text-sm text-[#a0a7b4]">Erlaubte Pflichtspalten: Ticker, Shares, Entry_Price.</div>
            </div>
            <Upload className="text-emerald-300" size={20} />
          </div>

          <label className="block rounded border border-dashed border-[#4b5563] bg-[#111419] p-5 text-center text-sm transition hover:border-emerald-300/50">
            <input
              accept=".csv,text/csv,text/plain"
              className="sr-only"
              type="file"
              onChange={(event) => handleFile(event.target.files?.[0] ?? null)}
            />
            <FileText className="mx-auto mb-3 text-[#a0a7b4]" />
            <span className="font-medium">CSV auswählen</span>
            <span className="mt-1 block text-xs text-[#a0a7b4]">{fileName}</span>
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
              value={content}
              onChange={(event) => {
                setContent(event.target.value);
                setLastResult(null);
              }}
            />
          </label>

          <label className="mt-4 flex items-center justify-between gap-3 rounded border border-[#2d333d] bg-[#111419] px-3 py-2 text-sm">
            <span>Offene Positionen ersetzen, die nicht in der CSV stehen</span>
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
              onClick={() => previewMutation.mutate()}
            >
              <CheckCircle2 size={16} />
              {previewMutation.isPending ? "Prüft" : "Vorschau prüfen"}
            </button>
            <button
              className="inline-flex items-center justify-center gap-2 rounded border border-emerald-300/40 bg-emerald-300/10 px-4 py-3 text-sm text-emerald-100 transition hover:border-emerald-200 disabled:cursor-not-allowed disabled:opacity-50"
              disabled={!canSave || saveMutation.isPending}
              type="button"
              onClick={() => saveMutation.mutate()}
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
    </div>
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
