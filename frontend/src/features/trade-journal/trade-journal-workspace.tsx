"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import {
  AlertTriangle,
  ArrowLeft,
  ChevronRight,
  CircleHelp,
  FileText,
  FilterX,
  NotebookPen,
  Plus,
  Search,
  SlidersHorizontal,
  Upload,
  X
} from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { FormEvent, ReactNode, useEffect, useMemo, useRef, useState } from "react";
import { StatusChip } from "@/components/ui/status-chip";
import { api } from "@/lib/api/client";
import { berlinDate } from "@/lib/date";
import type {
  Tone,
  TradeJournalAnalytics,
  TradeJournalEntryDetail,
  TradeJournalEntryRequest,
  TradeJournalEntryStatus,
  TradeJournalEntrySummary,
  TradeJournalEntryType,
  TradeJournalFilters
} from "@/lib/types/api";

type Tab = "executions" | "analytics";
const PAGE_SIZE = 20;
type Draft = {
  ticker: string;
  entry_type: TradeJournalEntryType;
  trade_date: string;
  price: string;
  shares: string;
  currency: string;
  fees: string;
  tax: string;
  source_evidence: string;
  note: string;
  stop_price: string;
};

const contextTone: Record<TradeJournalEntrySummary["context_status"], Tone> = {
  archived: "good",
  reconstructed: "neutral",
  partial: "warning",
  missing: "neutral",
  pending: "warning",
  failed: "bad"
};

