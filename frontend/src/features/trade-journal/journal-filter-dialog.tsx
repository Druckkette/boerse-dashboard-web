"use client";
import { useEffect, useRef, useState, type FormEvent } from "react";
import type { TradeJournalFilters } from "@/lib/types/api";
export function JournalFilterDialog({
  filters,
  onClose,
  onApply,
}: {
  filters: TradeJournalFilters;
  onClose: () => void;
  onApply: (values: Record<string, string> & { query: string }) => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const [draft, setDraft] = useState({
    query: filters.query || "",
    type: filters.entry_type || "",
    status: filters.status || "",
    source: filters.source || "",
    from: filters.date_from || "",
    to: filters.date_to || "",
    sort: filters.sort || "newest",
  });
  useEffect(() => {
    const element = ref.current;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    element?.showModal();
    return () => {
      element?.close();
      document.body.style.overflow = previous;
    };
  }, []);
  function apply(event: FormEvent) {
    event.preventDefault();
    onApply({ ...draft, query: draft.query.trim() });
  }
  function field(key: keyof typeof draft, value: string) {
    setDraft((current) => ({ ...current, [key]: value }));
  }
  return (
    <dialog
      ref={ref}
      aria-label="Journalfilter"
      onCancel={onClose}
      className="product-dialog fixed inset-0 m-auto max-h-[90dvh] w-[min(560px,96vw)] overflow-y-auto rounded-2xl bg-white p-5 shadow-2xl backdrop:bg-slate-900/50"
    >
      <form onSubmit={apply} className="space-y-4">
        <h2 className="text-lg font-semibold">Journal filtern</h2>
        <label className="block text-sm">
          Aktie, Ticker oder ISIN
          <input
            className="input-dark mt-1"
            value={draft.query}
            onChange={(event) => field("query", event.target.value)}
          />
        </label>
        {(
          [
            [
              "type",
              "Art",
              [
                ["", "Alle Arten"],
                ["buy", "Käufe"],
                ["sell", "Verkäufe"],
                ["ex_post", "Nachbereitungen"],
              ],
            ],
            [
              "status",
              "Status",
              [
                ["", "Alle Status"],
                ["open", "Offene Position"],
                ["closed", "Abgeschlossen"],
                ["draft", "Zuordnung offen"],
              ],
            ],
            [
              "source",
              "Quelle",
              [
                ["", "Alle Quellen"],
                ["broker", "Trade Republic"],
                ["unlinked", "Ohne Broker-Verknüpfung"],
              ],
            ],
            [
              "sort",
              "Sortierung",
              [
                ["newest", "Neueste zuerst"],
                ["oldest", "Älteste zuerst"],
              ],
            ],
          ] as [keyof typeof draft, string, string[][]][]
        ).map(([key, label, options]) => (
          <label className="block text-sm" key={key}>
            {label}
            <select
              className="input-dark mt-1"
              value={draft[key]}
              onChange={(event) => field(key, event.target.value)}
            >
              {options.map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
        ))}
        <div className="grid grid-cols-2 gap-3">
          {(
            [
              ["from", "Zeitraum von"],
              ["to", "Zeitraum bis"],
            ] as const
          ).map(([key, label]) => (
            <label className="min-w-0 text-sm" key={key}>
              {label}
              <input
                className="input-dark mt-1 min-w-0"
                type="date"
                value={draft[key]}
                onChange={(event) => field(key, event.target.value)}
              />
            </label>
          ))}
        </div>
        <div className="sticky bottom-0 flex flex-wrap justify-end gap-2 border-t bg-white py-3">
          <button
            type="button"
            className="rounded-lg border px-4"
            onClick={onClose}
          >
            Abbrechen
          </button>
          <button
            type="submit"
            className="rounded-lg bg-[#0f766e] px-4 text-white"
          >
            Filter anwenden
          </button>
        </div>
      </form>
    </dialog>
  );
}
