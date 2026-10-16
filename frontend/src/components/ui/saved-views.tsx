"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "next/navigation";
import { useState } from "react";
import { useBetaMode } from "@/components/beta-mode-provider";
import { api } from "@/lib/api/client";

export type SavedView = { id: string; name: string; scope: string; state: string; version: number; updated_at: string };
export function SavedViews({ scope }: { scope: string }) {
  const beta = useBetaMode();
  const params = useSearchParams();
  const [name, setName] = useState("");
  const client = useQueryClient();
  const query = useQuery({ queryKey: ["saved-views"], queryFn: api.savedViews, enabled: !beta, staleTime: 60_000 });
  const save = useMutation({ mutationFn: () => {
    const state = new URLSearchParams();
    if (params.has(scope)) state.set(scope, params.get(scope)!);
    return api.saveView({ name: name.trim(), scope, state: state.toString(), version: 1 });
  }, onSuccess: result => { client.setQueryData(["saved-views"], result); setName(""); } });
  const remove = useMutation({ mutationFn: api.deleteView, onSuccess: result => client.setQueryData(["saved-views"], result) });
  if (beta) return null;
  const views = query.data?.items.filter(view => view.scope === scope) ?? [];
  let unsupported = false;
  try { const state = JSON.parse(params.get(scope) || "null"); unsupported = Boolean(state && state.version !== 1); } catch { unsupported = true; }
  return <details className="rounded-lg border border-[#e3e8ef] bg-white p-3 text-sm">
    <summary className="cursor-pointer font-semibold">Gespeicherte Ansichten · {views.length}{unsupported ? " · ungültiger Link" : ""}</summary>
    {unsupported && <p role="alert" className="app-notice">Ansichtsversion wird nicht unterstützt. Die Standardauswahl wird angezeigt.</p>}
    <form className="mt-3 flex flex-wrap gap-2" onSubmit={event => { event.preventDefault(); save.mutate(); }}>
      <label className="min-w-0 flex-1"><span className="sr-only">Name der Ansicht</span><input className="input-dark" placeholder="Aktuelle Auswahl benennen" maxLength={60} value={name} onChange={event => setName(event.target.value)} /></label>
      <button type="submit" className="app-button" disabled={!name.trim() || save.isPending || query.isError}>Ansicht speichern</button>
    </form>
    {(query.error || save.error || remove.error) && <p role="alert" className="mt-2 text-red-700">{(query.error || save.error || remove.error)?.message}</p>}
    <div className="mt-3 flex flex-wrap gap-2">{views.map(view => <span key={view.id} className="inline-flex items-center gap-2 rounded-lg border px-2 py-1"><button type="button" className="font-medium text-[#0f766e]" onClick={() => window.history.pushState(null, "", `${window.location.pathname}${view.state ? `?${view.state}` : ""}${window.location.hash}`)}>{view.name}</button><button type="button" aria-label={`Ansicht ${view.name} entfernen`} disabled={remove.isPending} onClick={() => remove.mutate(view.id)}>×</button></span>)}</div>
    <p className="mt-2 text-xs text-[#687386]">Private Filteransichten. Strategieeinstellungen und Bestände werden nicht verändert.</p>
  </details>;
}