export function TradeJournalWorkspace() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const queryClient = useQueryClient();
  const tab = parseTab(searchParams.get("tab"));
  const selectedId = searchParams.get("entry");
  const filters = useMemo<TradeJournalFilters>(() => ({
    query: searchParams.get("query") ?? "",
    entry_type: (searchParams.get("type") ?? "") as TradeJournalEntryType | "",
    status: (searchParams.get("status") ?? "") as TradeJournalEntryStatus | "",
    source: (searchParams.get("source") ?? "") as TradeJournalFilters["source"],
    date_from: searchParams.get("from") ?? "",
    date_to: searchParams.get("to") ?? "",
    sort: searchParams.get("sort") === "oldest" ? "oldest" : "newest",
    limit: PAGE_SIZE,
    offset: Math.max(0, Number(searchParams.get("offset") ?? 0) || 0)
  }), [searchParams]);
  const [searchInput, setSearchInput] = useState(filters.query ?? "");
  const [dialog, setDialog] = useState<{ draft: Draft; entry: TradeJournalEntryDetail | null } | null>(null);

  const entriesQuery = useQuery({
    queryKey: ["trade-journal", filters],
    queryFn: () => api.tradeJournalEntries(filters)
  });
  const commonFilters = { query: filters.query, date_from: filters.date_from, date_to: filters.date_to };
  const analyticsQuery = useQuery({
    queryKey: ["trade-journal-analytics", commonFilters],
    queryFn: () => api.tradeJournalAnalytics(commonFilters),
    enabled: tab === "analytics"
  });
  const selectedQuery = useQuery({
    queryKey: ["trade-journal-entry", selectedId],
    queryFn: () => api.tradeJournalEntry(selectedId ?? ""),
    enabled: Boolean(selectedId)
  });

  const saveMutation = useMutation({
    mutationFn: ({ draft, entry }: { draft: Draft; entry: TradeJournalEntryDetail | null }) => {
      const payload = draftToRequest(draft);
      if (!entry) return api.createTradeJournalEntry(payload);
      if (entry.source === "trade_republic") return api.updateTradeJournalNotes(entry.id, {
        ...payload,
        basis_text: entry.entry_type === "buy" ? draft.note : entry.basis_text,
        primary_reasons: entry.entry_type === "buy" ? draft.note : entry.primary_reasons,
        sell_reason: entry.entry_type === "sell" ? draft.note : entry.sell_reason,
        alternative_entry: entry.alternative_entry,
        alternative_entry_text: entry.alternative_entry_text,
        questionnaire: entry.questionnaire,
        chart_images: entry.chart_images
      });
      return api.updateTradeJournalEntry(entry.id, payload);
    },
    onSuccess: (result) => {
      setDialog(null);
      void queryClient.invalidateQueries({ queryKey: ["trade-journal"] });
      void queryClient.invalidateQueries({ queryKey: ["trade-journal-entry", result.entry.id] });
      void queryClient.invalidateQueries({ queryKey: ["trade-journal-analytics"] });
      navigate({ entry: result.entry.id });
    }
  });
  const backfillMutation = useMutation({
    mutationFn: () => api.startJob({ type: "backfill_trade_journal_contexts", payload: { limit: 5000, source: "trade_journal" } })
  });

  const backfillJob = useQuery({
    queryKey: ["job", backfillMutation.data?.job_id],
    queryFn: () => api.job(backfillMutation.data?.job_id ?? ""),
    enabled: Boolean(backfillMutation.data?.job_id),
    refetchInterval: (query) => ["done", "failed", "skipped", "cancelled"].includes(query.state.data?.status ?? "") ? false : 2000
  });
  const handledBackfill = useRef<string | null>(null);
  useEffect(() => {
    const job = backfillJob.data;
    if (job?.status === "done" && handledBackfill.current !== job.job_id) {
      handledBackfill.current = job.job_id;
      void queryClient.invalidateQueries({ queryKey: ["trade-journal"] });
      void queryClient.invalidateQueries({ queryKey: ["trade-journal-entry"] });
    }
  }, [backfillJob.data, queryClient]);
  const backfillRunning = backfillMutation.isPending || ["queued", "running"].includes(backfillJob.data?.status ?? backfillMutation.data?.status ?? "");

  const entries = entriesQuery.data?.entries ?? [];
  const hasFilters = Boolean(filters.query || filters.entry_type || filters.status || filters.source || filters.date_from || filters.date_to);

  function navigate(changes: Record<string, string | number | null | undefined>) {
    const params = new URLSearchParams(searchParams.toString());
    for (const [key, value] of Object.entries(changes)) {
      if (value === null || value === undefined || value === "" || value === 0) params.delete(key);
      else params.set(key, String(value));
    }
    router.push(`/trade-journal${params.size ? `?${params.toString()}` : ""}`, { scroll: false });
  }

  function applySearch(event: FormEvent) {
    event.preventDefault();
    navigate({ query: searchInput.trim(), offset: null, entry: null });
  }

  function resetFilters() {
    setSearchInput("");
    router.push(`/trade-journal${tab === "executions" ? "" : `?tab=${tab}`}`, { scroll: false });
  }

  function openNew(type: TradeJournalEntryType = "buy") {
    const probableTicker = /^[A-Za-z0-9.^-]{1,32}$/.test(searchInput.trim()) ? searchInput.trim().toUpperCase() : "";
    setDialog({ entry: null, draft: emptyDraft(probableTicker, type) });
  }

  function openEdit(entry: TradeJournalEntryDetail) {
    setDialog({ entry, draft: entryDraft(entry) });
  }

  return (
    <div className="space-y-5">
      <section className="rounded-[18px] border border-[#dfe6ed] bg-white p-5 shadow-[0_8px_28px_rgba(15,23,42,0.05)] md:p-6">
        <div className="flex flex-col gap-5 2xl:flex-row 2xl:items-center 2xl:justify-between">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight text-[#172033]">Alle Handelsentscheidungen an einem Ort</h1>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-[#687386]">
              Broker-Ausführungen bilden die verlässliche Basis. Historische Bewertungen zeigen sichtbar, ob Daten archiviert, rekonstruiert, teilweise vorhanden oder noch nicht verfügbar sind.
            </p>
          </div>
          <div className="flex flex-col gap-2 sm:flex-row">
            <Link className="inline-flex h-10 items-center justify-center gap-2 rounded-[10px] bg-[#0f766e] px-4 text-sm font-semibold !text-white hover:bg-[#0b655f]" href="/portfolio/imports">
              <Upload size={16} /> Trade-Republic-Auszug importieren
            </Link>
            <button className="inline-flex h-10 items-center justify-center gap-2 rounded-[10px] border border-[#cfd9e3] px-4 text-sm font-semibold text-[#304052] hover:bg-[#f6f8fb]" type="button" onClick={() => openNew()}>
              <Plus size={16} /> Manueller Nachtrag
            </button>
            <button className="inline-flex h-10 items-center justify-center gap-2 rounded-[10px] border border-[#cfd9e3] px-4 text-sm font-semibold text-[#304052] hover:bg-[#f6f8fb] disabled:opacity-50" disabled={backfillRunning} type="button" onClick={() => backfillMutation.mutate()}>
              <BarChart3Icon /> {backfillRunning ? "Historie wird ergänzt…" : "Historie ergänzen"}
            </button>
          </div>
        </div>
        {backfillMutation.data && <p className="mt-3 text-sm text-[#0f766e]">{backfillJob.data?.status === "done" ? "Historie ergänzt. Die Ansichten wurden aktualisiert." : backfillJob.data?.status === "failed" ? `Historie konnte nicht ergänzt werden: ${backfillJob.data.error_message || backfillJob.data.message}` : backfillJob.data?.message || "Hintergrundjob gestartet. Fortschritt ist unter Jobs sichtbar."}</p>}
        {backfillMutation.isError && <p className="mt-3 text-sm text-rose-700">Historische Ergänzung konnte nicht gestartet werden: {(backfillMutation.error as Error).message}</p>}
        <div className="mt-5 grid gap-3 border-t border-[#edf1f5] pt-4 sm:grid-cols-3">
          <HeaderStat label="Ausführungen" value={String(entriesQuery.data?.total ?? 0)} detail="im aktuellen Filter" />
          <HeaderStat label="Brokerdaten" value={String(entries.filter((entry) => entry.source === "trade_republic").length)} detail="auf dieser Seite" />
          <HeaderStat label="Kontext offen" value={String(entries.filter((entry) => ["missing", "pending", "failed"].includes(entry.context_status)).length)} detail="auf dieser Seite" />
        </div>
      </section>

      <section className="overflow-hidden rounded-[16px] border border-[#dfe6ed] bg-white">
        <nav className="flex overflow-x-auto border-b border-[#e8edf2] px-2" aria-label="Tagebuchansichten">
          {([[
            "executions", "Ausführungen"
          ], ["analytics", "Auswertung"]] as Array<[Tab, string]>).map(([key, label]) => (
            <button key={key} className={clsx("border-b-2 px-4 py-3 text-sm font-semibold", tab === key ? "border-[#0f766e] text-[#0f766e]" : "border-transparent text-[#687386] hover:text-[#172033]")} type="button" onClick={() => navigate({ tab: key === "executions" ? null : key, entry: null, offset: null })}>{label}</button>
          ))}
        </nav>

        <form className="grid gap-3 border-b border-[#e8edf2] p-4 md:grid-cols-2 xl:grid-cols-4" onSubmit={applySearch}>
          <label className="relative xl:col-span-2">
            <span className="sr-only">Aktie, Ticker oder ISIN suchen</span>
            <Search className="absolute left-3 top-2.5 size-4 text-[#8a96a8]" />
            <input className="h-9 w-full rounded-[9px] border border-[#d8e1ea] pl-9 pr-3 text-sm outline-none focus:border-[#0f766e]" value={searchInput} placeholder="Aktie, Ticker oder ISIN suchen" onChange={(event) => setSearchInput(event.target.value)} />
          </label>
          <FilterSelect label="Art" value={filters.entry_type ?? ""} onChange={(value) => navigate({ type: value, offset: null, entry: null })} options={[["", "Alle Arten"], ["buy", "Käufe"], ["sell", "Verkäufe"], ["ex_post", "Nachbereitungen"]]} />
          <FilterSelect label="Status" value={filters.status ?? ""} onChange={(value) => navigate({ status: value, offset: null, entry: null })} options={[["", "Alle Status"], ["open", "Offene Position"], ["closed", "Abgeschlossen"], ["draft", "Zuordnung offen"]]} />
          <FilterSelect label="Quelle" value={filters.source ?? ""} onChange={(value) => navigate({ source: value, offset: null, entry: null })} options={[["", "Alle Quellen"], ["broker", "Trade Republic"], ["manual", "Manuell"]]} />
          <input aria-label="Zeitraum von" className="h-9 rounded-[9px] border border-[#d8e1ea] px-2 text-sm" type="date" value={filters.date_from ?? ""} onChange={(event) => navigate({ from: event.target.value, offset: null, entry: null })} />
          <input aria-label="Zeitraum bis" className="h-9 rounded-[9px] border border-[#d8e1ea] px-2 text-sm" type="date" value={filters.date_to ?? ""} onChange={(event) => navigate({ to: event.target.value, offset: null, entry: null })} />
          <FilterSelect label="Sortierung" value={filters.sort ?? "newest"} onChange={(value) => navigate({ sort: value === "newest" ? null : value, offset: null })} options={[["newest", "Neueste zuerst"], ["oldest", "Älteste zuerst"]]} />
          <button className="inline-flex h-9 items-center justify-center gap-2 rounded-[9px] bg-[#172033] px-3 text-sm font-semibold !text-white" type="submit"><SlidersHorizontal size={14} /> Anwenden</button>
        </form>
        {hasFilters && <div className="flex justify-end px-4 pt-3"><button className="inline-flex items-center gap-1 text-sm font-medium text-[#0f766e] hover:underline" type="button" onClick={resetFilters}><FilterX size={14} /> Filter zurücksetzen</button></div>}

        {tab === "executions" && <Pagination total={entriesQuery.data?.total ?? 0} offset={filters.offset ?? 0} loading={entriesQuery.isLoading} onPage={(offset) => navigate({ offset, entry: null })} />}
        <div className="p-4">
          {tab === "executions" && <ExecutionTable entries={entries} loading={entriesQuery.isLoading} onView={(id) => navigate({ entry: id })} />}
          {tab === "analytics" && <AnalyticsPanel data={analyticsQuery.data} loading={analyticsQuery.isLoading} />}
        </div>

        {tab === "executions" && <Pagination total={entriesQuery.data?.total ?? 0} offset={filters.offset ?? 0} loading={entriesQuery.isLoading} onPage={(offset) => navigate({ offset, entry: null })} />}

      </section>

      {entriesQuery.isError && <ErrorPanel>Ausführungen konnten nicht geladen werden: {(entriesQuery.error as Error).message}</ErrorPanel>}

      {selectedId && <DetailWindow entryId={selectedId} onClose={() => { if (dialog) setDialog(null); else navigate({ entry: null }); }}>
        {selectedQuery.isLoading ? <LoadingRows /> : selectedQuery.data?.entry ? <EntryDetail entry={selectedQuery.data.entry} onView={(id) => navigate({ entry: id })} onEdit={() => openEdit(selectedQuery.data.entry)} /> : <ErrorPanel>Der Eintrag konnte nicht geladen werden: {selectedQuery.error instanceof Error ? selectedQuery.error.message : "Nicht gefunden"}</ErrorPanel>}
        {dialog && <EntryDialog dialog={dialog} pending={saveMutation.isPending} error={saveMutation.error} onClose={() => setDialog(null)} onChange={(draft) => setDialog({ ...dialog, draft })} onSave={() => saveMutation.mutate(dialog)} />}
      </DetailWindow>}
      {dialog && !selectedId && <EntryDialog dialog={dialog} pending={saveMutation.isPending} error={saveMutation.error} onClose={() => setDialog(null)} onChange={(draft) => setDialog({ ...dialog, draft })} onSave={() => saveMutation.mutate(dialog)} />}

    </div>
  );
}

