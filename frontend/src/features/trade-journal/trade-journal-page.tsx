"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import {
  AlertTriangle,
  BarChart3,
  BookOpenCheck,
  Building2,
  CheckCircle2,
  Edit3,
  FileDown,
  Gauge,
  ImagePlus,
  Plus,
  Save,
  Search,
  TrendingUp,
  XCircle
} from "lucide-react";
import { FormEvent, ReactNode, useEffect, useMemo, useRef, useState } from "react";
import { StatusChip } from "@/components/ui/status-chip";
import { api } from "@/lib/api/client";
import type {
  Tone,
  TradeJournalDefaults,
  TradeJournalEntryDetail,
  TradeJournalEntryRequest,
  TradeJournalEntryStatus,
  TradeJournalEntrySummary,
  TradeJournalEntryType,
  TradeJournalImageSet
} from "@/lib/types/api";

type JournalDraft = {
  ticker: string;
  entry_type: TradeJournalEntryType;
  trade_date: string;
  price: string;
  shares: string;
  stop_price: string;
  linked_entry_id: string;
  status: TradeJournalEntryStatus;
  basis_text: string;
  alternative_entry: boolean;
  alternative_entry_text: string;
  primary_reasons: string;
  sell_reason: string;
  close_with_related_buy: boolean;
  questionnaire: Record<string, string>;
  chart_images: TradeJournalImageSet;
};

type SnapshotCheck = {
  label?: string;
  detail?: string;
  passed?: boolean;
  category?: string;
  severity?: string;
};

type SnapshotSignal = {
  category?: string;
  label?: string;
  detail?: string;
};

const entryLabels: Record<TradeJournalEntryType, string> = {
  buy: "Kauf",
  sell: "Verkauf",
  ex_post: "Ex-Post Analyse"
};

const statusTones: Record<TradeJournalEntryStatus, Tone> = {
  open: "warning",
  closed: "good",
  draft: "neutral"
};

const exPostQuestions = [
  ["checklist", "Hat die Aktie die Merkmale deiner Checkliste erfüllt?"],
  ["buy_reason", "Warum wurde die Aktie gekauft?"],
  ["entry_quality", "Wurde ein sinnvoller und regeltreuer Einstiegspunkt gewählt?"],
  ["position_build", "Wie wurde die Position aufgebaut?"],
  ["adds_reason", "Wenn Positionen nachgekauft wurden, warum?"],
  ["position_size", "War die Positionsgröße sinnvoll gewählt?"],
  ["market_environment", "Wie war das Marktumfeld beim Kauf und beim Verkauf?"],
  ["news", "Gab es besondere Nachrichten beim Kauf oder Verkauf?"],
  ["chart_pattern", "Lag beim Kauf ein Chartmuster vor?"],
  ["base_flaws", "Hatte die Basis rückblickend Fehler?"],
  ["held_too_long", "Wurde zu lange an der Aktie festgehalten?"],
  ["emotional_sale", "War es ein emotionaler Verkauf?"],
  ["sell_rules", "Wurden die Verkaufsregeln eingehalten?"],
  ["derived_rules", "Welche Regeln werden daraus abgeleitet?"]
];

