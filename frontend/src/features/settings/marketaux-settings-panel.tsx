"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { KeyRound } from "lucide-react";
import { api } from "@/lib/api/client";
import { useUiDraft } from "@/components/ui/ui-mode-provider";

const KEY = "MARKETAUX_API_KEY";

export function MarketauxSettingsPanel() {
  const client = useQueryClient();
  const [draft, setDraft] = useState("");
  const query = useQuery({ queryKey: ["runtime-config"], queryFn: api.runtimeConfig });
  const item = query.data?.items.find(item => item.key === KEY);
  const mutation = useMutation({
    mutationFn: (remove: boolean) => api.patchRuntimeConfig(remove
      ? { values: {}, clear_keys: [KEY] }
      : { values: { [KEY]: draft.trim() }, clear_keys: [] }),
    onSuccess: async response => {
      setDraft("");
      client.setQueryData(["runtime-config"], response);
      await client.invalidateQueries({ queryKey: ["stock-news"] });
    },
  });
  useUiDraft(Boolean(draft));

  return <section className="dashboard-section" aria-label="Marketaux Nachrichten-Zugang">
    <h2 className="flex items-center gap-2 text-base font-semibold"><KeyRound size={18} aria-hidden="true" />Aktiennachrichten · Marketaux</h2>
    <p className="mt-2 text-sm text-[#687386]">Hinterlege den API-Schlüssel für die Unternehmensnachrichten. Er wird im Backend gespeichert und nach dem Speichern nicht wieder angezeigt.</p>
    {query.isLoading ? <p role="status" className="mt-3 text-sm">Nachrichten-Zugang wird geladen…</p> : null}
    {query.isError ? <p role="alert" className="mt-3 text-sm text-[#c2413b]">Der gespeicherte Status ist derzeit nicht erreichbar.</p> : null}
    <form className="mt-4 space-y-3" onSubmit={event => { event.preventDefault(); if (draft.trim() && item?.editable) mutation.mutate(false); }}>
      <label className="block text-sm font-medium">Marketaux API-Schlüssel
        <input type="password" autoComplete="new-password" spellCheck={false} maxLength={256}
          aria-describedby="marketaux-key-status" className="input-dark mt-1 w-full"
          value={draft} disabled={!item?.editable || mutation.isPending}
          placeholder={item?.configured ? "Schlüssel bereits hinterlegt · neuen Schlüssel eingeben" : "Marketaux API-Schlüssel eingeben"}
          onChange={event => { setDraft(event.target.value); mutation.reset(); }} />
      </label>
      <p id="marketaux-key-status" className="text-xs text-[#687386]">{item ? item.configured ? "Ein Schlüssel ist hinterlegt. " : "Noch kein Schlüssel hinterlegt. " : "Der gespeicherte Status wird geprüft. "}Änderungen gelten beim nächsten Nachrichtenabruf; ein Neustart ist nicht erforderlich.</p>
      <div className="flex flex-wrap gap-2">
        <button className="app-button" type="submit" disabled={!draft.trim() || !item?.editable || mutation.isPending}>{mutation.isPending ? "Speichert…" : "Nachrichten-Schlüssel speichern"}</button>
        {item?.source === "database" ? <button className="app-button" type="button" disabled={mutation.isPending} onClick={() => mutation.mutate(true)}>Gespeicherten Schlüssel entfernen</button> : null}
      </div>
      {mutation.isSuccess ? <p role="status" className="text-sm text-[#0f766e]">Nachrichten-Zugang gespeichert.</p> : null}
      {mutation.isError ? <p role="alert" className="text-sm text-[#c2413b]">Der Nachrichten-Zugang konnte nicht gespeichert werden. Bitte erneut versuchen.</p> : null}
    </form>
  </section>;
}