function ExecutionTable({ entries, loading, onView }: { entries: TradeJournalEntrySummary[]; loading: boolean; onView: (id: string) => void }) {
  if (loading) return <LoadingRows />;
  if (!entries.length) return <EmptyState title="Keine Ausführungen gefunden" text="Passe die Filter an oder importiere einen Trade-Republic-CSV-Auszug." />;
  return (
    <>
      <div className="hidden overflow-x-auto md:block">
        <table className="w-full min-w-[1050px] border-separate border-spacing-0 text-sm">
          <thead><tr className="text-left text-xs font-semibold uppercase tracking-[0.08em] text-[#7a8798]">{["Kauf- / Verkaufsdatum", "Aktie", "Ausführung", "Stückzahl", "Preis", "Betrag", "Ergebnis", "Bewertung", "Notiz", ""].map((label) => <th key={label} className="border-b border-[#e8edf2] px-3 py-3">{label}</th>)}</tr></thead>
          <tbody>{entries.map((entry) => <tr key={entry.id} className="group cursor-pointer hover:bg-[#f7fafb]" tabIndex={0} aria-label={`${entry.ticker}: ${executionText(entry)} vom ${formatDate(entry.trade_date)} öffnen`} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); onView(entry.id); } }} onClick={() => onView(entry.id)}><td className="border-b border-[#edf1f5] px-3 py-3 tabular-nums text-[#526174]">{dateTime(entry)}</td><td className="border-b border-[#edf1f5] px-3 py-3"><div className="font-semibold text-[#172033]">{entry.instrument_name || entry.ticker}</div><div className="text-xs text-[#7a8798]">{entry.ticker}{entry.isin ? ` · ${entry.isin}` : ""}</div></td><td className="border-b border-[#edf1f5] px-3 py-3"><ExecutionLabel entry={entry} /></td><td className="border-b border-[#edf1f5] px-3 py-3 text-right tabular-nums">{quantity(entry.shares)}</td><td className="border-b border-[#edf1f5] px-3 py-3 text-right tabular-nums">{money(entry.price, entry.currency)}</td><td className="border-b border-[#edf1f5] px-3 py-3 text-right tabular-nums">{money(entry.gross_amount ?? gross(entry), entry.currency)}</td><td className={clsx("border-b border-[#edf1f5] px-3 py-3 text-right font-semibold tabular-nums", resultColor(entry.realized_pnl))}>{entry.entry_type === "sell" && entry.realized_pnl != null ? <span title="Verkaufsergebnis">{money(entry.realized_pnl, entry.currency)}</span> : <span className="font-normal text-[#9aa5b3]" title="Verkaufsergebnisse stehen bei der Verkaufsausführung; Käufe zeigen sie im Detail">—</span>}</td><td className="border-b border-[#edf1f5] px-3 py-3"><StatusChip tone={contextTone[entry.context_status]}>{entry.context_label}</StatusChip></td><td className="border-b border-[#edf1f5] px-3 py-3 text-center"><span className="sr-only">{entry.has_note ? "Notiz vorhanden" : "Keine Notiz"}</span><NotebookPen className={clsx("mx-auto size-4", entry.has_note ? "text-[#0f766e]" : "text-[#c4ccd5]")} /></td><td className="border-b border-[#edf1f5] px-3 py-3"><ChevronRight className="size-4 text-[#a6b0bd] group-hover:text-[#0f766e]" /></td></tr>)}</tbody>
        </table>
      </div>
      <div className="space-y-3 md:hidden">{entries.map((entry) => <button key={entry.id} className="w-full rounded-[14px] border border-[#e1e7ed] p-4 text-left" type="button" onClick={() => onView(entry.id)}><div className="flex items-start justify-between gap-3"><div><div className="font-semibold text-[#172033]">{entry.instrument_name || entry.ticker}</div><div className="mt-1 text-xs text-[#7a8798]">{dateTime(entry)} · {entry.ticker}</div></div><StatusChip tone={contextTone[entry.context_status]}>{entry.context_label}</StatusChip></div><div className="mt-4 grid grid-cols-3 gap-3 text-sm"><SmallValue label="Ausführung" value={executionText(entry)} /><SmallValue label="Stück" value={quantity(entry.shares)} /><SmallValue label="Preis" value={money(entry.price, entry.currency)} /></div></button>)}</div>
    </>
  );
}

