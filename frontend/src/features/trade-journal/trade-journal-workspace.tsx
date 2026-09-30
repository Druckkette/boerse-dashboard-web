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
import { FormEvent, ReactNode, useMemo, useState } from "react";
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
  TradeJournalFilters,
  TradeJournalTradeSummary
} from "@/lib/types/api";

type Tab = "executions" | "trades" | "analytics";
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
    limit: 50,
    offset: Math.max(0, Number(searchParams.get("offset") ?? 0) || 0)
  }), [searchParams]);
  const [searchInput, setSearchInput] = useState(filters.query ?? "");
  const [dialog, setDialog] = useState<{ draft: Draft; entry: TradeJournalEntryDetail | null } | null>(null);

  const entriesQuery = useQuery({
    queryKey: ["trade-journal", filters],
    queryFn: () => api.tradeJournalEntries(filters)
  });
  const commonFilters = { query: filters.query, date_from: filters.date_from, date_to: filters.date_to };
  const tradesQuery = useQuery({
    queryKey: ["trade-journal-trades", commonFilters],
    queryFn: () => api.tradeJournalTrades(commonFilters),
    enabled: tab === "trades"
  });
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
      void queryClient.invalidateQueries({ queryKey: ["trade-journal-trades"] });
      navigate({ entry: result.entry.id });
    }
  });
  const backfillMutation = useMutation({
    mutationFn: () => api.startJob({ type: "backfill_trade_journal_contexts", payload: { limit: 500, source: "trade_journal" } })
  });

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
            <button className="inline-flex h-10 items-center justify-center gap-2 rounded-[10px] border border-[#cfd9e3] px-4 text-sm font-semibold text-[#304052] hover:bg-[#f6f8fb] disabled:opacity-50" disabled={backfillMutation.isPending} type="button" onClick={() => backfillMutation.mutate()}>
              <BarChart3Icon /> {backfillMutation.isPending ? "Wird gestartet…" : "Historie ergänzen"}
            </button>
          </div>
        </div>
        {backfillMutation.data && <p className="mt-3 text-sm text-[#0f766e]">Hintergrundjob gestartet. Fortschritt und Fehlgründe sind unter Jobs sichtbar.</p>}
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
          ], ["trades", "Trades"], ["analytics", "Auswertung"]] as Array<[Tab, string]>).map(([key, label]) => (
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

        <div className="p-4">
          {tab === "executions" && <ExecutionTable entries={entries} loading={entriesQuery.isLoading} onView={(id) => navigate({ entry: id })} />}
          {tab === "trades" && <TradeTable loading={tradesQuery.isLoading} trades={tradesQuery.data?.trades ?? []} onView={(id) => navigate({ entry: id })} />}
          {tab === "analytics" && <AnalyticsPanel data={analyticsQuery.data} loading={analyticsQuery.isLoading} />}
        </div>

        {tab === "executions" && !entriesQuery.isLoading && (
          <div className="flex flex-col gap-3 border-t border-[#e8edf2] px-4 py-3 text-sm text-[#687386] sm:flex-row sm:items-center sm:justify-between">
            <span>{entriesQuery.data?.total ?? 0} Treffer · {entries.length ? (filters.offset ?? 0) + 1 : 0}–{Math.min((filters.offset ?? 0) + entries.length, entriesQuery.data?.total ?? 0)}</span>
            <div className="flex gap-2">
              <button className="rounded-[8px] border border-[#d8e1ea] px-3 py-1.5 disabled:opacity-40" disabled={(filters.offset ?? 0) === 0} type="button" onClick={() => navigate({ offset: Math.max(0, (filters.offset ?? 0) - 50), entry: null })}>Zurück</button>
              <button className="rounded-[8px] border border-[#d8e1ea] px-3 py-1.5 disabled:opacity-40" disabled={entriesQuery.data?.next_offset == null} type="button" onClick={() => navigate({ offset: entriesQuery.data?.next_offset, entry: null })}>Weitere laden</button>
            </div>
          </div>
        )}
      </section>

      {entriesQuery.isError && <ErrorPanel>Ausführungen konnten nicht geladen werden: {(entriesQuery.error as Error).message}</ErrorPanel>}

      {selectedId && (
        <section className="space-y-3">
          <button className="inline-flex items-center gap-2 text-sm font-semibold text-[#0f766e] hover:underline" type="button" onClick={() => navigate({ entry: null })}><ArrowLeft size={15} /> Zur Übersicht</button>
          {selectedQuery.isLoading ? <div className="h-72 animate-pulse rounded-[16px] bg-white" /> : selectedQuery.data?.entry ? <EntryDetail entry={selectedQuery.data.entry} onEdit={() => openEdit(selectedQuery.data.entry)} /> : <ErrorPanel>Der Eintrag konnte nicht geladen werden.</ErrorPanel>}
        </section>
      )}

      {dialog && <EntryDialog dialog={dialog} pending={saveMutation.isPending} error={saveMutation.error} onClose={() => setDialog(null)} onChange={(draft) => setDialog({ ...dialog, draft })} onSave={() => saveMutation.mutate(dialog)} />}
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
          <thead><tr className="text-left text-xs font-semibold uppercase tracking-[0.08em] text-[#7a8798]">{["Zeitpunkt", "Aktie", "Ausführung", "Stückzahl", "Preis", "Betrag", "Ergebnis", "Bewertung", "Notiz", ""].map((label) => <th key={label} className="border-b border-[#e8edf2] px-3 py-3">{label}</th>)}</tr></thead>
          <tbody>{entries.map((entry) => <tr key={entry.id} className="group cursor-pointer hover:bg-[#f7fafb]" onClick={() => onView(entry.id)}><td className="border-b border-[#edf1f5] px-3 py-3 tabular-nums text-[#526174]">{dateTime(entry)}</td><td className="border-b border-[#edf1f5] px-3 py-3"><div className="font-semibold text-[#172033]">{entry.instrument_name || entry.ticker}</div><div className="text-xs text-[#7a8798]">{entry.ticker}{entry.isin ? ` · ${entry.isin}` : ""}</div></td><td className="border-b border-[#edf1f5] px-3 py-3"><ExecutionLabel entry={entry} /></td><td className="border-b border-[#edf1f5] px-3 py-3 text-right tabular-nums">{quantity(entry.shares)}</td><td className="border-b border-[#edf1f5] px-3 py-3 text-right tabular-nums">{money(entry.price, entry.currency)}</td><td className="border-b border-[#edf1f5] px-3 py-3 text-right tabular-nums">{money(entry.gross_amount ?? gross(entry), entry.currency)}</td><td className={clsx("border-b border-[#edf1f5] px-3 py-3 text-right font-semibold tabular-nums", resultColor(entry.realized_pnl))}>{entry.entry_type === "sell" ? money(entry.realized_pnl, entry.currency) : <span className="font-normal text-[#9aa5b3]" title="Ergebnis entsteht erst bei einem Verkauf">—</span>}</td><td className="border-b border-[#edf1f5] px-3 py-3"><StatusChip tone={contextTone[entry.context_status]}>{entry.context_label}</StatusChip></td><td className="border-b border-[#edf1f5] px-3 py-3 text-center"><span className="sr-only">{entry.has_note ? "Notiz vorhanden" : "Keine Notiz"}</span><NotebookPen className={clsx("mx-auto size-4", entry.has_note ? "text-[#0f766e]" : "text-[#c4ccd5]")} /></td><td className="border-b border-[#edf1f5] px-3 py-3"><ChevronRight className="size-4 text-[#a6b0bd] group-hover:text-[#0f766e]" /></td></tr>)}</tbody>
        </table>
      </div>
      <div className="space-y-3 md:hidden">{entries.map((entry) => <button key={entry.id} className="w-full rounded-[14px] border border-[#e1e7ed] p-4 text-left" type="button" onClick={() => onView(entry.id)}><div className="flex items-start justify-between gap-3"><div><div className="font-semibold text-[#172033]">{entry.instrument_name || entry.ticker}</div><div className="mt-1 text-xs text-[#7a8798]">{dateTime(entry)} · {entry.ticker}</div></div><StatusChip tone={contextTone[entry.context_status]}>{entry.context_label}</StatusChip></div><div className="mt-4 grid grid-cols-3 gap-3 text-sm"><SmallValue label="Ausführung" value={executionText(entry)} /><SmallValue label="Stück" value={quantity(entry.shares)} /><SmallValue label="Preis" value={money(entry.price, entry.currency)} /></div></button>)}</div>
    </>
  );
}

