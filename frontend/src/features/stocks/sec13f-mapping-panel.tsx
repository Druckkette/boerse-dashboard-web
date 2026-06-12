"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Database, RefreshCw, Save } from "lucide-react";
import { useState } from "react";
import { StatusChip } from "@/components/ui/status-chip";
import { api } from "@/lib/api/client";
import type { Sec13FMappingUpdate } from "@/lib/types/api";

const emptyForm: Sec13FMappingUpdate = {
  cusip: "",
  ticker: "",
  issuer_name: ""
};

export function Sec13FMappingPanel() {
  const queryClient = useQueryClient();
  const [form, setForm] = useState<Sec13FMappingUpdate>(emptyForm);
  const query = useQuery({
    queryKey: ["sec13f-mappings"],
    queryFn: () => api.sec13FMappingReview(500),
    staleTime: 60_000
  });
  const mutation = useMutation({
    mutationFn: () => api.updateSec13FMapping(normalizeForm(form)),
    onSuccess: () => {
      setForm(emptyForm);
      void queryClient.invalidateQueries({ queryKey: ["sec13f-mappings"] });
    }
  });

  const mappings = query.data?.mappings ?? [];
  const unmatched = query.data?.unmatched ?? [];
  const canSave = normalizeForm(form).cusip.length === 9 && normalizeForm(form).ticker.length > 0;

  return (
    <section className="rounded border border-[#2d333d] bg-[#171a20]">
      <div className="flex flex-col gap-3 border-b border-[#2d333d] p-5 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <Database className="size-5 text-[#8ea4c8]" />
            <h2 className="text-lg font-semibold">13F CUSIP-Mapping</h2>
            <StatusChip tone={query.data?.source === "database" ? "good" : "warning"}>
              {mappings.length} Mappings
            </StatusChip>
            <StatusChip tone={unmatched.length ? "warning" : "neutral"}>{unmatched.length} offen</StatusChip>
          </div>
          <div className="mt-1 text-sm text-[#a0a7b4]">
            Manuelle Overrides werden beim nächsten SEC-13F-Refresh automatisch verwendet.
          </div>
        </div>
        <button
          className="inline-flex items-center gap-2 rounded border border-[#2d333d] bg-[#111419] px-3 py-2 text-sm transition hover:border-emerald-300/60"
          type="button"
          onClick={() => query.refetch()}
        >
          <RefreshCw size={15} className={query.isFetching ? "animate-spin text-emerald-300" : "text-[#a0a7b4]"} />
          Aktualisieren
        </button>
      </div>

      <div className="grid gap-5 p-5 xl:grid-cols-[360px_1fr]">
        <div className="rounded border border-[#242a33] bg-[#111419] p-4">
          <h3 className="text-sm font-semibold">Mapping eintragen</h3>
          <div className="mt-4 space-y-3">
            <Field
              label="CUSIP"
              value={form.cusip}
              onChange={(value) => setForm((current) => ({ ...current, cusip: value }))}
              placeholder="67066G104"
            />
            <Field
              label="Ticker"
              value={form.ticker}
              onChange={(value) => setForm((current) => ({ ...current, ticker: value }))}
              placeholder="NVDA"
            />
            <Field
              label="Issuer"
              value={form.issuer_name ?? ""}
              onChange={(value) => setForm((current) => ({ ...current, issuer_name: value }))}
              placeholder="NVIDIA CORP"
            />
            <button
              className="inline-flex w-full items-center justify-center gap-2 rounded bg-emerald-300 px-3 py-2 text-sm font-semibold text-[#101318] transition hover:bg-emerald-200 disabled:cursor-not-allowed disabled:opacity-40"
              type="button"
              disabled={!canSave || mutation.isPending}
              onClick={() => mutation.mutate()}
            >
              <Save size={15} />
              Speichern
            </button>
            {mutation.isError && (
              <div className="text-xs text-rose-200">
                {mutation.error instanceof Error ? mutation.error.message : "Mapping konnte nicht gespeichert werden."}
              </div>
            )}
          </div>
        </div>

        <div className="grid gap-5 2xl:grid-cols-2">
          <MappingTable mappings={mappings} loading={query.isLoading} />
          <UnmatchedTable unmatched={unmatched} jobId={query.data?.unmatched_source_job_id ?? ""} />
        </div>
      </div>
    </section>
  );
}

function MappingTable({
  mappings,
  loading
}: {
  mappings: NonNullable<Awaited<ReturnType<typeof api.sec13FMappingReview>>>["mappings"];
  loading: boolean;
}) {
  return (
    <div className="min-w-0 rounded border border-[#242a33] bg-[#111419]">
      <div className="border-b border-[#242a33] px-4 py-3 text-sm font-semibold">Gespeicherte Mappings</div>
      {loading ? (
        <div className="p-4 text-sm text-[#a0a7b4]">Lädt...</div>
      ) : mappings.length === 0 ? (
        <div className="p-4 text-sm text-[#a0a7b4]">Noch keine CUSIP-Mappings gespeichert.</div>
      ) : (
        <div className="max-h-[360px] overflow-auto">
          <table className="w-full min-w-[520px] border-collapse text-sm">
            <thead className="sticky top-0 bg-[#1f242c] text-left text-xs uppercase text-[#a0a7b4]">
              <tr>
                <th className="px-3 py-2 font-medium">CUSIP</th>
                <th className="px-3 py-2 font-medium">Ticker</th>
                <th className="px-3 py-2 font-medium">Quelle</th>
                <th className="px-3 py-2 font-medium">Issuer</th>
              </tr>
            </thead>
            <tbody>
              {mappings.map((mapping) => (
                <tr key={`${mapping.cusip}-${mapping.ticker}`} className="border-b border-[#242a33]">
                  <td className="px-3 py-2 font-mono text-xs">{mapping.cusip}</td>
                  <td className="px-3 py-2 font-semibold">{mapping.ticker}</td>
                  <td className="px-3 py-2 text-xs text-[#a0a7b4]">{mapping.source}</td>
                  <td className="max-w-56 truncate px-3 py-2 text-xs text-[#a0a7b4]">{mapping.issuer_name || "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function UnmatchedTable({
  unmatched,
  jobId
}: {
  unmatched: NonNullable<Awaited<ReturnType<typeof api.sec13FMappingReview>>>["unmatched"];
  jobId: string;
}) {
  return (
    <div className="min-w-0 rounded border border-[#242a33] bg-[#111419]">
      <div className="flex items-center justify-between gap-3 border-b border-[#242a33] px-4 py-3">
        <div className="flex items-center gap-2 text-sm font-semibold">
          <AlertTriangle className="size-4 text-amber-200" />
          Unmatched CUSIPs
        </div>
        {jobId && <div className="max-w-40 truncate text-xs text-[#697386]">{jobId}</div>}
      </div>
      {unmatched.length === 0 ? (
        <div className="p-4 text-sm text-[#a0a7b4]">Keine offenen CUSIPs aus dem letzten 13F-Job.</div>
      ) : (
        <div className="max-h-[360px] overflow-auto">
          <table className="w-full min-w-[700px] border-collapse text-sm">
            <thead className="sticky top-0 bg-[#1f242c] text-left text-xs uppercase text-[#a0a7b4]">
              <tr>
                <th className="px-3 py-2 font-medium">CUSIP</th>
                <th className="px-3 py-2 font-medium">Issuer</th>
                <th className="px-3 py-2 font-medium">Wert</th>
                <th className="px-3 py-2 font-medium">Grund</th>
                <th className="px-3 py-2 font-medium">Kandidaten</th>
              </tr>
            </thead>
            <tbody>
              {unmatched.map((item) => (
                <tr key={item.cusip} className="border-b border-[#242a33]">
                  <td className="px-3 py-2 font-mono text-xs">{item.cusip}</td>
                  <td className="max-w-56 truncate px-3 py-2">
                    <div>{item.issuer || "-"}</div>
                    <div className="text-xs text-[#697386]">{item.title}</div>
                  </td>
                  <td className="px-3 py-2 tabular-nums text-[#a0a7b4]">{usd(item.current_total_value_usd)}</td>
                  <td className="px-3 py-2 text-xs text-[#a0a7b4]">{item.reason || "-"}</td>
                  <td className="max-w-44 truncate px-3 py-2 text-xs text-[#a0a7b4]">
                    {item.candidate_tickers || "-"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function Field({
  label,
  value,
  onChange,
  placeholder
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
}) {
  return (
    <label className="block text-xs uppercase text-[#a0a7b4]">
      {label}
      <input
        className="mt-1 w-full rounded border border-[#2d333d] bg-[#171a20] px-3 py-2 text-sm text-white outline-none transition placeholder:text-[#697386] focus:border-emerald-300/70"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
      />
    </label>
  );
}

function normalizeForm(form: Sec13FMappingUpdate): Sec13FMappingUpdate {
  return {
    cusip: form.cusip.replace(/[^a-zA-Z0-9]/g, "").toUpperCase(),
    ticker: form.ticker.trim().toUpperCase().replace(".", "-"),
    issuer_name: form.issuer_name?.trim() ?? ""
  };
}

function usd(value?: number | null) {
  if (typeof value !== "number" || Number.isNaN(value)) return "-";
  if (value >= 1_000_000_000) return `$${(value / 1_000_000_000).toFixed(1)} Mrd.`;
  if (value >= 1_000_000) return `$${(value / 1_000_000).toFixed(1)} Mio.`;
  return `$${value.toLocaleString("de-DE", { maximumFractionDigits: 0 })}`;
}
