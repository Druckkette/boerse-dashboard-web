"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api/client";
import type { SellManualInput } from "@/lib/types/api";
import { SellRuleSetupEditor } from "./sell-rule-setup-editor";

export function SellSetupPanel({ ticker, onDirtyChange }: { ticker: string; onDirtyChange?: (dirty: boolean) => void }) {
  const queryClient = useQueryClient();
  const manual = useQuery({ queryKey: ["sell-manual", ticker], queryFn: () => api.sellManual(ticker) });
  const [draft, setDraft] = useState<SellManualInput | null>(null);
  const current = draft ?? manual.data;
  const dirty = draft !== null && JSON.stringify(draft) !== JSON.stringify(manual.data);
  const save = useMutation({
    mutationFn: (next: SellManualInput) => api.patchSellManual(ticker, next),
    onSuccess: (updated) => {
      queryClient.setQueryData(["sell-manual", ticker], updated);
      for (const key of ["sell-evaluation", "sell-metrics", "sell-ranking", "portfolio-snapshot"]) {
        queryClient.invalidateQueries({ queryKey: [key] });
      }
      setDraft(null);
    },
  });
  useEffect(() => {
    onDirtyChange?.(dirty);
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty, onDirtyChange]);
  if (manual.isLoading) return <p role="status">Verkaufsregeln werden geladen …</p>;
  if (!current || manual.isError) return <p role="alert">Verkaufsregeln konnten nicht geladen werden.</p>;
  const useGlobal = current.use_global_sell_setup !== false;
  function update(patch: Partial<SellManualInput>) {
    if (!current) return;
    setDraft({ ...current, ...patch });
    save.reset();
  }
  return <section className="rounded-[14px] border border-[#e3e8ef] bg-white p-5 text-[#172033]" aria-label={`Verkaufsregeln ${ticker}`}>
    <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
      <div>
        <h2 className="text-base font-semibold">Verkaufsregeln · {ticker}</h2>
        <p className="mt-1 text-sm text-[#687386]">{useGlobal ? "Verwendet die in Settings gespeicherte globale Strategie und alle globalen Grenzwerte." : "Änderungen an Strategie und Grenzwerten hier gelten nur für diese Aktie. Der globale Standard bleibt unverändert."}</p>
      </div>
      <div className="flex gap-2">
        <button type="button" disabled={!dirty || save.isPending} className="rounded border border-[#d8e1ea] px-3 py-2 text-sm disabled:opacity-50" onClick={() => { setDraft(null); save.reset(); }}>Verwerfen</button>
        <button type="button" disabled={!dirty || save.isPending} className="rounded bg-[#0f766e] px-3 py-2 text-sm font-semibold text-white disabled:opacity-50" onClick={() => save.mutate(current)}>{save.isPending ? "Speichert …" : dirty ? "Aktienregeln speichern" : "Gespeichert"}</button>
      </div>
    </div>
    <label className="mb-4 flex items-center gap-3 text-sm">
      <input type="checkbox" className="size-4 accent-[#0f766e]" checked={useGlobal} disabled={save.isPending} onChange={(event) => update({ use_global_sell_setup: event.target.checked })} />
      Globale Verkaufsstrategie übernehmen
    </label>
    {useGlobal && <p className="mb-4 text-sm text-[#687386]">Für eigene Regeln den Haken entfernen. Zum Ändern des Standards: <Link href="/settings#sell-strategy" className="underline">Globale Verkaufsstrategie öffnen</Link>.</p>}
    <fieldset disabled={useGlobal || save.isPending} className={useGlobal ? "opacity-70" : ""}>
      <SellRuleSetupEditor setup={current.sell_setup} onChange={(next) => update({ sell_setup: next, use_global_sell_setup: false })} />
    </fieldset>
    {save.isError && <p role="alert" className="mt-4 text-sm text-rose-700">{save.error.message}</p>}
  </section>;
}

export function PositionSellSettings({ globalDraftDirty, onDirtyChange }: { globalDraftDirty: boolean; onDirtyChange?: (dirty: boolean) => void }) {
  const positions = useQuery({ queryKey: ["portfolio-positions"], queryFn: api.portfolioPositions });
  const [ticker, setTicker] = useState("");
  const [stockDirty, setStockDirty] = useState(false);
  const handleDirty = useCallback((dirty: boolean) => { setStockDirty(dirty); onDirtyChange?.(dirty); }, [onDirtyChange]);
  return <section className="space-y-3 rounded-[14px] border border-[#e3e8ef] bg-white p-5">
    <h2 className="text-base font-semibold">Verkaufsstrategie pro Aktie</h2>
    <p className="text-sm text-[#687386]">Wähle eine Depotaktie, um den globalen Standard zu übernehmen oder eigene Regeln festzulegen. Bestehende individuelle Setups werden durch eine Änderung des Standards nicht überschrieben.</p>
    {globalDraftDirty && <p className="text-sm text-amber-800">Die globale Strategie hat ungespeicherte Änderungen. Die Aktienansicht verwendet den zuletzt gespeicherten Standard.</p>}
    <label className="block text-sm">Aktie auswählen
      <select className="mt-1 w-full rounded border border-[#d8e1ea] bg-white px-3 py-2" value={ticker} disabled={stockDirty || positions.isLoading} onChange={(event) => setTicker(event.target.value)}>
        <option value="">Depotaktie auswählen …</option>
        {positions.data?.map((position) => <option key={position.ticker} value={position.ticker}>{position.ticker} · {position.name}</option>)}
      </select>
    </label>
    {positions.isError && <p role="alert" className="text-sm text-rose-700">Depotaktien konnten nicht geladen werden.</p>}
    {stockDirty && <p className="text-sm text-[#687386]">Aktienregeln speichern oder verwerfen, bevor du die Aktie wechselst.</p>}
    {ticker && <SellSetupPanel key={ticker} ticker={ticker} onDirtyChange={handleDirty} />}
  </section>;
}