function TradeTable({ trades, loading, onView }: { trades: TradeJournalTradeSummary[]; loading: boolean; onView: (id: string) => void }) {
  if (loading) return <LoadingRows />;
  if (!trades.length) return <EmptyState title="Keine Trades gefunden" text="Trades entstehen aus Positionszyklen mit Käufen, Nachkäufen und Teilverkäufen." />;
  return <div className="space-y-3">{trades.map((trade) => <article key={trade.id} className="rounded-[14px] border border-[#e1e7ed] p-4"><div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between"><div><div className="flex items-center gap-2"><h3 className="text-lg font-semibold text-[#172033]">{trade.ticker}</h3><StatusChip tone={trade.status === "closed" ? "good" : "warning"}>{trade.status === "closed" ? "Abgeschlossen" : trade.status === "partial" ? "Teilverkauft" : "Offen"}</StatusChip><StatusChip tone={contextTone[trade.context_status]}>{contextLabel(trade.context_status)}</StatusChip></div><p className="mt-1 text-sm text-[#687386]">{trade.first_entry_date}{trade.last_exit_date ? ` bis ${trade.last_exit_date}` : ""} · {trade.execution_count} Ausführungen</p></div><div className={clsx("text-lg font-semibold tabular-nums", resultColor(trade.realized_pnl))}>{money(trade.realized_pnl, trade.currency)}</div></div><div className="mt-4 grid gap-3 sm:grid-cols-4"><SmallValue label="Gekauft" value={`${quantity(trade.bought_shares)} Stk.`} /><SmallValue label="Verkauft" value={`${quantity(trade.sold_shares)} Stk.`} /><SmallValue label="Restbestand" value={`${quantity(trade.remaining_shares)} Stk.`} /><SmallValue label="Nachbereitung" value={trade.has_review ? "Vorhanden" : "Offen"} /></div><ol className="mt-4 border-l-2 border-[#dbe4ea] pl-4">{trade.executions.map((entry) => <li key={entry.id} className="relative mb-2 last:mb-0"><span className="absolute -left-[21px] top-2 size-2.5 rounded-full border-2 border-white bg-[#0f766e]" /><button className="flex w-full items-center justify-between gap-3 rounded-[8px] px-2 py-1.5 text-left hover:bg-[#f4f7f9]" type="button" onClick={() => onView(entry.id)}><span className="text-sm text-[#304052]">{entry.trade_date} · {executionText(entry)} · {quantity(entry.shares)} Stk. zu {money(entry.price, entry.currency)}</span><ChevronRight className="size-4 shrink-0 text-[#a6b0bd]" /></button></li>)}</ol></article>)}</div>;
}

function AnalyticsPanel({ data, loading }: { data?: TradeJournalAnalytics; loading: boolean }) {
  if (loading) return <LoadingRows />;
  if (!data) return <EmptyState title="Keine Auswertung verfügbar" text="Die Kennzahlen werden serverseitig über alle gefilterten Trades berechnet." />;
  return <div className="space-y-4"><div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4"><Metric label="Geschlossene Trades" value={String(data.closed_trades)} detail={`${data.excluded_incomplete} ohne vollständige Kostenbasis ausgeschlossen`} /><Metric label="Nettoergebnis" value={money(data.net_result, "EUR")} detail="Summe der Tradeergebnisse; Währungen im Detail prüfen" tone={data.net_result >= 0 ? "good" : "bad"} /><Metric label="Trefferquote" value={data.hit_rate_pct == null ? "—" : `${number(data.hit_rate_pct)} %`} detail={`${data.winners} Gewinner · ${data.losers} Verlierer`} /><Metric label="Profit Factor" value={data.profit_factor == null ? "—" : number(data.profit_factor)} detail="Bruttogewinne / Bruttoverluste" /></div><div className="grid gap-3 sm:grid-cols-2"><Metric label="Durchschnittsgewinn" value={money(data.average_win, "EUR")} detail="nur gewinnende, geschlossene Trades" tone="good" /><Metric label="Durchschnittsverlust" value={money(data.average_loss, "EUR")} detail="nur verlierende, geschlossene Trades" tone="bad" /></div><div className="rounded-[14px] border border-amber-200 bg-amber-50 p-4 text-sm leading-6 text-amber-900"><AlertTriangle className="mr-2 inline size-4" />Ergebnisse verschiedener Brokerwährungen werden nicht stillschweigend umgerechnet. Für eine belastbare Gesamtwährung müssen alle Trades eine gespeicherte FX-Basis besitzen.</div></div>;
}

function EntryDetail({ entry, onEdit }: { entry: TradeJournalEntryDetail; onEdit: () => void }) {
  const stock = record(entry.stock_snapshot);
  const assessment = record(stock.assessment || stock);
  const scores = record(assessment.scores);
  const market = record(entry.market_snapshot);
  const portfolio = record(entry.portfolio_snapshot);
  const allocations = Array.isArray(portfolio.allocations) ? portfolio.allocations.map(record) : [];
  const notice = text(stock.context_notice) || text(market.context_notice);
  return <article className="space-y-4 rounded-[18px] border border-[#dfe6ed] bg-white p-5 shadow-[0_8px_28px_rgba(15,23,42,0.04)] md:p-6"><div className="flex flex-col gap-4 border-b border-[#e8edf2] pb-5 lg:flex-row lg:items-start lg:justify-between"><div><div className="flex flex-wrap items-center gap-2"><h2 className="text-2xl font-semibold text-[#172033]">{entry.instrument_name || entry.ticker}</h2><StatusChip tone="neutral">{entry.ticker}</StatusChip><ExecutionLabel entry={entry} /></div><p className="mt-2 text-sm text-[#687386]">{dateTime(entry)} · {quantity(entry.shares)} Stück zu {money(entry.price, entry.currency)} · {entry.source === "trade_republic" ? "Trade Republic" : "Manueller Nachtrag"}</p><div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-[#687386]"><StatusChip tone={contextTone[entry.context_status]}>{entry.context_label}</StatusChip><span>Datenstand {text(stock.information_cutoff) || text(stock.generated_at) || "nicht belegt"}</span><span>·</span><span>Erfasst {formatDateTime(entry.created_at)}</span><span>·</span><span>Regeln {text(stock.assessment_version) || "nicht versioniert"}</span></div>{notice && <p className="mt-3 rounded-[10px] border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">{notice}</p>}</div><button className="inline-flex items-center justify-center gap-2 rounded-[9px] border border-[#d8e1ea] px-3 py-2 text-sm font-semibold text-[#304052]" type="button" onClick={onEdit}><NotebookPen size={15} /> {entry.has_note ? "Notiz bearbeiten" : "Notiz ergänzen"}</button></div><section><SectionTitle>Überblick</SectionTitle><div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4"><Metric label="Ausführungspreis" value={money(entry.price, entry.currency)} detail={`${quantity(entry.shares)} Stück`} /><Metric label="Bruttobetrag" value={money(entry.gross_amount ?? gross(entry), entry.currency)} detail={`Gebühren ${money(entry.fees, entry.currency)} · Steuern ${money(entry.tax, entry.currency)}`} /><Metric label="Realisiertes Ergebnis" value={money(entry.realized_pnl, entry.currency)} detail={entry.realized_pnl_pct == null ? "Kostenbasis nicht vollständig" : `${number(entry.realized_pnl_pct)} %`} tone={(entry.realized_pnl ?? 0) >= 0 ? "good" : "bad"} /><Metric label="Positionsstatus" value={statusText(entry.status)} detail={entry.trade_group_id ? `Trade ${entry.trade_group_id.slice(0, 8)}…` : "Manueller Einzelbezug"} /></div></section><section><SectionTitle>Aktie damals</SectionTitle><div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4"><Metric label="Gesamtscore" value={score(scores.overall)} detail="Gesamtbewertung" /><Metric label="Technisch" value={score(scores.technical_v2 ?? scores.technical)} detail="Technische Komponenten" /><Metric label="Fundamental" value={score(scores.fundamental_v2 ?? scores.fundamental)} detail="Veröffentlichungsstand im Snapshot" /><Metric label="Chart / Trend" value={score(scores.chart_v2 ?? scores.chart)} detail="Historische Regelbasis beachten" /></div>{!Object.keys(stock).length && <UnknownBlock text="Keine Aktienbewertung gespeichert. Das ist keine positive Bewertung." />}</section><section><SectionTitle>Markt damals</SectionTitle>{Object.keys(market).length ? <JsonSummary value={market} /> : <UnknownBlock text="Kein verlässlicher Marktkontext gespeichert." />}</section>{allocations.length > 0 && <section><SectionTitle>Ausführungen & FIFO-Zuordnung</SectionTitle><div className="overflow-x-auto rounded-[12px] border border-[#e1e7ed]"><table className="w-full min-w-[700px] text-sm"><thead><tr className="bg-[#f7f9fb] text-left text-xs uppercase text-[#7a8798]"><th className="p-3">Kauflot</th><th className="p-3">Kaufdatum</th><th className="p-3 text-right">Stück</th><th className="p-3 text-right">Kostenbasis</th><th className="p-3 text-right">Nettoerlös</th><th className="p-3 text-right">Ergebnis</th></tr></thead><tbody>{allocations.map((item, index) => <tr key={`${text(item.buy_transaction_id)}-${index}`}><td className="border-t border-[#edf1f5] p-3 font-mono text-xs">{text(item.buy_transaction_id).slice(0, 12) || "—"}</td><td className="border-t border-[#edf1f5] p-3">{text(item.buy_date) || "—"}</td><td className="border-t border-[#edf1f5] p-3 text-right">{quantity(numeric(item.shares))}</td><td className="border-t border-[#edf1f5] p-3 text-right">{money(numeric(item.cost_basis), entry.currency)}</td><td className="border-t border-[#edf1f5] p-3 text-right">{money(numeric(item.net_proceeds), entry.currency)}</td><td className={clsx("border-t border-[#edf1f5] p-3 text-right font-semibold", resultColor(numeric(item.pnl)))}>{money(numeric(item.pnl), entry.currency)}</td></tr>)}</tbody></table></div></section>}<section><SectionTitle>Notizen & Nachbereitung</SectionTitle><div className="grid gap-3 md:grid-cols-2"><TextCard title="Entscheidungsgrund" value={entry.entry_type === "sell" ? entry.sell_reason : entry.primary_reasons || entry.basis_text} /><TextCard title="Nachbereitung" value={Object.keys(entry.questionnaire).length ? Object.entries(entry.questionnaire).map(([key, value]) => `${key}: ${String(value)}`).join("\n") : "Noch keine Nachbereitung."} /></div></section><section><SectionTitle>Datenherkunft</SectionTitle><div className="grid gap-3 md:grid-cols-3"><Metric label="Herkunft" value={entry.context_label} detail={entry.source === "trade_republic" ? "Brokerfakten unveränderlich" : "Manueller Nachtrag"} /><Metric label="Informationsstichtag" value={text(stock.information_cutoff) || "Unbekannt"} detail={text(stock.temporal_reliability) || "Zeitliche Zuverlässigkeit nicht belegt"} /><Metric label="Schema / Regeln" value={text(stock.snapshot_schema) || "Legacy"} detail={text(stock.assessment_version) || "Keine Regelversion gespeichert"} /></div></section></article>;
}

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
function JsonSummary({ value }: { value: Record<string, unknown> }) { const ampel = record(value.ampel); const overview = record(value.overview); return <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4"><Metric label="Marktphase" value={text(ampel.phase_label) || text(ampel.phase) || "Unbekannt"} detail="gespeicherter Marktblock" /><Metric label="Warnungen" value={number(numeric(ampel.warning_count) ?? numeric(value.warning_count))} detail="nur bei vollständig ausgewertetem Satz belastbar" /><Metric label="Benchmark" value={text(overview.ticker) || "S&P 500 / SPY"} detail={text(overview.as_of) || "Stichtag nicht belegt"} /><Metric label="Datenstatus" value={text(value.context_status) || "Legacy"} detail={text(value.temporal_reliability) || "Zeitbasis prüfen"} /></div>; }
function ErrorPanel({ children }: { children: ReactNode }) { return <div className="rounded-[12px] border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800">{children}</div>; }
function EmptyState({ title, text: value }: { title: string; text: string }) { return <div className="grid min-h-48 place-items-center rounded-[14px] border border-dashed border-[#d8e1ea] p-6 text-center"><div><FileText className="mx-auto size-8 text-[#a5b0bd]" /><div className="mt-3 font-semibold text-[#304052]">{title}</div><p className="mt-1 text-sm text-[#7a8798]">{value}</p></div></div>; }
function LoadingRows() { return <div className="space-y-2">{[0, 1, 2, 3].map((item) => <div key={item} className="h-16 animate-pulse rounded-[12px] bg-[#f1f4f7]" />)}</div>; }
function Field({ label, children }: { label: string; children: ReactNode }) { return <label className="block"><span className="mb-1 block text-xs font-semibold uppercase tracking-[0.06em] text-[#687386]">{label}</span>{children}</label>; }

function emptyDraft(ticker: string, type: TradeJournalEntryType): Draft { return { ticker, entry_type: type, trade_date: berlinDate(), price: "", shares: "", currency: "EUR", fees: "", tax: "", source_evidence: "", note: "", stop_price: "" }; }
function entryDraft(entry: TradeJournalEntryDetail): Draft { const portfolio = record(entry.portfolio_snapshot); return { ticker: entry.ticker, entry_type: entry.entry_type, trade_date: entry.trade_date, price: stringNumber(entry.price), shares: stringNumber(entry.shares), currency: entry.currency || "USD", fees: stringNumber(entry.fees), tax: stringNumber(entry.tax), source_evidence: text(portfolio.source_evidence), note: entry.entry_type === "sell" ? entry.sell_reason : entry.primary_reasons || entry.basis_text, stop_price: stringNumber(entry.stop_price) }; }
function draftToRequest(draft: Draft): TradeJournalEntryRequest { return { ticker: draft.ticker.trim().toUpperCase(), entry_type: draft.entry_type, trade_date: draft.trade_date, price: parseNumber(draft.price), shares: parseNumber(draft.shares), currency: draft.currency.trim().toUpperCase(), fees: parseNumber(draft.fees), tax: parseNumber(draft.tax), source_evidence: draft.source_evidence, stop_price: parseNumber(draft.stop_price), status: draft.entry_type === "buy" ? "open" : "closed", primary_reasons: draft.entry_type === "sell" ? "" : draft.note, sell_reason: draft.entry_type === "sell" ? draft.note : "", basis_text: draft.entry_type === "buy" ? draft.note : "", questionnaire: {}, chart_images: { daily_chart: "", weekly_chart: "" } }; }
function parseTab(value: string | null): Tab { return value === "trades" || value === "analytics" ? value : "executions"; }
function parseNumber(value: string): number | null { const parsed = Number(value.replace(",", ".")); return value.trim() && Number.isFinite(parsed) ? parsed : null; }
function stringNumber(value: number | null | undefined): string { return value == null ? "" : String(value); }
function record(value: unknown): Record<string, unknown> { return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {}; }
function text(value: unknown): string { return typeof value === "string" || typeof value === "number" ? String(value) : ""; }
function numeric(value: unknown): number | null { return typeof value === "number" && Number.isFinite(value) ? value : null; }
function number(value: number | null | undefined): string { return value == null ? "—" : new Intl.NumberFormat("de-DE", { maximumFractionDigits: 2 }).format(value); }
function quantity(value: number | null | undefined): string { return value == null ? "—" : new Intl.NumberFormat("de-DE", { maximumFractionDigits: 8 }).format(value); }
function money(value: number | null | undefined, currency = "USD"): string { if (value == null) return "—"; try { return new Intl.NumberFormat("de-DE", { style: "currency", currency: currency || "USD", maximumFractionDigits: 2 }).format(value); } catch { return `${number(value)} ${currency}`; } }
function score(value: unknown): string { const result = numeric(value); return result == null ? "Unbekannt" : number(result); }
function gross(entry: TradeJournalEntrySummary): number | null { return entry.price != null && entry.shares != null ? entry.price * entry.shares : null; }
function dateTime(entry: TradeJournalEntrySummary): string { if (entry.execution_at && !entry.execution_at.endsWith("T00:00:00")) return formatDateTime(entry.execution_at); return new Intl.DateTimeFormat("de-DE").format(new Date(`${entry.trade_date}T12:00:00`)); }
function formatDateTime(value: string): string { const date = new Date(value); return Number.isNaN(date.valueOf()) ? value : new Intl.DateTimeFormat("de-DE", { dateStyle: "medium", timeStyle: "short" }).format(date); }
function executionText(entry: TradeJournalEntrySummary): string { if (entry.entry_type === "ex_post") return "Nachbereitung"; if (entry.entry_type === "sell") return "Verkauf / Teilverkauf"; return entry.trade_group_id ? "Kauf / Nachkauf" : "Kauf"; }
function statusText(value: TradeJournalEntryStatus): string { return value === "open" ? "Offen" : value === "closed" ? "Abgeschlossen" : "Zuordnung offen"; }
function contextLabel(value: TradeJournalEntrySummary["context_status"]): string { return ({ archived: "Archiviert", reconstructed: "Rekonstruiert", partial: "Teilweise", missing: "Fehlt", pending: "Wird ergänzt", failed: "Fehlgeschlagen" })[value]; }
function resultColor(value: number | null | undefined): string { return value == null ? "text-[#687386]" : value >= 0 ? "text-[#138a57]" : "text-[#c2413b]"; }
