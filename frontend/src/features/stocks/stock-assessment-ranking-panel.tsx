"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, Download, Plus, RefreshCw, Square, X } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { CollapsiblePanel } from "@/components/ui/collapsible-panel";
import { StatusChip } from "@/components/ui/status-chip";
import { api } from "@/lib/api/client";

const control = "rounded-lg border border-[#d3dce6] bg-white px-3 py-2 text-sm text-[#172033] focus-visible:outline-2 focus-visible:outline-teal-700 disabled:opacity-40";
const terminal = new Set(["done", "failed", "skipped", "cancelled"]);
const scoreLabels = { overall_score: "Gesamtscore", technical_score: "Technisch", fundamental_score: "Fundamental", moving_average_score: "Trend", chart_behavior_score: "Chart", rs_rating: "RS-Rating" };
type ScoreKey = keyof typeof scoreLabels;

export function StockAssessmentRankingPanel() {
  const client = useQueryClient();
  const [open, setOpen] = useState(false);
  const [jobId, setJobId] = useState<string | null>(null);
  const [page, setPage] = useState(0);
  const [minScore, setMinScore] = useState(0);
  const [minRs, setMinRs] = useState(0);
  const [minFundamental, setMinFundamental] = useState(0);
  const [maxWarnings, setMaxWarnings] = useState(100);
  const [completeOnly, setCompleteOnly] = useState(false);
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState<ScoreKey>("overall_score");
  const [required, setRequired] = useState<string[]>([]);
  const [criterion, setCriterion] = useState("");
  const params = new URLSearchParams({
    min_score: String(minScore), min_rs: String(minRs), min_fundamental: String(minFundamental),
    max_warnings: String(maxWarnings), complete_only: String(completeOnly), search, sort, page: String(page)
  });
  required.forEach((label) => params.append("required", label));
  const queryString = params.toString();
  const query = useQuery({ queryKey: ["stock-screening", queryString], queryFn: () => api.stockScreening(queryString), enabled: open, staleTime: 60_000 });
  const exportList = useMutation({ mutationFn: () => api.exportStockScreening(queryString) });
  const jobs = useQuery({ queryKey: ["jobs"], queryFn: api.jobs, enabled: open, refetchInterval: open ? 10_000 : false });
  const discovered = jobs.data?.find((value) => value.job_type === "refresh_stock_assessments" && !terminal.has(value.status));
  const selectedId = discovered?.job_id ?? jobId;
  const job = useQuery({
    queryKey: ["job", selectedId], queryFn: () => api.job(selectedId!), enabled: Boolean(selectedId),
    refetchInterval: (state) => state.state.data && terminal.has(state.state.data.status) ? false : 2000
  });
  const running = Boolean(selectedId && (!job.data || !terminal.has(job.data.status)));
  const start = useMutation({
    mutationFn: () => api.startJob({ type: "refresh_stock_assessments", payload: { source: "stock_screening" } }),
    onSuccess: (created) => { setJobId(created.job_id); void client.invalidateQueries({ queryKey: ["jobs"] }); }
  });
  const cancel = useMutation({
    mutationFn: () => api.cancelJob(selectedId!),
    onSuccess: () => client.invalidateQueries({ queryKey: ["job", selectedId] })
  });
  const jobStatus = job.data?.status;
  useEffect(() => {
    if (jobStatus && terminal.has(jobStatus)) {
      void client.invalidateQueries({ queryKey: ["stock-screening"] });
      void client.invalidateQueries({ queryKey: ["stock-assessment-ranking"] });
    }
  }, [jobStatus, client]);
  const criteria = query.data?.criteria ?? [];
  const rows = query.data?.rows ?? [];
  const totalCount = query.data?.total_count ?? 0;
  const pageCount = Math.max(1, Math.ceil(totalCount / 50));
  const currentPage = page;
  const summary = query.data?.summary;
  const error = query.error ?? start.error ?? cancel.error ?? exportList.error;
  const filters = [
    { label: "Gesamtscore mindestens", value: minScore, set: setMinScore },
    { label: "RS-Rating mindestens", value: minRs, set: setMinRs },
    { label: "Fundamental-Score mindestens", value: minFundamental, set: setMinFundamental },
    { label: "Warnungen höchstens", value: maxWarnings, set: setMaxWarnings }
  ];
  return (
    <CollapsiblePanel title="Aktienbewertung Ranking" open={open} onOpenChange={setOpen}
      summary={<StatusChip tone={running ? "warning" : "neutral"}>{running ? "Bewertung läuft" : (summary?.records_written ?? 0) + " Aktien bewertet"}</StatusChip>}>
      <div className="space-y-4 p-4 text-[#172033]">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div><h3 className="text-base font-semibold">Bestenliste deines Aktienuniversums</h3>
            <p className="mt-1 text-sm text-[#687386]">{summary?.universe_count != null ? summary.records_written + " von " + summary.universe_count + " Aktien bewertet" : "Noch keine vollständige Universumsbewertung"}
              {summary?.generated_at ? " · Auswertung " + new Date(summary.generated_at).toLocaleString("de-DE") : ""}</p>
            {summary?.universe_count != null && <p className="mt-1 text-xs text-[#687386]">{summary.missing_count ?? 0} ohne ausreichende Kurse · {summary.stale_count ?? 0} mit altem Kursstand · {summary.error_count ?? 0} Bewertungsfehler</p>}
          </div>
          <div className="flex flex-wrap gap-2">
            <button type="button" className="inline-flex items-center gap-2 rounded-lg bg-[#0f766e] px-3 py-2 text-sm font-medium text-white! disabled:opacity-50" disabled={running || start.isPending} onClick={() => start.mutate()}><RefreshCw size={16} className={running || start.isPending ? "animate-spin" : ""} />Universum bewerten</button>
            <button type="button" className={control + " inline-flex items-center gap-2"} disabled={!totalCount || exportList.isPending} onClick={() => exportList.mutate()}><Download size={16} />{exportList.isPending ? "Export läuft" : "Bestenliste exportieren"}</button>
          </div>
        </div>
        {selectedId && <div className="rounded-lg border border-[#e3e8ef] bg-[#f6f8fb] p-3" aria-live="polite">
          <div className="flex flex-wrap items-center justify-between gap-2 text-sm"><span>{job.data?.current_step ?? "Bewertung wird eingereiht"} · {job.data?.progress ?? 0}%</span>
            {running && <button type="button" onClick={() => cancel.mutate()} disabled={cancel.isPending} className={control + " inline-flex items-center gap-2"}><Square size={13} />Abbrechen</button>}
          </div>
          <progress className="mt-2 h-2 w-full accent-teal-700" value={job.data?.progress ?? 0} max={100} aria-label="Fortschritt der Universumsbewertung" />
          <p className="mt-1 text-xs text-[#687386]">{job.data?.message}</p>
          {job.data?.error_message && <p className="mt-2 text-sm text-red-700">{job.data.error_message}</p>}
        </div>}
        {error && <p role="alert" className="text-sm text-red-700">{error instanceof Error ? error.message : "Bestenliste konnte nicht geladen werden."}</p>}
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">{filters.map((filter) => <label key={filter.label} className="grid gap-1 text-xs">{filter.label}<input className={control + " min-w-0 w-full"} type="number" min={0} max={filter.label.startsWith("RS") ? 99 : 100} value={filter.value} onChange={(event) => { filter.set(Math.max(0, Math.min(filter.label.startsWith("RS") ? 99 : 100, Number(event.target.value)))); setPage(0); }} /></label>)}</div>
        <div className="flex items-end gap-2">
          <label className="grid min-w-0 flex-1 gap-1 text-xs">Pflichtkriterium<select className={control + " w-full"} value={criterion} onChange={(event) => setCriterion(event.target.value)}><option value="">Kriterium auswählen</option>{criteria.filter((label) => !required.includes(label)).map((label) => <option key={label}>{label}</option>)}</select></label>
          <button type="button" title="Pflichtkriterium hinzufügen" aria-label="Pflichtkriterium hinzufügen" className={control} disabled={!criterion} onClick={() => { setRequired([...required, criterion]); setCriterion(""); setPage(0); }}><Plus size={20} /></button>
        </div>
        {!!required.length && <div className="flex flex-wrap gap-2">{required.map((label) => <span key={label} className="inline-flex max-w-full items-center gap-2 rounded-lg bg-teal-50 px-3 py-2 text-xs text-teal-900"><span>{label}</span><button type="button" aria-label={label + " entfernen"} onClick={() => setRequired(required.filter((value) => value !== label))}><X size={14} /></button></span>)}</div>}
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" className="accent-teal-700" checked={completeOnly} onChange={(event) => { setCompleteOnly(event.target.checked); setPage(0); }} />Nur aktuelle Kurse mit Fundamentals, RS-Linie, RS-Rating und 13F</label>
        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-[#e3e8ef] pt-3">
          <label className="flex flex-wrap items-center gap-2 text-sm">{totalCount} Treffer<input aria-label="Ticker oder Firmenname suchen" className={control + " max-w-52"} maxLength={100} placeholder="Ticker / Firma" value={search} onChange={(event) => { setSearch(event.target.value); setPage(0); }} /></label>
          <label className="flex items-center gap-2 text-sm">Sortierung<select className={control} value={sort} onChange={(event) => { setSort(event.target.value as ScoreKey); setPage(0); }}>{Object.entries(scoreLabels).map(([key, label]) => <option value={key} key={key}>{label}</option>)}</select></label>
        </div>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[1040px] text-left text-sm text-[#172033]">
          <thead className="border-y border-[#e3e8ef] bg-[#f6f8fb] text-xs text-[#687386]"><tr>{["Platz", "Aktie", "Score", "Technisch", "Fundamental", "Trend", "Chart", "RS", "Warnungen", "Kursstand / Daten"].map((label) => <th key={label} className="px-3 py-3 font-medium">{label}</th>)}</tr></thead>
          <tbody>{rows.map((row, index) => <tr key={row.ticker} className="border-b border-[#e3e8ef] hover:bg-teal-50/40">
            <td className="px-3 py-3 tabular-nums">{currentPage * 50 + index + 1}</td>
            <td className="px-3 py-3"><Link className="font-semibold text-teal-800 hover:underline" href={"/stocks/" + encodeURIComponent(row.ticker)}>{row.ticker}</Link><div className="max-w-44 truncate text-xs text-[#687386]" title={row.name}>{row.name}</div></td>
            <td className="px-3 py-3"><StatusChip tone={row.verdict_tone}>{row.overall_score} · {row.verdict_label}</StatusChip></td>
            <td className="px-3 py-3">{row.technical_score.toFixed(0)}</td><td className="px-3 py-3">{row.fundamentals_available ? row.fundamental_score.toFixed(0) : "Fehlen"}</td>
            <td className="px-3 py-3">{row.moving_average_score.toFixed(0)}</td><td className="px-3 py-3">{row.chart_behavior_score}</td><td className="px-3 py-3">{row.rs_rating ?? "Fehlt"}</td>
            <td className="px-3 py-3"><span title={row.top_warning}>{row.warnings_count}</span></td>
            <td className="px-3 py-3 text-xs"><span className={row.prices_stale ? "text-amber-800" : "text-[#687386]"}>{row.as_of}{row.prices_stale ? " · veraltet" : ""}</span><div className="mt-1 text-amber-800">{[!row.fundamentals_available && "Fundamentals fehlen", !row.rs_line_available && "RS-Linie fehlt", !row.institutional_available && "13F fehlen"].filter(Boolean).join(" · ")}</div></td>
          </tr>)}</tbody>
        </table>
      </div>
      {!rows.length && <p className="p-4 text-sm text-[#687386]">{query.isLoading ? "Bestenliste lädt…" : "Keine Treffer für diese Auswahl."}</p>}
      <div className="flex items-center justify-between gap-3 p-4 text-sm text-[#687386]"><span>Seite {currentPage + 1} von {pageCount}</span><div className="flex gap-2">
        <button type="button" aria-label="Vorherige Seite" className={control} disabled={currentPage === 0} onClick={() => setPage(currentPage - 1)}><ChevronLeft size={18} /></button>
        <button type="button" aria-label="Nächste Seite" className={control} disabled={currentPage + 1 >= pageCount} onClick={() => setPage(currentPage + 1)}><ChevronRight size={18} /></button>
      </div></div>
    </CollapsiblePanel>
  );
}
