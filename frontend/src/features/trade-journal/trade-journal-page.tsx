"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import {
  BookOpenCheck,
  CheckCircle2,
  Edit3,
  FileDown,
  ImagePlus,
  Plus,
  Save,
  Search,
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
            <JournalChecklist entry={selectedEntry} onEdit={() => void loadEntry(selectedEntry.id, "edit")} />
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

function JournalChecklist({ entry, onEdit }: { entry: TradeJournalEntryDetail; onEdit: () => void }) {
  const checks = checksFromSnapshot(entry.stock_snapshot);
  const marketLabel = marketPhaseLabel(entry.market_snapshot);
  const portfolio = entry.portfolio_snapshot;
  return (
    <article className="rounded border border-[#2d333d] bg-[#171a20] p-5 print:bg-white print:text-black" id="trade-journal-print">
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

      <div className="mt-4 grid gap-3 md:grid-cols-3">
        <MetricBox label="Preis" value={money(entry.price)} detail={`${entry.shares ?? "-"} Stück`} />
        <MetricBox label="Stopp" value={money(entry.stop_price)} detail={entry.stop_distance_pct === null || entry.stop_distance_pct === undefined ? "Abstand offen" : `${entry.stop_distance_pct.toFixed(2)}% Abstand`} />
        <MetricBox label="P&L" value={entry.realized_pnl_pct === null || entry.realized_pnl_pct === undefined ? "-" : `${entry.realized_pnl_pct.toFixed(2)}%`} detail={money(entry.realized_pnl_eur, "EUR")} />
      </div>

      <div className="mt-4 grid gap-3 md:grid-cols-2">
        <TextBlock title="Kaufbasis / Setup" text={entry.basis_text || "-"} />
        <TextBlock title="Kauf- oder Verkaufsgrund" text={entry.entry_type === "sell" ? entry.sell_reason || "-" : entry.primary_reasons || "-"} />
      </div>

      <div className="mt-4 grid gap-3 md:grid-cols-3">
        <MetricBox label="Marktampel S&P 500" value={marketLabel} detail={marketMaDetail(entry.market_snapshot)} />
        <MetricBox label="Positionsgröße EUR" value={money(asNumber(portfolio.position_size_eur), "EUR")} detail={`FX ${nestedValue(portfolio, "fx_rate.rate") ?? "-"}`} />
        <MetricBox
          label="Beta-Balancer / Risiko"
          value={formatNumber(asNumber(portfolio.beta_balancer_score))}
          detail={`Risikobeitrag ${formatNumber(asNumber(portfolio.risk_contribution))}`}
        />
      </div>

      <div className="mt-4 rounded border border-[#242a33] bg-[#111419] p-4 print:border-gray-300 print:bg-white">
        <div className="mb-3 flex items-center justify-between gap-3">
          <h3 className="text-base font-semibold">Gespeicherte Stock-Checkliste</h3>
          <StatusChip tone="neutral">{checks.length}</StatusChip>
        </div>
        {checks.length === 0 ? (
          <div className="text-sm text-[#a0a7b4] print:text-gray-700">Keine Checkliste im Snapshot vorhanden.</div>
        ) : (
          <div className="grid gap-2 md:grid-cols-2">
            {checks.map((check, index) => (
              <div key={`${check.label}-${index}`} className="flex gap-2 rounded border border-[#242a33] p-3 text-sm print:border-gray-300">
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
            ))}
          </div>
        )}
      </div>

      {Object.keys(entry.questionnaire).length > 0 && (
        <div className="mt-4 rounded border border-[#242a33] bg-[#111419] p-4 print:border-gray-300 print:bg-white">
          <h3 className="text-base font-semibold">Ex-Post-Fragebogen</h3>
          <div className="mt-3 space-y-3">
            {exPostQuestions.map(([key, label]) => (
              <TextBlock key={key} title={label} text={String(entry.questionnaire[key] ?? "-")} />
            ))}
          </div>
        </div>
      )}

      <div className="mt-4 grid gap-3 md:grid-cols-2">
        <ChartImage label="Tageschart" src={entry.chart_images.daily_chart} />
        <ChartImage label="Wochenchart" src={entry.chart_images.weekly_chart} />
      </div>
    </article>
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
  const checks = snapshot.checks;
  if (!Array.isArray(checks)) return [];
  return checks.filter((item): item is SnapshotCheck => typeof item === "object" && item !== null);
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

function asNumber(value: unknown) {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function money(value?: number | null, currency = "USD") {
  if (value === null || value === undefined || !Number.isFinite(value)) return "-";
  return `${value.toLocaleString("de-DE", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${currency}`;
}

function formatNumber(value?: number | null) {
  if (value === null || value === undefined || !Number.isFinite(value)) return "-";
  return value.toLocaleString("de-DE", { maximumFractionDigits: 3 });
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