function AnalyticsPanel({ data, loading }: { data?: TradeJournalAnalytics; loading: boolean }) {
  if (loading) return <LoadingRows />;
  if (!data) return <EmptyState title="Keine Auswertung verfügbar" text="Die Kennzahlen werden serverseitig über alle gefilterten Trades berechnet." />;
  return <div className="space-y-4"><div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4"><Metric label="Geschlossene Trades" value={String(data.closed_trades)} detail={`${data.excluded_incomplete} ohne vollständige Kostenbasis ausgeschlossen`} /><Metric label="Nettoergebnis" value={money(data.net_result, "EUR")} detail="Summe der Tradeergebnisse; Währungen im Detail prüfen" tone={data.net_result >= 0 ? "good" : "bad"} /><Metric label="Trefferquote" value={data.hit_rate_pct == null ? "—" : `${number(data.hit_rate_pct)} %`} detail={`${data.winners} Gewinner · ${data.losers} Verlierer`} /><Metric label="Profit Factor" value={data.profit_factor == null ? "—" : number(data.profit_factor)} detail="Bruttogewinne / Bruttoverluste" /></div><div className="grid gap-3 sm:grid-cols-2"><Metric label="Durchschnittsgewinn" value={money(data.average_win, "EUR")} detail="nur gewinnende, geschlossene Trades" tone="good" /><Metric label="Durchschnittsverlust" value={money(data.average_loss, "EUR")} detail="nur verlierende, geschlossene Trades" tone="bad" /></div><div className="rounded-[14px] border border-amber-200 bg-amber-50 p-4 text-sm leading-6 text-amber-900"><AlertTriangle className="mr-2 inline size-4" />Ergebnisse verschiedener Brokerwährungen werden nicht stillschweigend umgerechnet. Für eine belastbare Gesamtwährung müssen alle Trades eine gespeicherte FX-Basis besitzen.</div></div>;
}

function DetailWindow({ children, onClose, entryId }: { children: ReactNode; onClose: () => void; entryId: string }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current;
    dialog?.showModal();
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { dialog?.close(); document.body.style.overflow = previous; };
  }, []);
  useEffect(() => { ref.current?.scrollTo({ top: 0 }); }, [entryId]);
  return <dialog ref={ref} aria-label="Handelsdetails" onCancel={(event) => { event.preventDefault(); onClose(); }} className="fixed inset-0 m-auto max-h-[94dvh] w-[min(1200px,96vw)] overflow-y-auto rounded-[18px] bg-[#f5f7fa] p-0 shadow-2xl backdrop:bg-[#0f172a]/60">
    <div className="sticky top-0 z-10 flex items-center justify-between border-b border-[#dfe6ed] bg-white px-5 py-3"><button type="button" className="inline-flex items-center gap-2 text-sm font-semibold text-[#0f766e]" onClick={onClose}><ArrowLeft size={16} /> Zur Übersicht</button><button type="button" aria-label="Details schließen" className="rounded-full p-2 hover:bg-slate-100" onClick={onClose}><X size={20} /></button></div>
    <div className="p-3 md:p-5">{children}</div>
  </dialog>;
}

function Pagination({ total, offset, loading, onPage }: { total: number; offset: number; loading: boolean; onPage: (offset: number) => void }) {
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const page = Math.floor(offset / PAGE_SIZE) + 1;
  return <nav aria-label="Seiten der Handelsübersicht" className="flex flex-wrap items-center justify-between gap-3 border-y border-[#e8edf2] px-4 py-3 text-sm text-[#687386]">
    <span>{total} Ausführungen · {PAGE_SIZE} pro Seite</span>
    <div className="flex items-center gap-2"><button type="button" className="rounded-lg border px-3 py-1.5 disabled:opacity-40" disabled={loading || offset === 0} onClick={() => onPage(0)}>Erste</button><button type="button" className="rounded-lg border px-3 py-1.5 disabled:opacity-40" disabled={loading || offset === 0} onClick={() => onPage(Math.max(0, offset - PAGE_SIZE))}>Zurück</button><label className="flex items-center gap-2">Seite <select aria-label="Seite auswählen" className="rounded-lg border bg-white p-1.5" value={Math.min(page, pages)} disabled={loading} onChange={(event) => onPage((Number(event.target.value) - 1) * PAGE_SIZE)}>{Array.from({ length: pages }, (_, i) => <option key={i} value={i + 1}>{i + 1}</option>)}</select> von {pages}</label><button type="button" className="rounded-lg border px-3 py-1.5 disabled:opacity-40" disabled={loading || page >= pages} onClick={() => onPage(offset + PAGE_SIZE)}>Weiter</button></div>
  </nav>;
}