export function TradeJournalPage() {
  const queryClient = useQueryClient();
  const [tickerInput, setTickerInput] = useState("NVDA");
  const [activeTicker, setActiveTicker] = useState("NVDA");
  const [activeType, setActiveType] = useState<TradeJournalEntryType>("buy");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [selectedEntry, setSelectedEntry] = useState<TradeJournalEntryDetail | null>(null);
  const [loadingEntryId, setLoadingEntryId] = useState<string | null>(null);
  const seedKeyRef = useRef("");
  const [draft, setDraft] = useState<JournalDraft>(() => emptyDraft("NVDA", "buy"));

  const entriesQuery = useQuery({
    queryKey: ["trade-journal", activeTicker],
    queryFn: () => api.tradeJournalEntries(activeTicker),
    enabled: Boolean(activeTicker)
  });

  const defaultsQuery = useQuery({
    queryKey: ["trade-journal-defaults", activeTicker, activeType],
    queryFn: () => api.tradeJournalDefaults(activeTicker, activeType),
    enabled: Boolean(activeTicker) && editingId === null,
    staleTime: 30_000
  });
  const defaultLinkedEntryId = defaultsQuery.data?.open_buy_entry_id ?? null;
  const defaultLinkedEntry = useQuery({
    queryKey: ["trade-journal-entry", defaultLinkedEntryId],
    queryFn: () => api.tradeJournalEntry(defaultLinkedEntryId ?? ""),
    enabled: activeType === "ex_post" && editingId === null && Boolean(defaultLinkedEntryId),
    staleTime: 30_000
  });

  const entries = useMemo(() => entriesQuery.data?.entries ?? [], [entriesQuery.data?.entries]);
  const canCreateExPost = useMemo(
    () => entries.some((entry) => entry.entry_type === "buy" && entry.status === "closed")
      && entries.some((entry) => entry.entry_type === "sell" && entry.status === "closed"),
    [entries]
  );

  useEffect(() => {
    if (!defaultsQuery.data || editingId !== null) return;
    const nextKey = `${defaultsQuery.data.ticker}-${defaultsQuery.data.entry_type}-${defaultsQuery.data.trade_date}`;
    if (seedKeyRef.current === nextKey) return;
    seedKeyRef.current = nextKey;
    queueMicrotask(() => setDraft(fromDefaults(defaultsQuery.data)));
  }, [defaultsQuery.data, editingId]);

  useEffect(() => {
    if (activeType !== "ex_post" || editingId !== null || !defaultLinkedEntry.data?.entry) return;
    const summary = checklistSummaryFromSnapshot(defaultLinkedEntry.data.entry.stock_snapshot);
    if (!summary) return;
    queueMicrotask(() => {
      setDraft((previous) => {
        if (previous.entry_type !== "ex_post" || previous.questionnaire.checklist) return previous;
        return { ...previous, questionnaire: { ...previous.questionnaire, checklist: summary } };
      });
    });
  }, [activeType, defaultLinkedEntry.data?.entry, editingId]);

  const saveMutation = useMutation({
    mutationFn: (payload: TradeJournalEntryRequest) =>
      editingId ? api.updateTradeJournalEntry(editingId, payload) : api.createTradeJournalEntry(payload),
    onSuccess: (payload) => {
      setSelectedEntry(payload.entry);
      setEditingId(null);
      void queryClient.invalidateQueries({ queryKey: ["trade-journal", activeTicker] });
    }
  });

  function loadTicker(event?: FormEvent) {
    event?.preventDefault();
    const clean = normalizeTicker(tickerInput);
    if (!clean) return;
    setActiveTicker(clean);
    setActiveType("buy");
    setEditingId(null);
    setSelectedEntry(null);
    seedKeyRef.current = "";
    setDraft(emptyDraft(clean, "buy"));
  }

  function startNew(type: TradeJournalEntryType) {
    setActiveType(type);
    setEditingId(null);
    setSelectedEntry(null);
    seedKeyRef.current = "";
    setDraft(emptyDraft(activeTicker, type));
  }

  async function loadEntry(entryId: string, mode: "view" | "edit") {
    setLoadingEntryId(entryId);
    try {
      const payload = await api.tradeJournalEntry(entryId);
      setSelectedEntry(payload.entry);
      if (mode === "edit") {
        setEditingId(entryId);
        setActiveType(payload.entry.entry_type);
        setDraft(fromEntry(payload.entry));
      }
    } finally {
      setLoadingEntryId(null);
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    saveMutation.mutate(toRequest(draft));
  }

  const counterpartId = selectedEntry
    ? selectedEntry.linked_entry_id
      ?? entries.find((entry) => entry.entry_type === "sell" && entry.linked_entry_id === selectedEntry.id)?.id
      ?? null
    : null;

  return (
    <div className="space-y-5">
      <header className="rounded border border-[#2d333d] bg-[#171a20] p-5">
        <div className="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
          <div>
            <div className="flex items-center gap-2 text-sm text-[#a0a7b4]">
              <BookOpenCheck className="size-4 text-[#8ea4c8]" />
              Trading Review
            </div>
            <h1 className="mt-1 text-3xl font-semibold">Handelstagebuch</h1>
            <p className="mt-2 max-w-4xl text-sm leading-6 text-[#a0a7b4]">
              Kaufsituation, Verkaufsentscheidung, Marktumfeld und Checklisten werden beim Speichern als historischer Snapshot festgehalten.
            </p>
          </div>
          <form className="flex w-full flex-col gap-2 sm:flex-row xl:max-w-md" onSubmit={loadTicker}>
            <label className="sr-only" htmlFor="journal-ticker">Ticker</label>
            <input
              id="journal-ticker"
              className="min-h-10 flex-1 rounded border border-[#2d333d] bg-[#111419] px-3 py-2 text-sm uppercase outline-none transition focus:border-emerald-300/70"
              value={tickerInput}
              placeholder="Ticker oder Symbol"
              onChange={(event) => setTickerInput(event.target.value.toUpperCase())}
            />
            <button
              className="inline-flex min-h-10 items-center justify-center gap-2 rounded border border-emerald-300/35 bg-emerald-300/10 px-3 py-2 text-sm text-emerald-100 transition hover:border-emerald-200"
              type="submit"
            >
              <Search size={15} />
              Laden
            </button>
          </form>
        </div>
      </header>

      <section className="grid gap-3 md:grid-cols-3">
        <ActionCard type="buy" active={activeType === "buy" && !editingId} onClick={() => startNew("buy")} />
        <ActionCard type="sell" active={activeType === "sell" && !editingId} onClick={() => startNew("sell")} />
        <ActionCard
          type="ex_post"
          active={activeType === "ex_post" && !editingId}
          disabled={!canCreateExPost}
          detail={canCreateExPost ? "Kauf und Verkauf liegen geschlossen vor." : "Wird aktiv, sobald Kauf und Verkauf geschlossen sind."}
          onClick={() => startNew("ex_post")}
        />
      </section>

      {entriesQuery.isError && (
        <section className="rounded border border-rose-300/30 bg-rose-400/10 p-4 text-sm text-rose-100">
          Tagebucheinträge konnten nicht geladen werden: {(entriesQuery.error as Error).message}
        </section>
      )}

      <div className="grid gap-5 xl:grid-cols-[0.95fr_1.05fr]">
        <JournalForm
          defaults={defaultsQuery.data}
          draft={draft}
          editing={Boolean(editingId)}
          isSaving={saveMutation.isPending}
          error={saveMutation.error}
          onDraftChange={setDraft}
          onSubmit={submit}
        />

        <section className="space-y-4">
          <EntryList
            entries={entries}
            loading={entriesQuery.isLoading}
            loadingEntryId={loadingEntryId}
            onView={(entryId) => void loadEntry(entryId, "view")}
            onEdit={(entryId) => void loadEntry(entryId, "edit")}
          />
          {selectedEntry && (
            <JournalChecklist
              counterpartId={counterpartId}
              entry={selectedEntry}
              onEdit={() => void loadEntry(selectedEntry.id, "edit")}
            />
          )}
        </section>
      </div>
    </div>
  );
}

function ActionCard({
  type,
  active,
  disabled = false,
  detail,
  onClick
}: {
  type: TradeJournalEntryType;
  active: boolean;
  disabled?: boolean;
  detail?: string;
  onClick: () => void;
}) {
  return (
    <button
      className={clsx(
        "rounded border p-4 text-left transition",
        active ? "border-emerald-300/50 bg-emerald-300/10" : "border-[#2d333d] bg-[#171a20] hover:border-[#46505d]",
        disabled && "cursor-not-allowed opacity-55 hover:border-[#2d333d]"
      )}
      type="button"
      disabled={disabled}
      onClick={onClick}
    >
      <div className="flex items-center justify-between gap-3">
        <div className="text-base font-semibold">{entryLabels[type]} anlegen</div>
        <Plus className="size-4 text-[#8ea4c8]" />
      </div>
      <p className="mt-2 text-sm leading-6 text-[#a0a7b4]">
        {detail ?? (type === "buy"
          ? "Setup, Marktphase, Stop, Risiko und Chartbilder einfrieren."
          : "Entscheidung, P&L, Stop-Abweichung und Verkaufsgrund dokumentieren.")}
      </p>
    </button>
  );
}

function JournalForm({
  defaults,
  draft,
  editing,
  isSaving,
  error,
  onDraftChange,
  onSubmit
}: {
  defaults?: TradeJournalDefaults;
  draft: JournalDraft;
  editing: boolean;
  isSaving: boolean;
  error: unknown;
  onDraftChange: (draft: JournalDraft) => void;
  onSubmit: (event: FormEvent) => void;
}) {
  const stopDistance = stopDistancePct(numberFromString(draft.price), numberFromString(draft.stop_price));
  const isSell = draft.entry_type === "sell";
  const isBuy = draft.entry_type === "buy";
  const isExPost = draft.entry_type === "ex_post";

  function patch(patchValue: Partial<JournalDraft>) {
    onDraftChange({ ...draft, ...patchValue });
  }

  function patchQuestion(key: string, value: string) {
    patch({ questionnaire: { ...draft.questionnaire, [key]: value } });
  }

  return (
    <form className="space-y-4 rounded border border-[#2d333d] bg-[#171a20] p-5" onSubmit={onSubmit}>
      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-xl font-semibold">{editing ? "Eintrag bearbeiten" : `${entryLabels[draft.entry_type]} erfassen`}</h2>
            <StatusChip tone="neutral">{draft.ticker}</StatusChip>
          </div>
          <p className="mt-2 text-sm leading-6 text-[#a0a7b4]">
            Die Bewertung aus Stocks, Marktampel S&P 500 und Portfolio-Risikodaten werden beim Speichern übernommen.
          </p>
        </div>
        <StatusChip tone={editing ? "warning" : "good"}>{editing ? "Edit" : "Neu"}</StatusChip>
      </div>

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <Field label="Ticker">
          <input className="input-dark uppercase" value={draft.ticker} onChange={(event) => patch({ ticker: event.target.value.toUpperCase() })} />
        </Field>
        <Field label={isSell ? "Verkaufsdatum" : isBuy ? "Kaufdatum" : "Analysedatum"}>
          <input className="input-dark" type="date" value={draft.trade_date} onChange={(event) => patch({ trade_date: event.target.value })} />
        </Field>
        <Field label="Preis USD">
          <input className="input-dark" inputMode="decimal" value={draft.price} onChange={(event) => patch({ price: event.target.value })} />
        </Field>
        <Field label="Stückzahl">
          <input className="input-dark" inputMode="decimal" value={draft.shares} onChange={(event) => patch({ shares: event.target.value })} />
        </Field>
      </div>

      <div className="grid gap-3 md:grid-cols-3">
        <Field label="Stoppkurs USD">
          <input className="input-dark" inputMode="decimal" value={draft.stop_price} onChange={(event) => patch({ stop_price: event.target.value })} />
        </Field>
        <MetricBox label="Stopp-Abstand" value={stopDistance === null ? "-" : `${stopDistance.toFixed(2)}%`} detail="automatisch aus Preis und Stopp" />
        <MetricBox
          label="Verknüpfter Kauf"
          value={draft.linked_entry_id ? "gefunden" : defaults?.open_buy_entry_id ? "offen" : "-"}
          detail={defaults?.open_buy_date ? `${defaults.open_buy_date} · ${money(defaults.open_buy_price)}` : "für Verkauf / Ex-Post"}
        />
      </div>

      {isBuy && (
        <div className="grid gap-3 md:grid-cols-2">
          <Field label="Welche Basis lag vor?">
            <textarea
              className="input-dark min-h-24"
              value={draft.basis_text}
              placeholder="Rückkehr zur 50-Tage-Linie"
              onChange={(event) => patch({ basis_text: event.target.value })}
            />
          </Field>
          <Field label="Primäre Gründe für den Kauf">
            <textarea className="input-dark min-h-24" value={draft.primary_reasons} onChange={(event) => patch({ primary_reasons: event.target.value })} />
          </Field>
          <label className="flex items-center gap-2 rounded border border-[#242a33] bg-[#111419] p-3 text-sm text-[#c9d0da]">
            <input
              type="checkbox"
              checked={draft.alternative_entry}
              onChange={(event) => patch({ alternative_entry: event.target.checked })}
            />
            Alternativer Einstieg
          </label>
          {draft.alternative_entry && (
            <Field label="Alternativer Einstieg">
              <textarea
                className="input-dark min-h-20"
                value={draft.alternative_entry_text}
                placeholder="Rückkehr zur 50-Tage-Linie"
                onChange={(event) => patch({ alternative_entry_text: event.target.value })}
              />
            </Field>
          )}
        </div>
      )}

      {isSell && (
        <div className="space-y-3">
          <Field label="Grund für den Verkauf">
            <textarea className="input-dark min-h-24" value={draft.sell_reason} onChange={(event) => patch({ sell_reason: event.target.value })} />
          </Field>
          <label className="flex items-center gap-2 rounded border border-[#242a33] bg-[#111419] p-3 text-sm text-[#c9d0da]">
            <input
              type="checkbox"
              checked={draft.close_with_related_buy}
              onChange={(event) => patch({ close_with_related_buy: event.target.checked })}
            />
            Mit dem Speichern Verkauf und verbundenen offenen Kauf schließen
          </label>
        </div>
      )}

      {isExPost && (
        <div className="space-y-3">
          <div className="rounded border border-[#242a33] bg-[#111419] p-4">
            <h3 className="text-base font-semibold">Ex-Post-Fragebogen</h3>
            <p className="mt-1 text-sm text-[#a0a7b4]">
              Checklistenpunkte aus dem Kauf-Snapshot werden im gespeicherten Eintrag darunter angezeigt.
            </p>
          </div>
          <div className="grid gap-3">
            {exPostQuestions.map(([key, label]) => (
              <Field key={key} label={label}>
                <textarea className="input-dark min-h-20" value={draft.questionnaire[key] ?? ""} onChange={(event) => patchQuestion(key, event.target.value)} />
              </Field>
            ))}
          </div>
        </div>
      )}

      <div className="grid gap-3 md:grid-cols-2">
        <ImageUpload
          label="Tageschart"
          value={draft.chart_images.daily_chart}
          onChange={(value) => patch({ chart_images: { ...draft.chart_images, daily_chart: value } })}
        />
        <ImageUpload
          label="Wochenchart"
          value={draft.chart_images.weekly_chart}
          onChange={(value) => patch({ chart_images: { ...draft.chart_images, weekly_chart: value } })}
        />
      </div>

      {defaults && (
        <div className="grid gap-3 md:grid-cols-3">
          <MetricBox label="Default Preis" value={money(defaults.price)} detail="aktueller Cache-Wert" />
          <MetricBox label="Marktampel" value={marketPhaseLabel(defaults.market_snapshot)} detail={marketMaDetail(defaults.market_snapshot)} />
          <MetricBox label="Positionsgröße" value={money(asNumber(defaults.portfolio_snapshot.position_size_eur), "EUR")} detail="aus Preis und Stückzahl" />
        </div>
      )}

      {Boolean(error) && (
        <div className="rounded border border-rose-300/30 bg-rose-400/10 p-3 text-sm text-rose-100">
          Speichern fehlgeschlagen: {(error as Error).message}
        </div>
      )}

      <button
        className="inline-flex min-h-10 items-center justify-center gap-2 rounded border border-emerald-300/35 bg-emerald-300/10 px-4 py-2 text-sm text-emerald-100 transition hover:border-emerald-200 disabled:cursor-not-allowed disabled:opacity-60"
        type="submit"
        disabled={isSaving}
      >
        <Save size={16} />
        {isSaving ? "Speichert..." : "Eintrag speichern"}
      </button>
    </form>
  );
}

function EntryList({
  entries,
  loading,
  loadingEntryId,
  onView,
  onEdit
}: {
  entries: TradeJournalEntrySummary[];
  loading: boolean;
  loadingEntryId: string | null;
  onView: (entryId: string) => void;
  onEdit: (entryId: string) => void;
}) {
  return (
    <section className="rounded border border-[#2d333d] bg-[#171a20] p-5">
      <div className="mb-4 flex items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-semibold">Bestehende Einträge</h2>
          <p className="mt-1 text-sm text-[#a0a7b4]">Kauf, Verkauf und Ex-Post werden pro Ticker chronologisch gespeichert.</p>
        </div>
        <StatusChip tone="neutral">{entries.length}</StatusChip>
      </div>
      {loading ? (
        <div className="space-y-2">
          {[0, 1, 2].map((item) => <div key={item} className="h-20 animate-pulse rounded border border-[#242a33] bg-[#111419]" />)}
        </div>
      ) : entries.length === 0 ? (
        <div className="rounded border border-[#242a33] bg-[#111419] p-4 text-sm text-[#a0a7b4]">
          Noch kein Tagebucheintrag für diesen Ticker.
        </div>
      ) : (
        <div className="space-y-2">
          {entries.map((entry) => (
            <div key={entry.id} className="rounded border border-[#242a33] bg-[#111419] p-3">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                <button className="min-w-0 text-left" type="button" onClick={() => onView(entry.id)}>
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-semibold">{entry.title}</span>
                    <StatusChip tone={statusTones[entry.status]}>{entry.status}</StatusChip>
                  </div>
                  <p className="mt-1 text-sm text-[#a0a7b4]">{entry.summary}</p>
                </button>
                <div className="flex gap-2">
                  <button className="rounded border border-[#2d333d] px-3 py-2 text-xs text-[#c9d0da] hover:border-[#46505d]" type="button" onClick={() => onView(entry.id)}>
                    {loadingEntryId === entry.id ? "Lädt..." : "Anzeigen"}
                  </button>
                  <button className="inline-flex items-center gap-1 rounded border border-[#2d333d] px-3 py-2 text-xs text-[#c9d0da] hover:border-[#46505d]" type="button" onClick={() => onEdit(entry.id)}>
                    <Edit3 size={13} />
                    Edit
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

function JournalChecklist({
  counterpartId,
  entry,
  onEdit
}: {
  counterpartId: string | null;
  entry: TradeJournalEntryDetail;
  onEdit: () => void;
}) {
  const counterpartQuery = useQuery({
    queryKey: ["trade-journal-entry", counterpartId],
    queryFn: () => api.tradeJournalEntry(counterpartId ?? ""),
    enabled: Boolean(counterpartId)
  });
  const counterpart = counterpartQuery.data?.entry ?? null;
  const marketLabel = marketPhaseLabel(entry.market_snapshot);
  const portfolio = entry.portfolio_snapshot;
  return (
    <article className="space-y-4 rounded border border-[#2d333d] bg-[#171a20] p-5 print:bg-white print:text-black" id="trade-journal-print">
      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-xl font-semibold">{entry.title}</h2>
            <StatusChip tone={statusTones[entry.status]}>{entry.status}</StatusChip>
          </div>
          <p className="mt-1 text-sm text-[#a0a7b4] print:text-gray-700">{entry.summary}</p>
        </div>
        <div className="flex gap-2 print:hidden">
          <button className="inline-flex items-center gap-2 rounded border border-[#2d333d] px-3 py-2 text-sm text-[#c9d0da] hover:border-[#46505d]" type="button" onClick={onEdit}>
            <Edit3 size={15} />
            Editieren
          </button>
          <button className="inline-flex items-center gap-2 rounded border border-emerald-300/35 bg-emerald-300/10 px-3 py-2 text-sm text-emerald-100 hover:border-emerald-200" type="button" onClick={() => printEntry(entry)}>
            <FileDown size={15} />
            PDF / Drucken
          </button>
        </div>
      </div>

      <div className="grid gap-3 md:grid-cols-3">
        <MetricBox label="Preis" value={money(entry.price)} detail={`${entry.shares ?? "-"} Stück`} />
        <MetricBox label="Stopp" value={money(entry.stop_price)} detail={entry.stop_distance_pct === null || entry.stop_distance_pct === undefined ? "Abstand offen" : `${entry.stop_distance_pct.toFixed(2)}% Abstand`} />
        <MetricBox
          label="P&L / Stop-Abweichung"
          value={entry.realized_pnl_pct === null || entry.realized_pnl_pct === undefined ? "-" : `${entry.realized_pnl_pct.toFixed(2)}%`}
          detail={`${money(entry.realized_pnl_eur, "EUR")} · Stop-Abw. ${pct(entry.stop_deviation_pct)}`}
        />
      </div>

      <div className="grid gap-3 md:grid-cols-2">
        <TextBlock title="Kaufbasis / Setup" text={entry.basis_text || "-"} />
        <TextBlock title="Kauf- oder Verkaufsgrund" text={entry.entry_type === "sell" ? entry.sell_reason || "-" : entry.primary_reasons || "-"} />
        {entry.alternative_entry ? (
          <TextBlock title="Alternativer Einstieg" text={entry.alternative_entry_text || "Rückkehr zur 50-Tage-Linie"} />
        ) : null}
      </div>

      <div className="grid gap-3 md:grid-cols-3">
        <MetricBox label="Marktampel S&P 500" value={marketLabel} detail={marketMaDetail(entry.market_snapshot)} />
        <MetricBox
          label="Positionsgröße / Gewichtung"
          value={money(asNumber(portfolio.position_size_eur), "EUR")}
          detail={`Gewicht ${pct(asNumber(portfolio.weight_pct))} · FX ${nestedValue(portfolio, "fx_rate.rate") ?? "-"}`}
        />
        <MetricBox
          label="ATR / Beta / Risiko"
          value={formatNumber(asNumber(portfolio.beta_balancer_score))}
          detail={`ATR ${pct(asNumber(portfolio.atr_pct))} · Beta ${formatNumber(asNumber(portfolio.beta))} · Risikobeitrag ${formatNumber(asNumber(portfolio.risk_contribution))}`}
        />
      </div>

      <TradeComparison entry={entry} counterpart={counterpart} loading={counterpartQuery.isLoading} />
      <StockSnapshotReport snapshot={entry.stock_snapshot} />

      {Object.keys(entry.questionnaire).length > 0 && (
        <div className="rounded border border-[#242a33] bg-[#111419] p-4 print:border-gray-300 print:bg-white">
          <h3 className="text-base font-semibold">Ex-Post-Fragebogen</h3>
          <div className="mt-3 space-y-3">
            {exPostQuestions.map(([key, label]) => (
              <TextBlock key={key} title={label} text={String(entry.questionnaire[key] ?? "-")} />
            ))}
          </div>
        </div>
      )}

      <div className="grid gap-3 md:grid-cols-2">
        <ChartImage label="Tageschart" src={entry.chart_images.daily_chart} />
        <ChartImage label="Wochenchart" src={entry.chart_images.weekly_chart} />
      </div>
    </article>
  );
}

function TradeComparison({
  counterpart,
  entry,
  loading
}: {
  counterpart: TradeJournalEntryDetail | null;
  entry: TradeJournalEntryDetail;
  loading: boolean;
}) {
  if (!counterpart && !loading) return null;
  const buy = entry.entry_type === "buy" ? entry : counterpart?.entry_type === "buy" ? counterpart : null;
  const sell = entry.entry_type === "sell" ? entry : counterpart?.entry_type === "sell" ? counterpart : null;
  return (
    <section className="rounded border border-[#242a33] bg-[#111419] p-4 print:border-gray-300 print:bg-white">
      <div className="mb-3 flex items-center justify-between gap-3">
        <h3 className="text-base font-semibold">Gegenüberstellung Kauf / Verkauf</h3>
        <StatusChip tone={buy && sell ? "good" : "neutral"}>{loading ? "lädt" : buy && sell ? "vollständig" : "teilweise"}</StatusChip>
      </div>
      {loading ? (
        <div className="text-sm text-[#a0a7b4]">Verknüpften Eintrag laden...</div>
      ) : (
        <div className="grid gap-3 md:grid-cols-2">
          <ComparisonColumn label="Kauf" entry={buy} />
          <ComparisonColumn label="Verkauf" entry={sell} />
        </div>
      )}
      {buy && sell ? (
        <div className="mt-3 grid gap-3 md:grid-cols-3">
          <MetricBox label="Realisierte Rendite" value={pct(sell.realized_pnl_pct)} detail={money(sell.realized_pnl_eur, "EUR")} />
          <MetricBox label="Stop-Abweichung" value={pct(sell.stop_deviation_pct)} detail="Verkaufspreis vs. Kauf-Stopp" />
          <MetricBox label="Haltedauer" value={holdingDays(buy.trade_date, sell.trade_date)} detail={`${buy.trade_date} bis ${sell.trade_date}`} />
        </div>
      ) : null}
    </section>
  );
}

function ComparisonColumn({ entry, label }: { entry: TradeJournalEntryDetail | null; label: string }) {
  if (!entry) {
    return (
      <div className="rounded border border-dashed border-[#343b47] p-3 text-sm text-[#a0a7b4]">
        Kein {label}-Eintrag verknüpft.
      </div>
    );
  }
  return (
    <div className="rounded border border-[#2d333d] p-3">
      <div className="mb-2 flex items-center justify-between gap-2">
        <div className="font-medium">{label}</div>
        <StatusChip tone={statusTones[entry.status]}>{entry.status}</StatusChip>
      </div>
      <div className="grid gap-2 text-sm text-[#c9d0da]">
        <div>Datum: {entry.trade_date}</div>
        <div>Preis: {money(entry.price)}</div>
        <div>Stückzahl: {entry.shares ?? "-"}</div>
        <div>Stopp: {money(entry.stop_price)} · {pct(entry.stop_distance_pct)}</div>
      </div>
    </div>
  );
}

function StockSnapshotReport({ snapshot }: { snapshot: Record<string, unknown> }) {
  const assessment = assessmentFromSnapshot(snapshot);
  const scores = recordValue(assessment.scores);
  const metrics = recordValue(assessment.metrics);
  const fundamentals = recordValue(snapshot.fundamentals);
  const fundamentalItem = recordValue(fundamentals.item);
  const institutional = recordValue(snapshot.institutional_13f);
  const institutionalItem = recordValue(institutional.item);
  const rs = recordValue(snapshot.relative_strength);
  const rsItem = recordValue(rs.item);
  const checks = checksFromSnapshot(snapshot);
  const chartSignals = chartSignalsFromSnapshot(snapshot);
  const drivers = stringArray(assessment.drivers);
  const warnings = stringArray(assessment.warnings);

  return (
    <section className="space-y-4 rounded border border-[#242a33] bg-[#111419] p-4 print:border-gray-300 print:bg-white">
      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div>
          <h3 className="text-base font-semibold">Stock Detail Snapshot</h3>
          <p className="mt-1 text-sm text-[#a0a7b4] print:text-gray-700">
            Eingefrorene Bewertung am Tagebucheintrag: Scores, Kennzahlen, Regeln, Fundamentals, 13F und Relative Stärke.
          </p>
        </div>
        <StatusChip tone={toneValue(assessment.verdict_tone)}>{stringValue(assessment.verdict_label) || "Snapshot"}</StatusChip>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
        <MetricBox label="Gesamtscore" value={formatNumber(asNumber(scores.overall))} detail={stringValue(assessment.verdict_text) || "Aktienbewertung"} />
        <MetricBox label="Technisch" value={formatNumber(asNumber(scores.technical))} detail="Preis, Volumen, RS, CMF" />
        <MetricBox label="Fundamental" value={formatNumber(asNumber(scores.fundamental))} detail="EPS, Umsatz, ROE, Marge" />
        <MetricBox label="Trend" value={formatNumber(asNumber(scores.moving_averages))} detail="10/21/50/200" />
        <MetricBox label="Chart" value={formatNumber(asNumber(scores.chart_behavior))} detail="Chartverhalten" />
      </div>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <MetricBox label="Aktueller Preis" value={money(asNumber(metrics.last_close))} detail={`Veränderung ${pct(asNumber(metrics.change_pct))}`} />
        <MetricBox label="ATR" value={pct(asNumber(metrics.atr_pct))} detail={atrRegime(asNumber(metrics.atr_pct))} />
        <MetricBox label="RS-Rating" value={formatNumber(asNumber(metrics.rs_rating))} detail={`RS Stand ${stringValue(rsItem.date) || "-"}`} />
        <MetricBox label="Beta" value={formatNumber(asNumber(metrics.beta))} detail={betaRegime(asNumber(metrics.beta))} />
      </div>

      <div className="grid gap-3 md:grid-cols-2">
        <TextList title="Treiber" icon="good" items={drivers} empty="Keine Treiber gespeichert." />
        <TextList title="Warnungen" icon="warning" items={warnings} empty="Keine Warnungen gespeichert." />
      </div>

      <RuleChecklist checks={checks} />
      <ChartSignalPanel signals={chartSignals} />
      <FundamentalsSnapshot item={fundamentalItem} />
      <InstitutionalSnapshot item={institutionalItem} source={stringValue(institutional.source)} />
      <RelativeStrengthSnapshot item={rsItem} found={Boolean(rs.found)} />
    </section>
  );
}

function TextList({ empty, icon, items, title }: { empty: string; icon: "good" | "warning"; items: string[]; title: string }) {
  return (
    <div className="rounded border border-[#2d333d] p-3">
      <div className="mb-2 flex items-center gap-2 font-medium">
        {icon === "good" ? <CheckCircle2 className="size-4 text-emerald-300" /> : <AlertTriangle className="size-4 text-amber-300" />}
        {title}
      </div>
      {items.length === 0 ? (
        <div className="text-sm text-[#a0a7b4]">{empty}</div>
      ) : (
        <div className="space-y-2">
          {items.map((item) => (
            <div key={item} className="rounded border border-[#242a33] p-2 text-sm leading-5 text-[#c9d0da]">
              {item}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function RuleChecklist({ checks }: { checks: SnapshotCheck[] }) {
  const groups = [
    ["technical", "Technisch"],
    ["trend", "Trend"],
    ["risk", "Überdehnung"],
    ["fundamental", "Fundamental"]
  ];
  return (
    <div className="rounded border border-[#2d333d] p-3">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 font-medium">
          <Gauge className="size-4 text-[#8ea4c8]" />
          Regel-Checkliste
        </div>
        <StatusChip tone="neutral">{checks.length}</StatusChip>
      </div>
      {checks.length === 0 ? (
        <div className="text-sm text-[#a0a7b4]">Keine Checkliste im Snapshot vorhanden.</div>
      ) : (
        <div className="grid gap-3 lg:grid-cols-2">
          {groups.map(([category, label]) => (
            <div key={category} className="rounded border border-[#242a33] p-3">
              <div className="mb-2 text-sm font-medium">{label}</div>
              <div className="space-y-2">
                {checks.filter((check) => check.category === category).map((check, index) => (
                  <CheckRow key={`${check.label}-${index}`} check={check} />
                ))}
                {checks.filter((check) => check.category === category).length === 0 ? (
                  <div className="text-sm text-[#7f8794]">Keine Regeln.</div>
                ) : null}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function CheckRow({ check }: { check: SnapshotCheck }) {
  return (
    <div className="flex gap-2 rounded border border-[#242a33] p-2 text-sm print:border-gray-300">
      {check.passed ? (
        <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-emerald-300 print:text-green-700" />
      ) : (
        <XCircle className="mt-0.5 size-4 shrink-0 text-rose-300 print:text-red-700" />
      )}
      <div>
        <div className={check.passed ? "text-emerald-100 print:text-green-800" : "text-rose-100 print:text-red-800"}>{check.label}</div>
        <div className="text-xs leading-5 text-[#a0a7b4] print:text-gray-700">{check.detail}</div>
      </div>
    </div>
  );
}

function ChartSignalPanel({ signals }: { signals: SnapshotSignal[] }) {
  const groups: Array<[string, string, Tone]> = [
    ["positive", "Positive Zeichen", "good" as Tone],
    ["negative", "Warnzeichen", "bad" as Tone],
    ["neutral", "Neutral", "neutral" as Tone]
  ];
  return (
    <div className="rounded border border-[#2d333d] p-3">
      <div className="mb-3 flex items-center gap-2 font-medium">
        <BarChart3 className="size-4 text-[#8ea4c8]" />
        Chartverhalten
      </div>
      <div className="grid gap-3 md:grid-cols-3">
        {groups.map(([category, label, tone]) => {
          const items = signals.filter((signal) => signal.category === category);
          return (
            <div key={category} className="rounded border border-[#242a33] p-3">
              <div className="mb-2 flex items-center justify-between gap-2">
                <div className="text-sm font-medium">{label}</div>
                <StatusChip tone={tone}>{items.length}</StatusChip>
              </div>
              {items.length === 0 ? (
                <div className="text-sm text-[#7f8794]">Keine Signale.</div>
              ) : (
                <div className="space-y-2">
                  {items.map((signal, index) => (
                    <div key={`${signal.label}-${index}`} className="rounded border border-[#242a33] p-2 text-sm">
                      <div className="font-medium">{signal.label}</div>
                      <div className="mt-1 text-xs leading-5 text-[#a0a7b4]">{signal.detail}</div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function FundamentalsSnapshot({ item }: { item: Record<string, unknown> }) {
  const epsQuarter = recordArray(item.eps_quarter_history).slice(0, 3);
  const epsAnnual = recordArray(item.annual_eps_history).slice(0, 3);
  const revenueQuarter = recordArray(item.revenue_quarter_history).slice(0, 3);
  const revenueAnnual = recordArray(item.annual_revenue_history).slice(0, 3);
  const roeHistory = recordArray(item.roe_history).slice(0, 3);
  return (
    <div className="rounded border border-[#2d333d] p-3">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 font-medium">
          <TrendingUp className="size-4 text-[#8ea4c8]" />
          Fundamental
        </div>
        <StatusChip tone={item.ticker ? "good" : "warning"}>{stringValue(item.source) || "missing"}</StatusChip>
      </div>
      {!item.ticker ? (
        <div className="text-sm text-[#a0a7b4]">Keine Fundamental-Daten im Snapshot.</div>
      ) : (
        <div className="space-y-3">
          <div className="grid gap-3 md:grid-cols-4">
            <MetricBox label="Stand" value={stringValue(item.as_of) || "-"} detail={stringValue(item.fiscal_period) || "Periode fehlt"} />
            <MetricBox label="Gewinnmarge" value={pct(asNumber(item.profit_margin_pct))} detail="Profit Margin" />
            <MetricBox label="ROE" value={pct(asNumber(item.roe_pct))} detail="Return on Equity" />
            <MetricBox label="EPS 4Q Summe" value={formatNumber(asNumber(item.trailing_eps))} detail="Summe letzte vier Quartale" />
          </div>
          <div className="grid gap-3 xl:grid-cols-2">
            <MiniHistory title="EPS letzte 3 Quartale" rows={epsQuarter} labelKey="fiscal_period" valueKey="eps_growth_yoy_pct" />
            <MiniHistory title="EPS letzte 3 Jahre" rows={epsAnnual} labelKey="fiscal_year" valueKey="eps_growth_yoy_pct" />
            <MiniHistory title="Umsatz letzte 3 Quartale" rows={revenueQuarter} labelKey="fiscal_period" valueKey="revenue_growth_yoy_pct" />
            <MiniHistory title="Umsatz letzte 3 Jahre" rows={revenueAnnual} labelKey="fiscal_year" valueKey="revenue_growth_yoy_pct" />
          </div>
          {roeHistory.length > 0 ? (
            <MiniHistory title="ROE Historie" rows={roeHistory} labelKey="fiscal_year" valueKey="roe_pct" />
          ) : null}
        </div>
      )}
    </div>
  );
}

function MiniHistory({
  labelKey,
  rows,
  title,
  valueKey
}: {
  labelKey: string;
  rows: Record<string, unknown>[];
  title: string;
  valueKey: string;
}) {
  return (
    <div className="rounded border border-[#242a33] p-3">
      <div className="mb-2 text-sm font-medium">{title}</div>
      {rows.length === 0 ? (
        <div className="text-sm text-[#7f8794]">Keine Daten gespeichert.</div>
      ) : (
        <div className="space-y-2">
          {rows.map((row, index) => {
            const value = asNumber(row[valueKey]);
            return (
              <div key={`${String(row[labelKey])}-${index}`} className="flex items-center justify-between gap-3 text-sm">
                <span className="text-[#a0a7b4]">{stringValue(row[labelKey]) || `#${index + 1}`}</span>
                <span className={value === null ? "text-[#7f8794]" : value >= 20 ? "text-emerald-200" : "text-rose-200"}>
                  {pct(value)}
                </span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function InstitutionalSnapshot({ item, source }: { item: Record<string, unknown>; source: string }) {
  return (
    <div className="rounded border border-[#2d333d] p-3">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 font-medium">
          <Building2 className="size-4 text-[#8ea4c8]" />
          Institutionelle 13F-Trends
        </div>
        <StatusChip tone={item.ticker ? toneFor13F(stringValue(item.trend)) : "warning"}>{stringValue(item.trend) || source || "missing"}</StatusChip>
      </div>
      {!item.ticker ? (
        <div className="text-sm text-[#a0a7b4]">Keine 13F-Trends im Snapshot.</div>
      ) : (
        <div className="grid gap-3 md:grid-cols-4">
          <MetricBox label="Alle 13F-Halter" value={formatNumber(asNumber(item.holder_count))} detail={deltaText(asNumber(item.holder_count_delta))} />
          <MetricBox label="Große Institutionen" value={formatNumber(asNumber(item.large_holder_count))} detail={deltaText(asNumber(item.large_holder_delta))} />
          <MetricBox label="Marktwert" value={usd(asNumber(item.total_value_usd))} detail={pct(asNumber(item.total_value_delta_pct))} />
          <MetricBox label="Aktien" value={compact(asNumber(item.total_shares))} detail={pct(asNumber(item.total_shares_delta_pct))} />
        </div>
      )}
    </div>
  );
}

function RelativeStrengthSnapshot({ found, item }: { found: boolean; item: Record<string, unknown> }) {
  return (
    <div className="rounded border border-[#2d333d] p-3">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 font-medium">
          <TrendingUp className="size-4 text-[#8ea4c8]" />
          Relative Stärke
        </div>
        <StatusChip tone={found ? toneForRating(asNumber(item.rating)) : "warning"}>{found ? formatNumber(asNumber(item.rating)) : "missing"}</StatusChip>
      </div>
      {!found ? (
        <div className="text-sm text-[#a0a7b4]">Kein RS-Rating im Snapshot.</div>
      ) : (
        <div className="grid gap-3 md:grid-cols-4">
          <MetricBox label="Bewertung" value={formatNumber(asNumber(item.rating))} detail={`Universe ${formatNumber(asNumber(item.universe_size))}`} />
          <MetricBox label="3M Return" value={pct(asNumber(item.ret_3m))} detail={`1M ${pct(asNumber(item.ret_1m))}`} />
          <MetricBox label="6M vs SPY" value={pct(asNumber(item.excess_return_6m))} detail={`12M vs SPY ${pct(asNumber(item.excess_return_12m))}`} />
          <MetricBox
            label="RS-Linie"
            value={asBoolean(item.new_high_52w) ? "New High" : asBoolean(item.near_high_52w) ? "Near High" : "Off High"}
            detail={`21-EMA ${formatNumber(asNumber(item.rs_ema21))} · 50-EMA ${formatNumber(asNumber(item.rs_ema50))}`}
          />
        </div>
      )}
    </div>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs uppercase text-[#a0a7b4]">{label}</span>
      {children}
    </label>
  );
}

function MetricBox({ label, value, detail }: { label: string; value: string; detail: string }) {
  return (
    <div className="rounded border border-[#242a33] bg-[#111419] p-3 print:border-gray-300 print:bg-white">
      <div className="text-xs uppercase text-[#a0a7b4] print:text-gray-600">{label}</div>
      <div className="mt-1 text-lg font-semibold tabular-nums">{value}</div>
      <div className="mt-1 text-xs text-[#7f8794] print:text-gray-600">{detail}</div>
    </div>
  );
}

function TextBlock({ title, text }: { title: string; text: string }) {
  return (
    <div className="rounded border border-[#242a33] bg-[#111419] p-3 print:border-gray-300 print:bg-white">
      <div className="text-xs uppercase text-[#a0a7b4] print:text-gray-600">{title}</div>
      <div className="mt-2 whitespace-pre-wrap text-sm leading-6 text-[#c9d0da] print:text-gray-900">{text}</div>
    </div>
  );
}

function ImageUpload({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
  async function handleFile(file?: File) {
    if (!file) return;
    const dataUrl = await readFileAsDataUrl(file);
    onChange(dataUrl);
  }

  return (
    <div className="rounded border border-[#242a33] bg-[#111419] p-4">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div className="text-sm font-medium">{label}</div>
        <ImagePlus className="size-4 text-[#8ea4c8]" />
      </div>
      {value ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img alt={label} className="mb-3 max-h-56 w-full rounded border border-[#2d333d] object-contain" src={value} />
      ) : (
        <div className="mb-3 flex h-32 items-center justify-center rounded border border-dashed border-[#2d333d] text-sm text-[#7f8794]">
          Noch kein Bild hochgeladen
        </div>
      )}
      <input
        accept="image/*"
        className="block w-full text-sm text-[#a0a7b4] file:mr-3 file:rounded file:border-0 file:bg-[#26333a] file:px-3 file:py-2 file:text-sm file:text-emerald-100"
        type="file"
        onChange={(event) => void handleFile(event.target.files?.[0])}
      />
      {value && (
        <button className="mt-2 text-xs text-rose-200 hover:text-rose-100" type="button" onClick={() => onChange("")}>
          Bild entfernen
        </button>
      )}
    </div>
  );
}

function ChartImage({ label, src }: { label: string; src: string }) {
  return (
    <div className="rounded border border-[#242a33] bg-[#111419] p-3 print:border-gray-300 print:bg-white">
      <div className="mb-2 text-xs uppercase text-[#a0a7b4] print:text-gray-600">{label}</div>
      {src ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img alt={label} className="max-h-96 w-full rounded object-contain" src={src} />
      ) : (
        <div className="rounded border border-dashed border-[#2d333d] p-8 text-center text-sm text-[#7f8794] print:text-gray-600">
          Kein Chartbild gespeichert.
        </div>
      )}
    </div>
  );
}

function emptyDraft(ticker: string, type: TradeJournalEntryType): JournalDraft {
  return {
    ticker,
    entry_type: type,
    trade_date: new Date().toISOString().slice(0, 10),
    price: "",
    shares: "",
    stop_price: "",
    linked_entry_id: "",
    status: type === "buy" ? "open" : "closed",
    basis_text: "",
    alternative_entry: false,
    alternative_entry_text: "",
    primary_reasons: "",
    sell_reason: "",
    close_with_related_buy: type === "sell",
    questionnaire: {},
    chart_images: { daily_chart: "", weekly_chart: "" }
  };
}

function fromDefaults(defaults: TradeJournalDefaults): JournalDraft {
  return {
    ...emptyDraft(defaults.ticker, defaults.entry_type),
    trade_date: defaults.trade_date,
    price: defaults.price === null || defaults.price === undefined ? "" : String(round(defaults.price, 2)),
    shares: defaults.shares === null || defaults.shares === undefined ? "" : String(defaults.shares),
    stop_price: defaults.stop_price === null || defaults.stop_price === undefined ? "" : String(round(defaults.stop_price, 2)),
    linked_entry_id: defaults.open_buy_entry_id ?? "",
    close_with_related_buy: defaults.entry_type === "sell"
  };
}

function fromEntry(entry: TradeJournalEntryDetail): JournalDraft {
  return {
    ticker: entry.ticker,
    entry_type: entry.entry_type,
    trade_date: entry.trade_date,
    price: entry.price === null || entry.price === undefined ? "" : String(entry.price),
    shares: entry.shares === null || entry.shares === undefined ? "" : String(entry.shares),
    stop_price: entry.stop_price === null || entry.stop_price === undefined ? "" : String(entry.stop_price),
    linked_entry_id: entry.linked_entry_id ?? "",
    status: entry.status,
    basis_text: entry.basis_text,
    alternative_entry: entry.alternative_entry,
    alternative_entry_text: entry.alternative_entry_text,
    primary_reasons: entry.primary_reasons,
    sell_reason: entry.sell_reason,
    close_with_related_buy: false,
    questionnaire: stringRecord(entry.questionnaire),
    chart_images: entry.chart_images
  };
}

function toRequest(draft: JournalDraft): TradeJournalEntryRequest {
  return {
    ticker: normalizeTicker(draft.ticker),
    entry_type: draft.entry_type,
    trade_date: draft.trade_date || null,
    price: numberFromString(draft.price),
    shares: numberFromString(draft.shares),
    stop_price: numberFromString(draft.stop_price),
    linked_entry_id: draft.linked_entry_id || null,
    status: draft.status,
    basis_text: draft.basis_text,
    alternative_entry: draft.alternative_entry,
    alternative_entry_text: draft.alternative_entry_text,
    primary_reasons: draft.primary_reasons,
    sell_reason: draft.sell_reason,
    close_with_related_buy: draft.close_with_related_buy,
    questionnaire: draft.questionnaire,
    chart_images: draft.chart_images
  };
}

function normalizeTicker(value: string) {
  return value.trim().toUpperCase();
}

function numberFromString(value: string) {
  if (!value.trim()) return null;
  const parsed = Number(value.replace(",", "."));
  return Number.isFinite(parsed) ? parsed : null;
}

function stopDistancePct(price: number | null, stop: number | null) {
  if (!price || !stop) return null;
  return ((price - stop) / price) * 100;
}

function readFileAsDataUrl(file: File) {
  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result ?? ""));
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}

function checksFromSnapshot(snapshot: Record<string, unknown>): SnapshotCheck[] {
  const assessment = assessmentFromSnapshot(snapshot);
  const checks = assessment.checks;
  if (!Array.isArray(checks)) return [];
  return checks.filter((item): item is SnapshotCheck => typeof item === "object" && item !== null);
}

function checklistSummaryFromSnapshot(snapshot: Record<string, unknown>) {
  const checks = checksFromSnapshot(snapshot);
  if (checks.length === 0) return "";
  const passed = checks.filter((check) => check.passed).map((check) => check.label).filter(Boolean);
  const failed = checks.filter((check) => !check.passed).map((check) => check.label).filter(Boolean);
  return [
    `Erfüllt (${passed.length}/${checks.length}): ${passed.join(", ") || "-"}`,
    `Nicht erfüllt (${failed.length}/${checks.length}): ${failed.join(", ") || "-"}`
  ].join("\n");
}

function chartSignalsFromSnapshot(snapshot: Record<string, unknown>): SnapshotSignal[] {
  const assessment = assessmentFromSnapshot(snapshot);
  const signals = assessment.chart_signals;
  if (!Array.isArray(signals)) return [];
  return signals.filter((item): item is SnapshotSignal => typeof item === "object" && item !== null);
}

function assessmentFromSnapshot(snapshot: Record<string, unknown>) {
  const nested = snapshot.assessment;
  return isRecord(nested) ? nested : snapshot;
}

function marketPhaseLabel(snapshot: Record<string, unknown>) {
  const label = nestedValue(snapshot, "ampel.phase_label") ?? nestedValue(snapshot, "overview.phase_label");
  return typeof label === "string" && label ? label : "-";
}

function marketMaDetail(snapshot: Record<string, unknown>) {
  const behavior = nestedValue(snapshot, "ampel.ma_behavior");
  if (!isRecord(behavior)) return "MA-Verhalten nicht verfügbar";
  const parts = [
    behavior.above_ema21 ? "über 21-EMA" : "unter 21-EMA",
    behavior.above_sma50 ? "über 50-SMA" : "unter 50-SMA",
    behavior.above_sma200 ? "über 200-SMA" : "unter 200-SMA",
    behavior.correct_order ? "Ordnung korrekt" : "Ordnung nicht bestätigt"
  ];
  return parts.join(" · ");
}

function nestedValue(source: Record<string, unknown>, path: string): unknown {
  let current: unknown = source;
  for (const part of path.split(".")) {
    if (!isRecord(current)) return undefined;
    current = current[part];
  }
  return current;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function recordValue(value: unknown): Record<string, unknown> {
  return isRecord(value) ? value : {};
}

function recordArray(value: unknown): Record<string, unknown>[] {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is Record<string, unknown> => isRecord(item));
}

function stringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is string => typeof item === "string" && item.trim().length > 0);
}

function stringValue(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function asNumber(value: unknown) {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function asBoolean(value: unknown) {
  return typeof value === "boolean" ? value : false;
}

function toneValue(value: unknown): Tone {
  return value === "good" || value === "neutral" || value === "warning" || value === "bad" ? value : "neutral";
}

function money(value?: number | null, currency = "USD") {
  if (value === null || value === undefined || !Number.isFinite(value)) return "-";
  return `${value.toLocaleString("de-DE", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${currency}`;
}

function formatNumber(value?: number | null) {
  if (value === null || value === undefined || !Number.isFinite(value)) return "-";
  return value.toLocaleString("de-DE", { maximumFractionDigits: 3 });
}

function pct(value?: number | null) {
  if (value === null || value === undefined || !Number.isFinite(value)) return "-";
  return `${value >= 0 ? "+" : ""}${value.toFixed(1)}%`;
}

function deltaText(value?: number | null) {
  if (value === null || value === undefined || !Number.isFinite(value)) return "-";
  return `${value >= 0 ? "+" : ""}${value.toLocaleString("de-DE")} vs. Vorperiode`;
}

function compact(value?: number | null) {
  if (value === null || value === undefined || !Number.isFinite(value)) return "-";
  if (Math.abs(value) >= 1_000_000_000) return `${(value / 1_000_000_000).toFixed(1)} Mrd.`;
  if (Math.abs(value) >= 1_000_000) return `${(value / 1_000_000).toFixed(1)} Mio.`;
  return value.toLocaleString("de-DE", { maximumFractionDigits: 0 });
}

function usd(value?: number | null) {
  if (value === null || value === undefined || !Number.isFinite(value)) return "-";
  return `$${compact(value)}`;
}

function atrRegime(value?: number | null) {
  if (value === null || value === undefined || !Number.isFinite(value)) return "ATR nicht verfügbar";
  if (value < 2.5) return "Ruhig";
  if (value < 4) return "Lebhaft";
  if (value < 8) return "Stürmisch";
  return "Explosiv";
}

function betaRegime(value?: number | null) {
  if (value === null || value === undefined || !Number.isFinite(value)) return "Beta nicht verfügbar";
  if (value < 0.98) return "Defensiv";
  if (value <= 1.02) return "Marktnah";
  if (value <= 2) return "Wachstumsorientiert";
  return "Hochdynamisch";
}

function toneForRating(value?: number | null): Tone {
  if (value === null || value === undefined || !Number.isFinite(value)) return "neutral";
  if (value >= 80) return "good";
  if (value >= 60) return "neutral";
  if (value >= 40) return "warning";
  return "bad";
}

function toneFor13F(value: string): Tone {
  if (value === "positive" || value === "new") return "good";
  if (value === "negative") return "bad";
  if (value === "neutral") return "neutral";
  return "warning";
}

function holdingDays(start: string, end: string) {
  const startDate = new Date(`${start}T00:00:00`);
  const endDate = new Date(`${end}T00:00:00`);
  const days = Math.round((endDate.getTime() - startDate.getTime()) / 86_400_000);
  return Number.isFinite(days) ? `${Math.max(0, days)} Tage` : "-";
}

function historySummary(rows: Record<string, unknown>[], valueKey: string) {
  if (rows.length === 0) return "-";
  return rows.slice(0, 3).map((row) => pct(asNumber(row[valueKey]))).join(" · ");
}

function round(value: number, digits: number) {
  const factor = 10 ** digits;
  return Math.round(value * factor) / factor;
}

function stringRecord(value: Record<string, unknown>): Record<string, string> {
  return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, String(item ?? "")]));
}

function printEntry(entry: TradeJournalEntryDetail) {
  const popup = window.open("", "_blank", "width=1100,height=900");
  if (!popup) {
    window.print();
    return;
  }
  popup.document.write(printHtml(entry));
  popup.document.close();
  popup.focus();
  popup.print();
}

function printHtml(entry: TradeJournalEntryDetail) {
  const assessment = assessmentFromSnapshot(entry.stock_snapshot);
  const scores = recordValue(assessment.scores);
  const metrics = recordValue(assessment.metrics);
  const fundamentals = recordValue(entry.stock_snapshot.fundamentals);
  const fundamentalItem = recordValue(fundamentals.item);
  const institutionalItem = recordValue(recordValue(entry.stock_snapshot.institutional_13f).item);
  const rsItem = recordValue(recordValue(entry.stock_snapshot.relative_strength).item);
  const checks = checksFromSnapshot(entry.stock_snapshot);
  const checkHtml = checks.map((check) => `
    <li class="${check.passed ? "good" : "bad"}">
      <strong>${escapeHtml(check.label ?? "")}</strong><br />
      <span>${escapeHtml(check.detail ?? "")}</span>
    </li>
  `).join("");
  const daily = entry.chart_images.daily_chart ? `<img src="${entry.chart_images.daily_chart}" alt="Tageschart" />` : "<p>Kein Tageschart gespeichert.</p>";
  const weekly = entry.chart_images.weekly_chart ? `<img src="${entry.chart_images.weekly_chart}" alt="Wochenchart" />` : "<p>Kein Wochenchart gespeichert.</p>";
  return `<!doctype html>
<html lang="de">
<head>
  <meta charset="utf-8" />
  <title>${escapeHtml(entry.title)}</title>
  <style>
    body { font-family: Arial, sans-serif; margin: 32px; color: #111827; }
    h1 { margin: 0 0 8px; }
    h2 { margin-top: 28px; border-bottom: 1px solid #d1d5db; padding-bottom: 6px; }
    .grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
    .box { border: 1px solid #d1d5db; border-radius: 6px; padding: 12px; margin-top: 10px; }
    .muted { color: #6b7280; font-size: 12px; }
    li { margin-bottom: 8px; padding: 8px; border: 1px solid #d1d5db; border-radius: 6px; }
    li.good { border-color: #86efac; background: #f0fdf4; }
    li.bad { border-color: #fecdd3; background: #fff1f2; }
    img { max-width: 100%; max-height: 520px; object-fit: contain; border: 1px solid #d1d5db; border-radius: 6px; }
    @media print { body { margin: 18mm; } }
  </style>
</head>
<body>
  <h1>${escapeHtml(entry.title)}</h1>
  <div class="muted">${escapeHtml(entry.summary)} · Status ${escapeHtml(entry.status)}</div>
  <div class="grid">
    <div class="box"><div class="muted">Preis</div><strong>${escapeHtml(money(entry.price))}</strong></div>
    <div class="box"><div class="muted">Stopp</div><strong>${escapeHtml(money(entry.stop_price))}</strong></div>
    <div class="box"><div class="muted">Marktampel</div><strong>${escapeHtml(marketPhaseLabel(entry.market_snapshot))}</strong></div>
  </div>
  <h2>Aktienbewertung</h2>
  <div class="grid">
    <div class="box"><div class="muted">Gesamtscore</div><strong>${escapeHtml(formatNumber(asNumber(scores.overall)))}</strong></div>
    <div class="box"><div class="muted">Technisch</div><strong>${escapeHtml(formatNumber(asNumber(scores.technical)))}</strong></div>
    <div class="box"><div class="muted">Fundamental</div><strong>${escapeHtml(formatNumber(asNumber(scores.fundamental)))}</strong></div>
    <div class="box"><div class="muted">Aktueller Preis</div><strong>${escapeHtml(money(asNumber(metrics.last_close)))}</strong></div>
    <div class="box"><div class="muted">ATR</div><strong>${escapeHtml(pct(asNumber(metrics.atr_pct)))}</strong></div>
    <div class="box"><div class="muted">RS-Rating</div><strong>${escapeHtml(formatNumber(asNumber(metrics.rs_rating)))}</strong></div>
  </div>
  <h2>Fundamental / 13F / RS</h2>
  <div class="grid">
    <div class="box"><div class="muted">EPS Quartale</div><strong>${escapeHtml(historySummary(recordArray(fundamentalItem.eps_quarter_history), "eps_growth_yoy_pct"))}</strong></div>
    <div class="box"><div class="muted">Umsatz Quartale</div><strong>${escapeHtml(historySummary(recordArray(fundamentalItem.revenue_quarter_history), "revenue_growth_yoy_pct"))}</strong></div>
    <div class="box"><div class="muted">13F Halter</div><strong>${escapeHtml(formatNumber(asNumber(institutionalItem.holder_count)))}</strong></div>
    <div class="box"><div class="muted">13F Trend</div><strong>${escapeHtml(stringValue(institutionalItem.trend) || "-")}</strong></div>
    <div class="box"><div class="muted">RS 6M vs SPY</div><strong>${escapeHtml(pct(asNumber(rsItem.excess_return_6m)))}</strong></div>
    <div class="box"><div class="muted">Beta</div><strong>${escapeHtml(formatNumber(asNumber(metrics.beta)))}</strong></div>
  </div>
  <h2>Notizen</h2>
  <div class="box">${escapeHtml(entry.primary_reasons || entry.sell_reason || entry.basis_text || "-").replace(/\n/g, "<br />")}</div>
  <h2>Checkliste</h2>
  <ul>${checkHtml || "<li>Keine Checkliste gespeichert.</li>"}</ul>
  <h2>Charts</h2>
  <div class="box">${daily}</div>
  <div class="box">${weekly}</div>
</body>
</html>`;
}

function escapeHtml(value: string) {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}
