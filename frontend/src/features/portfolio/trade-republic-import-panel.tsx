"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, FileText, Save } from "lucide-react";
import { useState, type DragEvent } from "react";
import { StatusChip } from "@/components/ui/status-chip";
import { api } from "@/lib/api/client";
import type {
  PortfolioImportRow,
  TradeRepublicTransactionImportRequest,
  TradeRepublicTransactionImportResponse
} from "@/lib/types/api";

const tradeRepublicCsvPlaceholder = `date,datetime,type,asset_class,name,symbol,shares,price,currency,amount,fee,tax
2025-01-02,2025-01-02T10:00:00Z,BUY,STOCK,NVIDIA,US67066G1040,10,100,USD,-1000,-1,0
2025-01-10,2025-01-10T10:00:00Z,SELL,STOCK,NVIDIA,US67066G1040,2,120,USD,240,-1,-10
`;

export function TradeRepublicTransactionImportPanel() {
  const queryClient = useQueryClient();
  const [fileName, setFileName] = useState("");
  const [content, setContent] = useState("");
  const [replaceOpenPositions, setReplaceOpenPositions] = useState(false);
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
      invalidatePortfolio(queryClient);
    }
  });

  function payload({
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
    previewMutation.mutate(payload({ dryRun: true, nextContent, nextFileName: file.name }));
  }

  function handleDrop(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    setDragActive(false);
    handleFile(event.dataTransfer.files?.[0] ?? null);
  }

  const result = lastResult;
  const missingMappingCount = result?.mappings.filter((mapping) => !mapping.ticker && !(overrides[mapping.isin] || "").trim()).length ?? 0;
  const canSave = Boolean(result?.ok && result.dry_run && result.transactions_total > 0 && content.trim());
  const saveHint = !result
    ? "CSV hochladen oder einfügen. Nach Upload wird automatisch geprüft."
    : !result.ok
      ? "Vorschau enthält Fehler."
      : !result.dry_run
        ? "Dieser Import wurde gespeichert."
        : result.transactions_total === 0
          ? "Keine Buchungen erkannt."
          : missingMappingCount > 0
            ? `${missingMappingCount} ISINs ohne Yahoo-Ticker. Speichern ist möglich; diese offenen Positionen werden übersprungen, bis die Zuordnung ergänzt ist.`
            : "Speichert Transaktionen, Cashflows, ISIN-Zuordnungen und rekonstruierte offene Positionen.";
  const cashLabel = result
    ? result.cash_balance_estimate.toLocaleString("de-DE", { maximumFractionDigits: 2, style: "currency", currency: "EUR" })
    : "-";

  return (
    <section className="rounded border border-[#2d333d] bg-[#171a20] p-5">
      <div className="mb-5 flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div>
          <h2 className="text-lg font-semibold">Trade-Republic-Transaktionsexport</h2>
          <p className="mt-1 max-w-3xl text-sm leading-6 text-[#a0a7b4]">
            CSV direkt im Portfolio hochladen. Die Vorschau startet automatisch; danach werden offene Positionen,
            Transaktionen und Cashflows gespeichert.
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
            <span>Offene Positionen vor TR-Import ersetzen</span>
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
              onClick={() => previewMutation.mutate(payload({ dryRun: true }))}
            >
              <CheckCircle2 size={16} />
              {previewMutation.isPending ? "Prüft" : "TR-Vorschau prüfen"}
            </button>
            <button
              className="inline-flex items-center justify-center gap-2 rounded border border-emerald-300/40 bg-emerald-300/10 px-4 py-3 text-sm text-emerald-100 transition hover:border-emerald-200 disabled:cursor-not-allowed disabled:opacity-50"
              disabled={!canSave || saveMutation.isPending}
              type="button"
              onClick={() => saveMutation.mutate(payload({ dryRun: false }))}
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
        </div>
      </div>
    </section>
  );
}

export function IsinMappingMaintenancePanel() {
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

      <button
        className="mt-4 inline-flex items-center justify-center gap-2 rounded border border-emerald-300/40 bg-emerald-300/10 px-4 py-2 text-sm text-emerald-100 transition hover:border-emerald-200 disabled:cursor-not-allowed disabled:opacity-50"
        disabled={saveMutation.isPending || query.isLoading}
        type="button"
        onClick={() => saveMutation.mutate()}
      >
        <Save size={16} />
        Mappings speichern
      </button>
      {saveMutation.error && (
        <div className="mt-4 rounded border border-rose-300/30 bg-rose-300/10 p-3 text-sm text-rose-100">
          {saveMutation.error instanceof Error ? saveMutation.error.message : "Mappings konnten nicht gespeichert werden."}
        </div>
      )}
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
            Erkannte Zuordnungen werden beim Speichern dauerhaft übernommen und beim nächsten Import automatisch genutzt.
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

function ImportPreviewTable({ rows }: { rows: PortfolioImportRow[] }) {
  return (
    <div className="overflow-hidden rounded border border-[#2d333d]">
      <div className="max-h-[420px] overflow-auto">
        <table className="w-full min-w-[760px] border-collapse text-sm">
          <thead className="sticky top-0 bg-[#1f242c] text-left text-xs uppercase text-[#a0a7b4]">
            <tr>
              <th className="border-b border-[#2d333d] px-4 py-3">Ticker</th>
              <th className="border-b border-[#2d333d] px-4 py-3">Stück</th>
              <th className="border-b border-[#2d333d] px-4 py-3">Einstand</th>
              <th className="border-b border-[#2d333d] px-4 py-3">Kaufdatum</th>
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
                <td className="px-4 py-3 text-xs text-[#a0a7b4]">{row.buy_date ?? "-"}</td>
                <td className="px-4 py-3 text-xs text-[#a0a7b4]">{row.warnings.join(" ") || "-"}</td>
              </tr>
            ))}
          </tbody>
        </table>
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

function invalidatePortfolio(queryClient: ReturnType<typeof useQueryClient>) {
  queryClient.invalidateQueries({ queryKey: ["portfolio-snapshot"] });
  queryClient.invalidateQueries({ queryKey: ["portfolio-positions"] });
  queryClient.invalidateQueries({ queryKey: ["portfolio-curve"] });
  queryClient.invalidateQueries({ queryKey: ["portfolio-transactions"] });
  queryClient.invalidateQueries({ queryKey: ["portfolio-cash-flows"] });
  queryClient.invalidateQueries({ queryKey: ["portfolio-import-history"] });
  queryClient.invalidateQueries({ queryKey: ["portfolio-buy-strength"] });
  queryClient.invalidateQueries({ queryKey: ["sell-ranking"] });
}