function EntryDetail({ entry, onEdit, onView }: { entry: TradeJournalEntryDetail; onEdit: () => void; onView: (id: string) => void }) {
  const stock = record(entry.stock_snapshot);
  const assessment = record(stock.assessment || stock);
  const metrics = record(stock.metrics || assessment.metrics);
  const market = record(entry.market_snapshot);
  const portfolio = record(entry.portfolio_snapshot);
  const allocations = Array.isArray(portfolio.allocations) ? portfolio.allocations.map(record) : [];
  const executions = entry.executions?.length ? entry.executions : [entry];
  const reasons = reasonTexts(stock);
  const priceCurrency = text(stock.quote_currency) || "USD";
  const notice = text(stock.context_notice) || text(market.context_notice);
  return <article className="space-y-6 rounded-[18px] border border-[#dfe6ed] bg-white p-5 md:p-6">
    <div className="flex flex-col gap-4 border-b border-[#e8edf2] pb-5 lg:flex-row lg:items-start lg:justify-between"><div><div className="flex flex-wrap items-center gap-2"><h2 className="text-2xl font-semibold text-[#172033]">{entry.instrument_name || entry.ticker}</h2><StatusChip tone="neutral">{entry.ticker}</StatusChip><ExecutionLabel entry={entry} /></div><p className="mt-2 text-sm text-[#687386]">{dateTime(entry)} · {quantity(entry.shares)} Stück zu {money(entry.price, entry.currency)} · {entry.source === "trade_republic" ? "Trade Republic" : "Manueller Nachtrag"}</p><div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-[#687386]"><StatusChip tone={contextTone[entry.context_status]}>{entry.context_label}</StatusChip><span>Kursdaten bis {formatDate(text(stock.data_as_of))}</span></div>{notice && <p className="mt-3 text-sm text-amber-900">{notice}</p>}</div><button className="inline-flex items-center justify-center gap-2 rounded-[9px] border border-[#d8e1ea] px-3 py-2 text-sm font-semibold text-[#304052]" type="button" onClick={onEdit}><NotebookPen size={15} /> {entry.has_note ? "Notiz bearbeiten" : "Notiz ergänzen"}</button></div>
    <section><SectionTitle>Überblick</SectionTitle><div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4"><Metric label="Ausführungspreis" value={money(entry.price, entry.currency)} detail={`${quantity(entry.shares)} Stück`} /><Metric label="Bruttobetrag" value={money(Math.abs(entry.gross_amount ?? gross(entry) ?? 0), entry.currency)} detail={`Gebühren ${money(Math.abs(entry.fees ?? 0), entry.currency)} · Steuern ${money(Math.abs(entry.tax ?? 0), entry.currency)}`} /><Metric label="Realisiertes Ergebnis" value={money(entry.realized_pnl, entry.currency)} detail={entry.realized_pnl == null ? "Noch kein zugeordnetes Verkaufsergebnis" : entry.entry_type === "buy" ? "Ergebnis der zugeordneten Verkäufe" : `${number(entry.realized_pnl_pct)} %`} tone={entry.realized_pnl == null ? "neutral" : entry.realized_pnl >= 0 ? "good" : "bad"} /><Metric label="Bestand dieses Kauflots" value={entry.entry_type === "buy" ? `${quantity(numeric(portfolio.remaining_shares))} Stück` : statusText(entry.status)} detail={entry.entry_type === "buy" ? "Nach zugeordneten Verkäufen" : "Status der Ausführung"} /></div></section>
    <section><SectionTitle>Ausführungen dieser Position</SectionTitle><p className="mb-3 text-sm text-[#687386]">Käufe, Nachkäufe und Verkäufe gemeinsam. Öffne eine Ausführung für ihre damaligen Aktien- und Marktdaten.</p><div className="overflow-x-auto"><table className="w-full min-w-[640px] text-sm"><thead><tr className="bg-slate-50 text-left text-xs text-[#7a8798]">{["Kauf- / Verkaufsdatum", "Art", "Stück", "Preis", "Ergebnis", ""].map((label) => <th key={label} className="p-3">{label}</th>)}</tr></thead><tbody>{executions.map((item) => <tr key={item.id} className={item.id === entry.id ? "bg-teal-50" : ""}><td className="border-t p-3">{dateTime(item)}</td><td className="border-t p-3"><ExecutionLabel entry={item} /></td><td className="border-t p-3">{quantity(item.shares)}</td><td className="border-t p-3">{money(item.price, item.currency)}</td><td className={clsx("border-t p-3", resultColor(item.realized_pnl))}>{item.entry_type === "sell" ? money(item.realized_pnl, item.currency) : "—"}</td><td className="border-t p-3"><button type="button" className="font-semibold text-[#0f766e] hover:underline" onClick={() => onView(item.id)} aria-label={`${item.entry_type === "buy" ? "Kauf" : "Verkauf"} vom ${formatDate(item.trade_date)} öffnen`}>{item.id === entry.id ? "Ausgewählt" : "Details"}</button></td></tr>)}</tbody></table></div></section>
    <section><SectionTitle>Aktie damals · {formatDate(text(stock.data_as_of) || text(assessment.as_of))}</SectionTitle><p className="mb-3 text-sm text-[#687386]">{(stock.context_status === "archived" || entry.context_status === "archived") ? "Gespeicherte damalige Bewertung." : "Aus historischen Daten mit heutigen Bewertungsregeln rekonstruiert. Teilwerte bleiben sichtbar, auch wenn die Gesamtbewertung unvollständig ist."}</p><div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4"><ScoreMetric label="Gesamtscore" assessment={assessment} component="overall" /><ScoreMetric label="Technisch" assessment={assessment} component="technical" /><ScoreMetric label="Fundamental" assessment={assessment} component="fundamental" /><ScoreMetric label="Chart / Trend" assessment={assessment} component="chart" /></div><div className="mt-3 grid gap-3 sm:grid-cols-2 xl:grid-cols-4"><Metric label="Schlusskurs" value={money(numeric(metrics.last_close), priceCurrency)} detail="Börsenwährung; unabhängig von der Brokerwährung" /><Metric label="Tagesänderung" value={percent(metrics.daily_return_pct ?? metrics.change_pct)} detail="Letzte gespeicherte Sitzung" /><Metric label="50- / 200-Tage-Linie" value={`${number(numeric(metrics.sma50))} / ${number(numeric(metrics.sma200))}`} detail="Aus gespeicherten Schlusskursen" /><Metric label="RS-Rating" value={number(numeric(record(stock.relative_strength).rating) ?? numeric(metrics.rs_rating))} detail="Historischer relativer Stärkevergleich" /></div>{reasons.length > 0 && <NoticeList title="Grenzen der historischen Aktienbewertung" items={reasons} />}{Array.isArray(assessment.warnings) && <NoticeList title="Warnungen zur Aktie" items={assessment.warnings.map(text)} />}{!Object.keys(stock).length && <UnknownBlock text="Keine historischen Aktienwerte vorhanden. Historie ergänzen und Datenlücken prüfen." />}</section>
    <section><SectionTitle>Markt damals</SectionTitle>{Object.keys(market).length ? <MarketContext value={market} /> : <UnknownBlock text="Kein verlässlicher Marktkontext gespeichert." />}</section>
    {allocations.length > 0 && <section><SectionTitle>Kauf- und Verkaufszuordnung (FIFO)</SectionTitle><div className="overflow-x-auto rounded-[12px] border border-[#e1e7ed]"><table className="w-full min-w-[700px] text-sm"><thead><tr className="bg-[#f7f9fb] text-left text-xs text-[#7a8798]">{["Kaufdatum", "Verkaufsdatum", "Stück", "Kostenbasis", "Nettoerlös", "Ergebnis"].map((label) => <th key={label} className="p-3">{label}</th>)}</tr></thead><tbody>{allocations.map((item, index) => { const buy = executions.find((execution) => execution.source_transaction_id === item.buy_transaction_id); return <tr key={index}><td className="border-t p-3">{buy ? <button type="button" className="text-[#0f766e] hover:underline" onClick={() => onView(buy.id)}>{formatDate(text(item.buy_date))}</button> : formatDate(text(item.buy_date))}</td><td className="border-t p-3">{formatDate(entry.trade_date)}</td><td className="border-t p-3">{quantity(numeric(item.shares))}</td><td className="border-t p-3">{money(numeric(item.cost_basis), entry.currency)}</td><td className="border-t p-3">{money(numeric(item.net_proceeds), entry.currency)}</td><td className={clsx("border-t p-3 font-semibold", resultColor(numeric(item.pnl)))}>{money(numeric(item.pnl), entry.currency)}</td></tr>; })}</tbody></table></div></section>}
    <section><SectionTitle>Notizen & Nachbereitung</SectionTitle><div className="grid gap-3 md:grid-cols-2"><TextCard title="Entscheidungsgrund" value={entry.entry_type === "sell" ? entry.sell_reason : entry.primary_reasons || (entry.basis_text.startsWith("Automatisch aus Trade-Republic") ? "" : entry.basis_text)} /><TextCard title="Nachbereitung" value={Object.keys(entry.questionnaire).length ? Object.entries(entry.questionnaire).map(([key, value]) => `${key}: ${String(value)}`).join("\n") : "Noch keine Nachbereitung."} /></div></section>
    <section><SectionTitle>Datenbasis</SectionTitle><div className="grid gap-3 md:grid-cols-2"><Metric label="Verwendeter Handelstag" value={formatDate(text(stock.data_as_of))} detail="Letzte abgeschlossene US-Börsensitzung vor der Ausführung. Intraday-Daten sind nicht archiviert." /><Metric label="Erfasst" value={formatDateTime(entry.created_at)} detail={entry.source === "trade_republic" ? "Aus der Brokerabrechnung übernommen" : "Manuell erfasst"} /></div></section>
  </article>;
}

function ScoreMetric({ label, assessment, component }: { label: string; assessment: Record<string, unknown>; component: string }) {
  const current = record(assessment[`${component}_v2`]);
  const legacy = record(assessment.scores);
  const value = Object.keys(current).length ? current.score : legacy[component === "chart" ? "chart_behavior" : component];
  const status = text(current.status);
  return <Metric label={label} value={numeric(value) == null ? "Nicht belegbar" : `${number(numeric(value))} / 100`} detail={status === "partial" ? "Teilbewertung · Daten fehlen" : status === "missing" ? "Historische Daten fehlen" : numeric(value) == null ? "Keine vollständige historische Bewertung" : "Aus damaliger Datenbasis"} />;
}

function MarketContext({ value }: { value: Record<string, unknown> }) {
  const ampel = record(value.ampel);
  const stored = record(ampel.metrics_json);
  const trend = record(value.trend || stored.trend_ampel);
  const breadth = record(value.breadth);
  const benchmark = record(value.benchmark || value.overview);
  const checks = Array.isArray(value.warning_checks) ? value.warning_checks.map(record) : [];
  const active = checks.filter((check) => check.active_warning);
  const marketChecks = Array.isArray(value.market_warning_checks) ? value.market_warning_checks.map(record) : [];
  const marketActive = marketChecks.filter((check) => check.active_warning);
  const phase = text(trend.phase_label || ampel.phase_label || ampel.ampel_phase || ampel.phase) || "Nicht belegt";
  return <div className="space-y-3"><div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4"><Metric label="Marktphase" value={phase} detail={`${formatDate(text(trend.as_of || ampel.date || ampel.as_of || value.data_as_of))} · ${text(trend.phase_reason || stored.action)}`} /><Metric label="Marktwarnungen" value={marketChecks.length ? String(marketActive.length) : number(numeric(ampel.warning_count))} detail={marketChecks.length ? `Gespeichertes Marktumfeld vom ${formatDate(text(ampel.date || value.data_as_of))}` : "Gespeicherte Anzahl; Einzelprüfungen nicht archiviert"} /><Metric label="Benchmark-Rendite" value={percent(benchmark.daily_return_pct)} detail={`${text(benchmark.instrument || benchmark.ticker) || "SPY"} · ${formatDate(text(benchmark.as_of || value.data_as_of))}`} /><Metric label="Volatilität" value={text(ampel.volatility_regime) || "Nicht belegt"} detail={`Marktbreite: ${text(ampel.breadth_mode) || "Nicht belegt"}`} /></div>{Object.keys(breadth).length > 0 && <div className="grid gap-3 sm:grid-cols-3"><Metric label="Aktien über 50-Tage-Linie" value={percent(breadth.pct_above_50sma)} detail={formatDate(text(breadth.date))} /><Metric label="Aktien über 200-Tage-Linie" value={percent(breadth.pct_above_200sma)} detail={formatDate(text(breadth.date))} /><Metric label="Neue Hochs / Tiefs" value={`${number(numeric(breadth.new_highs))} / ${number(numeric(breadth.new_lows))}`} detail="Gespeicherte Marktbreite" /></div>}{marketChecks.length > 0 && <NoticeList title="Aktive Warnungen im damaligen Marktumfeld" items={marketActive.length ? marketActive.map((check) => `${text(check.label)}: ${text(check.detail)}`) : ["Keine aktive Warnung im gespeicherten Marktumfeld."]} />}{checks.length > 0 ? <><NoticeList title="Zusätzliche Indexwarnungen" items={active.length ? active.map((check) => `${text(check.label)}: ${text(check.detail)}`) : ["Keine aktive Warnung in den verfügbaren Indexprüfungen."]} /><p className="text-xs leading-5 text-[#7a8798]">{text(value.warning_scope)}</p><details className="rounded-lg border p-3 text-sm text-[#526174]"><summary className="cursor-pointer font-semibold">Alle {checks.length} Indexprüfungen</summary><ul className="mt-3 space-y-2">{checks.map((check, index) => <li key={index}>{check.active_warning ? "⚠" : "✓"} {text(check.label)}: {text(check.detail)}</li>)}</ul></details></> : <UnknownBlock text="Die damaligen Einzelwarnungen fehlen. Mit „Historie ergänzen“ können sie aus historischen Indexkursen rekonstruiert werden." />}<NoticeList title="Datenlücken im Marktumfeld" items={reasonTexts(value)} /></div>;
}

function NoticeList({ title, items }: { title: string; items: string[] }) {
  if (!items.length) return null;
  return <div className="mt-3 rounded-[12px] border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900"><div className="font-semibold">{title}</div><ul className="mt-2 list-disc space-y-1 pl-5">{items.map((item, index) => <li key={index}>{item}</li>)}</ul></div>;
}

const REASON_LABELS: Record<string, string> = {
  price_history_below_200_sessions: "Weniger als 200 historische Kurstage; langfristige Trendbewertung unvollständig.",
  fundamentals_missing: "Kein unverändert gespeicherter Fundamentaldatenstand vor der Ausführung verfügbar. Später aktualisierte Werte werden ausgeschlossen.",
  fundamental_publication_time_unverified: "Fundamentaldaten waren vor der Ausführung gespeichert; der genaue Veröffentlichungszeitpunkt ist nicht belegt.",
  rs_rating_missing: "Kein historisches RS-Rating vorhanden. Die RS-Linie wird aus den Kursen rekonstruiert.",
  published_13f_missing: "Keine vor diesem Stichtag veröffentlichten institutionellen 13F-Daten gespeichert.",
  market_snapshot_missing: "Kein damaliger Marktstatus gespeichert.", breadth_missing: "Historische Marktbreite fehlt.",
  benchmark_prices_missing: "Historische Benchmark-Kurse fehlen.", stock_prices_stale: "Aktienkurse reichen nicht bis zum vorgesehenen Handelstag.",
  market_snapshot_stale: "Marktstatus stammt aus einer früheren Sitzung.", breadth_stale: "Marktbreite stammt aus einer früheren Sitzung.",
  benchmark_prices_stale: "Benchmark-Kurse stammen aus einer früheren Sitzung.", market_warning_history_missing: "Für einzelne Marktwarnungen fehlen ausreichende historische Indexkurse."
};
function reasonTexts(value: Record<string, unknown>): string[] { const reasons = record(value.data_quality).reason_codes; return Array.isArray(reasons) ? reasons.map((reason) => REASON_LABELS[text(reason)] || `Datenlücke: ${text(reason)}`) : []; }
function percent(value: unknown): string { return numeric(value) == null ? "—" : `${number(numeric(value))} %`; }
function formatDate(value: string): string { if (!value) return "Nicht belegt"; const date = new Date(`${value.slice(0, 10)}T12:00:00`); return Number.isNaN(date.valueOf()) ? "Nicht belegt" : new Intl.DateTimeFormat("de-DE", { dateStyle: "medium", timeZone: "Europe/Berlin" }).format(date); }

function EntryDialog({ dialog, pending, error, onClose, onChange, onSave }: { dialog: { draft: Draft; entry: TradeJournalEntryDetail | null }; pending: boolean; error: unknown; onClose: () => void; onChange: (draft: Draft) => void; onSave: () => void }) {
  const draft = dialog.draft;
  const broker = dialog.entry?.source === "trade_republic";
  const patch = (value: Partial<Draft>) => onChange({ ...draft, ...value });
  function submit(event: FormEvent) { event.preventDefault(); onSave(); }
  return <div className="fixed inset-0 z-50 overflow-y-auto bg-[#0f172a]/55 p-3 backdrop-blur-sm md:p-8" role="dialog" aria-modal="true" aria-label={dialog.entry ? "Notiz bearbeiten" : "Manueller Nachtrag"}><form className="mx-auto max-w-4xl rounded-[18px] bg-white shadow-2xl" onSubmit={submit}><div className="flex items-center justify-between border-b border-[#e8edf2] px-5 py-4"><div><h2 className="text-xl font-semibold text-[#172033]">{broker ? "Notiz zur Broker-Ausführung" : dialog.entry ? "Manuellen Eintrag bearbeiten" : "Manueller Nachtrag"}</h2><p className="mt-1 text-sm text-[#687386]">{broker ? "Ausführungsdaten und FIFO-Ergebnis bleiben unverändert." : "Fehlende Ausführung ergänzen; spätere CSV-Treffer werden nicht automatisch verschmolzen."}</p></div><button aria-label="Dialog schließen" className="rounded-full p-2 text-[#687386] hover:bg-[#f0f3f6]" type="button" onClick={onClose}><X size={20} /></button></div><div className="space-y-5 p-5">{!broker && <><div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4"><Field label="Ticker *"><input required className="input-light uppercase" value={draft.ticker} onChange={(event) => patch({ ticker: event.target.value.toUpperCase() })} /></Field><Field label="Ausführung *"><select className="input-light" value={draft.entry_type} onChange={(event) => patch({ entry_type: event.target.value as TradeJournalEntryType })}><option value="buy">Kauf</option><option value="sell">Verkauf</option><option value="ex_post">Nachbereitung</option></select></Field><Field label="Handelsdatum *"><input required className="input-light" type="date" value={draft.trade_date} onChange={(event) => patch({ trade_date: event.target.value })} /></Field><Field label="Währung *"><input required className="input-light uppercase" maxLength={8} value={draft.currency} onChange={(event) => patch({ currency: event.target.value.toUpperCase() })} /></Field></div><div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5"><Field label="Preis *"><input required className="input-light" inputMode="decimal" value={draft.price} onChange={(event) => patch({ price: event.target.value })} /></Field><Field label="Stückzahl *"><input required className="input-light" inputMode="decimal" value={draft.shares} onChange={(event) => patch({ shares: event.target.value })} /></Field><Field label="Gebühren"><input className="input-light" inputMode="decimal" value={draft.fees} onChange={(event) => patch({ fees: event.target.value })} /></Field><Field label="Steuern"><input className="input-light" inputMode="decimal" value={draft.tax} onChange={(event) => patch({ tax: event.target.value })} /></Field><Field label="Stopp"><input className="input-light" inputMode="decimal" value={draft.stop_price} onChange={(event) => patch({ stop_price: event.target.value })} /></Field></div><Field label="Quelle / Beleg"><input className="input-light" value={draft.source_evidence} placeholder="z. B. Abrechnung vom …" onChange={(event) => patch({ source_evidence: event.target.value })} /></Field></>}<Field label={draft.entry_type === "sell" ? "Verkaufsgrund / Notiz" : "Entscheidungsgrund / Notiz"}><textarea className="input-light min-h-36" value={draft.note} onChange={(event) => patch({ note: event.target.value })} /></Field>{Boolean(error) && <ErrorPanel>Speichern fehlgeschlagen: {(error as Error).message}</ErrorPanel>}<div className="flex justify-end gap-2"><button className="rounded-[9px] border border-[#d8e1ea] px-4 py-2 text-sm font-semibold text-[#526174]" type="button" onClick={onClose}>Abbrechen</button><button className="rounded-[9px] bg-[#0f766e] px-4 py-2 text-sm font-semibold !text-white disabled:opacity-50" disabled={pending} type="submit">{pending ? "Speichert…" : "Speichern"}</button></div></div></form></div>;
}

function HeaderStat({ label, value, detail }: { label: string; value: string; detail: string }) { return <div><div className="text-xs font-semibold uppercase tracking-[0.1em] text-[#7a8798]">{label}</div><div className="mt-1 text-xl font-semibold tabular-nums text-[#172033]">{value}</div><div className="text-xs text-[#7a8798]">{detail}</div></div>; }
function BarChart3Icon() { return <span aria-hidden="true" className="text-base leading-none">↗</span>; }
function FilterSelect({ label, value, onChange, options }: { label: string; value: string; onChange: (value: string) => void; options: string[][] }) { return <label><span className="sr-only">{label}</span><select className="h-9 w-full rounded-[9px] border border-[#d8e1ea] bg-white px-2 text-sm text-[#304052]" value={value} onChange={(event) => onChange(event.target.value)}>{options.map(([key, item]) => <option key={key} value={key}>{item}</option>)}</select></label>; }
function ExecutionLabel({ entry }: { entry: TradeJournalEntrySummary }) { return <span className={clsx("inline-flex rounded-full px-2 py-1 text-xs font-semibold", entry.entry_type === "sell" ? "bg-rose-50 text-rose-700" : entry.entry_type === "buy" ? "bg-emerald-50 text-emerald-700" : "bg-slate-100 text-slate-700")}>{executionText(entry)}</span>; }
function Metric({ label, value, detail, tone = "neutral" }: { label: string; value: string; detail: string; tone?: Tone }) { return <div className="rounded-[14px] border border-[#e1e7ed] bg-[#fafcfd] p-4"><div className="text-xs font-semibold uppercase tracking-[0.08em] text-[#7a8798]">{label}</div><div className={clsx("mt-2 text-xl font-semibold tabular-nums", tone === "good" ? "text-[#138a57]" : tone === "bad" ? "text-[#c2413b]" : "text-[#172033]")}>{value}</div><div className="mt-1 text-xs leading-5 text-[#7a8798]">{detail}</div></div>; }
function SmallValue({ label, value }: { label: string; value: string }) { return <div><div className="text-xs uppercase text-[#8a96a8]">{label}</div><div className="mt-1 font-medium tabular-nums text-[#304052]">{value}</div></div>; }
function SectionTitle({ children }: { children: ReactNode }) { return <h3 className="mb-3 text-base font-semibold text-[#172033]">{children}</h3>; }
function TextCard({ title, value }: { title: string; value: string }) { return <div className="rounded-[14px] border border-[#e1e7ed] p-4"><div className="text-xs font-semibold uppercase tracking-[0.08em] text-[#7a8798]">{title}</div><div className="mt-2 whitespace-pre-wrap text-sm leading-6 text-[#304052]">{value || "Noch keine Notiz."}</div></div>; }
function UnknownBlock({ text: value }: { text: string }) { return <div className="flex items-start gap-2 rounded-[12px] border border-[#dfe6ed] bg-[#f7f9fb] p-4 text-sm text-[#526174]"><CircleHelp className="mt-0.5 size-4 shrink-0" />{value}</div>; }
function ErrorPanel({ children }: { children: ReactNode }) { return <div className="rounded-[12px] border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800">{children}</div>; }
function EmptyState({ title, text: value }: { title: string; text: string }) { return <div className="grid min-h-48 place-items-center rounded-[14px] border border-dashed border-[#d8e1ea] p-6 text-center"><div><FileText className="mx-auto size-8 text-[#a5b0bd]" /><div className="mt-3 font-semibold text-[#304052]">{title}</div><p className="mt-1 text-sm text-[#7a8798]">{value}</p></div></div>; }
function LoadingRows() { return <div className="space-y-2">{[0, 1, 2, 3].map((item) => <div key={item} className="h-16 animate-pulse rounded-[12px] bg-[#f1f4f7]" />)}</div>; }
function Field({ label, children }: { label: string; children: ReactNode }) { return <label className="block"><span className="mb-1 block text-xs font-semibold uppercase tracking-[0.06em] text-[#687386]">{label}</span>{children}</label>; }

function emptyDraft(ticker: string, type: TradeJournalEntryType): Draft { return { ticker, entry_type: type, trade_date: berlinDate(), price: "", shares: "", currency: "EUR", fees: "", tax: "", source_evidence: "", note: "", stop_price: "" }; }
function entryDraft(entry: TradeJournalEntryDetail): Draft { const portfolio = record(entry.portfolio_snapshot); return { ticker: entry.ticker, entry_type: entry.entry_type, trade_date: entry.trade_date, price: stringNumber(entry.price), shares: stringNumber(entry.shares), currency: entry.currency || "USD", fees: stringNumber(entry.fees), tax: stringNumber(entry.tax), source_evidence: text(portfolio.source_evidence), note: entry.entry_type === "sell" ? entry.sell_reason : entry.primary_reasons || entry.basis_text, stop_price: stringNumber(entry.stop_price) }; }
function draftToRequest(draft: Draft): TradeJournalEntryRequest { return { ticker: draft.ticker.trim().toUpperCase(), entry_type: draft.entry_type, trade_date: draft.trade_date, price: parseNumber(draft.price), shares: parseNumber(draft.shares), currency: draft.currency.trim().toUpperCase(), fees: parseNumber(draft.fees), tax: parseNumber(draft.tax), source_evidence: draft.source_evidence, stop_price: parseNumber(draft.stop_price), status: draft.entry_type === "buy" ? "open" : "closed", primary_reasons: draft.entry_type === "sell" ? "" : draft.note, sell_reason: draft.entry_type === "sell" ? draft.note : "", basis_text: draft.entry_type === "buy" ? draft.note : "", questionnaire: {}, chart_images: { daily_chart: "", weekly_chart: "" } }; }
function parseTab(value: string | null): Tab { return value === "analytics" ? value : "executions"; }
function parseNumber(value: string): number | null { const parsed = Number(value.replace(",", ".")); return value.trim() && Number.isFinite(parsed) ? parsed : null; }
function stringNumber(value: number | null | undefined): string { return value == null ? "" : String(value); }
function record(value: unknown): Record<string, unknown> { return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {}; }
function text(value: unknown): string { return typeof value === "string" || typeof value === "number" ? String(value) : ""; }
function numeric(value: unknown): number | null { return typeof value === "number" && Number.isFinite(value) ? value : null; }
function number(value: number | null | undefined): string { return value == null ? "—" : new Intl.NumberFormat("de-DE", { maximumFractionDigits: 2 }).format(value); }
function quantity(value: number | null | undefined): string { return value == null ? "—" : new Intl.NumberFormat("de-DE", { maximumFractionDigits: 8 }).format(value); }
function money(value: number | null | undefined, currency = "USD"): string { if (value == null) return "—"; try { return new Intl.NumberFormat("de-DE", { style: "currency", currency: currency || "USD", maximumFractionDigits: 2 }).format(value); } catch { return `${number(value)} ${currency}`; } }
function gross(entry: TradeJournalEntrySummary): number | null { return entry.price != null && entry.shares != null ? entry.price * entry.shares : null; }
function dateTime(entry: TradeJournalEntrySummary): string { if (entry.execution_at && !entry.execution_at.endsWith("T00:00:00")) return formatDateTime(entry.execution_at); return new Intl.DateTimeFormat("de-DE").format(new Date(`${entry.trade_date}T12:00:00`)); }
function formatDateTime(value: string): string { const date = new Date(value); return Number.isNaN(date.valueOf()) ? value : new Intl.DateTimeFormat("de-DE", { dateStyle: "medium", timeStyle: "short", timeZone: "Europe/Berlin" }).format(date); }
function executionText(entry: TradeJournalEntrySummary): string { if (entry.entry_type === "ex_post") return "Nachbereitung"; if (entry.entry_type === "sell") return "Verkauf / Teilverkauf"; return entry.trade_group_id ? "Kauf / Nachkauf" : "Kauf"; }
function statusText(value: TradeJournalEntryStatus): string { return value === "open" ? "Offen" : value === "closed" ? "Abgeschlossen" : "Zuordnung offen"; }
function resultColor(value: number | null | undefined): string { return value == null ? "text-[#687386]" : value >= 0 ? "text-[#138a57]" : "text-[#c2413b]"; }
