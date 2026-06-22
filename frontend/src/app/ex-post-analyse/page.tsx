"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ClipboardCheck, Save, Search } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { StatusChip } from "@/components/ui/status-chip";
import { api } from "@/lib/api/client";
import type {
  SellDiagnostics,
  SellPostMortemCheck,
  SellPostMortemNote,
  SellPostMortemNoteRequest
} from "@/lib/types/api";

export default function ExPostAnalysePage() {
  return (
    <Suspense fallback={<ExPostAnalyseFallback />}>
      <ExPostAnalyseContent />
    </Suspense>
  );
}

function ExPostAnalyseContent() {
  const queryClient = useQueryClient();
  const router = useRouter();
  const searchParams = useSearchParams();
  const initialTicker = normalizeTicker(searchParams.get("ticker")) || "NVDA";
  const [tickerInput, setTickerInput] = useState(initialTicker);
  const [activeTicker, setActiveTicker] = useState(initialTicker);
  const [drafts, setDrafts] = useState<Record<string, SellPostMortemNoteRequest>>({});

  const diagnostics = useQuery({
    queryKey: ["sell-diagnostics", activeTicker],
    queryFn: () => api.sellDiagnostics(activeTicker),
    enabled: Boolean(activeTicker)
  });

  const saveNote = useMutation({
    mutationFn: (payload: SellPostMortemNoteRequest) => api.saveSellPostMortemNote(activeTicker, payload),
    onSuccess: (payload, variables) => {
      queryClient.setQueryData(
        ["sell-diagnostics", activeTicker],
        diagnostics.data ? { ...diagnostics.data, post_mortem_notes: payload.notes } : diagnostics.data
      );
      setDrafts((previous) => {
        const next = { ...previous };
        delete next[variables.check_key];
        return next;
      });
    }
  });

  function loadTicker() {
    const normalized = normalizeTicker(tickerInput);
    if (!normalized) return;
    setActiveTicker(normalized);
    setDrafts({});
    router.replace(`/ex-post-analyse?ticker=${encodeURIComponent(normalized)}`, { scroll: false });
  }

  function updateDraft(checkKey: string, patch: Partial<SellPostMortemNoteRequest>) {
    const stored = diagnostics.data?.post_mortem_notes.find((note) => note.check_key === checkKey);
    setDrafts((previous) => ({
      ...previous,
      [checkKey]: {
        check_key: checkKey,
        note: previous[checkKey]?.note ?? stored?.note ?? "",
        action: previous[checkKey]?.action ?? stored?.action ?? "",
        status: previous[checkKey]?.status ?? stored?.status ?? "open",
        ...patch
      }
    }));
  }

  function saveDraft(checkKey: string) {
    const draft = drafts[checkKey];
    if (!draft) return;
    saveNote.mutate(draft);
  }

  return (
    <div className="space-y-5">
      <div className="rounded border border-[#2d333d] bg-[#171a20] p-5">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <div className="flex items-center gap-2 text-sm text-[#a0a7b4]">
              <ClipboardCheck className="size-4 text-[#8ea4c8]" />
              Sell Review
            </div>
            <h1 className="mt-1 text-3xl font-semibold">Ex Post Analyse</h1>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-[#a0a7b4]">
              Post-Mortem-Checks nach Verkaufsentscheidungen. Die aktive Strategie bleibt im Sell Monitor; hier werden nur Review-Notizen gepflegt.
            </p>
          </div>

          <form
            className="flex w-full flex-col gap-2 sm:flex-row lg:max-w-md"
            onSubmit={(event) => {
              event.preventDefault();
              loadTicker();
            }}
          >
            <label className="sr-only" htmlFor="ex-post-ticker">Ticker</label>
            <input
              id="ex-post-ticker"
              className="min-h-10 flex-1 rounded border border-[#2d333d] bg-[#111419] px-3 py-2 text-sm uppercase outline-none transition focus:border-emerald-300/70"
              placeholder="Ticker"
              value={tickerInput}
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
      </div>

      <DiagnosticsStatus diagnostics={diagnostics.data} isLoading={diagnostics.isLoading} ticker={activeTicker} />

      {diagnostics.error && (
        <section className="rounded border border-rose-300/30 bg-rose-400/10 p-5 text-sm text-rose-100">
          Ex-Post-Daten konnten nicht geladen werden: {(diagnostics.error as Error).message}
        </section>
      )}

      {diagnostics.isLoading && (
        <section className="grid gap-3 md:grid-cols-2">
          {[0, 1, 2, 3].map((item) => (
            <div key={item} className="h-52 animate-pulse rounded border border-[#242a33] bg-[#171a20]" />
          ))}
        </section>
      )}

      {diagnostics.data && (
        <section className="grid gap-3 md:grid-cols-2">
          {diagnostics.data.post_mortem.map((check) => (
            <PostMortemCard
              key={check.key}
              check={check}
              draft={drafts[check.key]}
              note={diagnostics.data.post_mortem_notes.find((item) => item.check_key === check.key)}
              saving={saveNote.isPending && saveNote.variables?.check_key === check.key}
              onDraftChange={updateDraft}
              onSave={saveDraft}
            />
          ))}
        </section>
      )}
    </div>
  );
}

function ExPostAnalyseFallback() {
  return (
    <div className="space-y-5">
      <div className="rounded border border-[#2d333d] bg-[#171a20] p-5">
        <div className="h-8 w-64 animate-pulse rounded bg-[#242a33]" />
        <div className="mt-3 h-4 w-96 max-w-full animate-pulse rounded bg-[#242a33]" />
      </div>
    </div>
  );
}

function normalizeTicker(value: string | null | undefined) {
  return String(value || "").trim().toUpperCase();
}

function DiagnosticsStatus({
  diagnostics,
  isLoading,
  ticker
}: {
  diagnostics?: SellDiagnostics;
  isLoading: boolean;
  ticker: string;
}) {
  if (isLoading) {
    return (
      <section className="rounded border border-[#2d333d] bg-[#171a20] p-5">
        <div className="h-5 w-44 animate-pulse rounded bg-[#242a33]" />
        <div className="mt-3 h-4 w-72 animate-pulse rounded bg-[#242a33]" />
      </section>
    );
  }

  if (!diagnostics) {
    return (
      <section className="rounded border border-[#2d333d] bg-[#171a20] p-5 text-sm text-[#a0a7b4]">
        Keine Ex-Post-Daten für {ticker} geladen.
      </section>
    );
  }

  return (
    <section className="rounded border border-[#2d333d] bg-[#171a20] p-5">
      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div>
          <h2 className="text-base font-semibold">{diagnostics.ticker}</h2>
          <p className="mt-1 text-sm text-[#a0a7b4]">Stand {diagnostics.as_of}</p>
        </div>
        <StatusChip tone="neutral">{diagnostics.post_mortem.length} Checks</StatusChip>
      </div>
      <div className="mt-4 rounded border border-[#242a33] bg-[#111419] p-4 text-sm leading-6 text-[#d8dde6]">
        {diagnostics.next_action}
      </div>
    </section>
  );
}

function PostMortemCard({
  check,
  draft,
  note,
  saving,
  onDraftChange,
  onSave
}: {
  check: SellPostMortemCheck;
  draft?: SellPostMortemNoteRequest;
  note?: SellPostMortemNote;
  saving: boolean;
  onDraftChange: (checkKey: string, patch: Partial<SellPostMortemNoteRequest>) => void;
  onSave: (checkKey: string) => void;
}) {
  const value = draft ?? {
    check_key: check.key,
    note: note?.note ?? "",
    action: note?.action ?? "",
    status: note?.status ?? "open"
  };
  const dirty = Boolean(draft);

  return (
    <article className="rounded border border-[#242a33] bg-[#171a20] p-4">
      <div className="mb-3 flex items-start justify-between gap-3">
        <div>
          <h3 className="font-medium">{check.label}</h3>
          <p className="mt-1 text-sm leading-6 text-[#a0a7b4]">{check.evidence}</p>
        </div>
        <StatusChip tone={check.tone}>{statusLabel(check.status)}</StatusChip>
      </div>

      <div className="space-y-3">
        <label className="block text-xs text-[#a0a7b4]">
          Notiz
          <textarea
            className="mt-1 min-h-24 w-full resize-y rounded border border-[#2d333d] bg-[#111419] px-3 py-2 text-sm text-[#d8dde6] outline-none transition focus:border-emerald-300/70"
            value={value.note}
            onChange={(event) => onDraftChange(check.key, { note: event.target.value })}
          />
        </label>
        <label className="block text-xs text-[#a0a7b4]">
          Nächste Maßnahme
          <input
            className="mt-1 w-full rounded border border-[#2d333d] bg-[#111419] px-3 py-2 text-sm text-[#d8dde6] outline-none transition focus:border-emerald-300/70"
            value={value.action}
            onChange={(event) => onDraftChange(check.key, { action: event.target.value })}
          />
        </label>
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <select
            className="rounded border border-[#2d333d] bg-[#111419] px-3 py-2 text-sm text-[#d8dde6]"
            value={value.status}
            onChange={(event) =>
              onDraftChange(check.key, { status: event.target.value as SellPostMortemNoteRequest["status"] })
            }
          >
            <option value="open">offen</option>
            <option value="done">erledigt</option>
            <option value="dismissed">verworfen</option>
          </select>
          <button
            className="inline-flex items-center justify-center gap-2 rounded border border-emerald-300/35 bg-emerald-300/10 px-3 py-2 text-sm text-emerald-100 transition hover:border-emerald-200 disabled:cursor-not-allowed disabled:opacity-50"
            disabled={!dirty || saving}
            type="button"
            onClick={() => onSave(check.key)}
          >
            <Save size={15} />
            {saving ? "Speichert" : note ? "Aktualisieren" : "Speichern"}
          </button>
        </div>
      </div>
    </article>
  );
}

function statusLabel(status: SellPostMortemCheck["status"]) {
  if (status === "ok") return "ok";
  if (status === "fail") return "kritisch";
  return "prüfen";
}
