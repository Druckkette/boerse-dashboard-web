"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Database, KeyRound, LockKeyhole, RotateCw, Save, ShieldAlert, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";
import { StatusChip } from "@/components/ui/status-chip";
import { api } from "@/lib/api/client";
import type { RuntimeConfigItem } from "@/lib/types/api";

const categoryLabels: Record<RuntimeConfigItem["category"], string> = {
  external_api: "API & Datenquellen",
  notifications: "Benachrichtigungen",
  database: "Datenbank",
  security: "Security",
  deployment: "Deployment"
};

const categoryOrder: RuntimeConfigItem["category"][] = ["external_api", "notifications", "database", "security", "deployment"];

export function RuntimeConfigPanel() {
  const queryClient = useQueryClient();
  const query = useQuery({ queryKey: ["runtime-config"], queryFn: api.runtimeConfig, staleTime: 30_000 });
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [clearKeys, setClearKeys] = useState<string[]>([]);
  const mutation = useMutation({
    mutationFn: () => api.patchRuntimeConfig({ values: cleanDraft(draft), clear_keys: clearKeys }),
    onSuccess: (updated) => {
      queryClient.setQueryData(["runtime-config"], updated);
      queryClient.invalidateQueries({ queryKey: ["settings"] });
      setDraft({});
      setClearKeys([]);
    }
  });

  const grouped = useMemo(() => {
    const groups = new Map<RuntimeConfigItem["category"], RuntimeConfigItem[]>();
    for (const item of query.data?.items ?? []) {
      groups.set(item.category, [...(groups.get(item.category) ?? []), item]);
    }
    return categoryOrder
      .map((category) => ({ category, items: groups.get(category) ?? [] }))
      .filter((group) => group.items.length > 0);
  }, [query.data?.items]);
  const pendingCount = Object.keys(cleanDraft(draft)).length + clearKeys.length;

  function setValue(key: string, value: string) {
    setDraft((current) => ({ ...current, [key]: value }));
    setClearKeys((current) => current.filter((item) => item !== key));
  }

  function toggleClear(key: string) {
    setDraft((current) => {
      const next = { ...current };
      delete next[key];
      return next;
    });
    setClearKeys((current) => (current.includes(key) ? current.filter((item) => item !== key) : [...current, key]));
  }

  return (
    <section className="rounded border border-[#2d333d] bg-[#171a20] p-5">
      <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
        <div>
          <div className="mb-2 flex items-center gap-2 text-sm text-emerald-200">
            <KeyRound size={18} />
            Konfiguration & Secrets
          </div>
          <h2 className="text-lg font-semibold">API-Zugänge im Setup pflegen</h2>
          <p className="mt-2 max-w-4xl text-sm leading-6 text-[#a0a7b4]">
            Runtime-Werte werden in Postgres gespeichert und von Backend/Worker gelesen. Bestehende Werte werden nicht im Klartext angezeigt.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <StatusChip tone={pendingCount ? "warning" : "good"}>{pendingCount ? `${pendingCount} Änderung(en)` : "aktuell"}</StatusChip>
          <button
            className="inline-flex items-center gap-2 rounded border border-[#2d333d] bg-[#111419] px-3 py-2 text-sm transition hover:border-emerald-300/60"
            type="button"
            onClick={() => query.refetch()}
          >
            <RotateCw size={15} className={query.isFetching ? "animate-spin text-emerald-300" : "text-[#a0a7b4]"} />
            Status
          </button>
          <button
            className="inline-flex items-center gap-2 rounded border border-emerald-300/40 bg-emerald-300/10 px-3 py-2 text-sm text-emerald-100 transition hover:border-emerald-200 disabled:cursor-not-allowed disabled:opacity-50"
            disabled={pendingCount === 0 || mutation.isPending}
            type="button"
            onClick={() => mutation.mutate()}
          >
            <Save size={15} />
            {mutation.isPending ? "Speichert" : "Speichern"}
          </button>
        </div>
      </div>

      {query.data?.note && (
        <div className="mt-4 rounded border border-sky-300/25 bg-sky-300/10 p-3 text-sm leading-6 text-sky-100">
          {query.data.note}
        </div>
      )}
      {query.error && (
        <div className="mt-4 rounded border border-rose-300/30 bg-rose-300/10 p-3 text-sm text-rose-100">
          {query.error instanceof Error ? query.error.message : "Runtime-Konfiguration konnte nicht geladen werden."}
        </div>
      )}
      {mutation.error && (
        <div className="mt-4 rounded border border-rose-300/30 bg-rose-300/10 p-3 text-sm text-rose-100">
          {mutation.error instanceof Error ? mutation.error.message : "Runtime-Konfiguration konnte nicht gespeichert werden."}
        </div>
      )}

      <div className="mt-5 space-y-4">
        {grouped.map((group) => (
          <div key={group.category} className="rounded border border-[#242a33] bg-[#111419] p-4">
            <div className="mb-3 flex items-center gap-2">
              {iconForCategory(group.category)}
              <h3 className="text-base font-semibold">{categoryLabels[group.category]}</h3>
            </div>
            <div className="grid gap-3 xl:grid-cols-2">
              {group.items.map((item) => (
                <RuntimeConfigField
                  clearSelected={clearKeys.includes(item.key)}
                  draftValue={draft[item.key] ?? ""}
                  item={item}
                  key={item.key}
                  onClear={() => toggleClear(item.key)}
                  onChange={(value) => setValue(item.key, value)}
                />
              ))}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function RuntimeConfigField({
  clearSelected,
  draftValue,
  item,
  onChange,
  onClear
}: {
  clearSelected: boolean;
  draftValue: string;
  item: RuntimeConfigItem;
  onChange: (value: string) => void;
  onClear: () => void;
}) {
  return (
    <div className="rounded border border-[#2d333d] bg-[#171a20] p-4">
      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <div className="font-medium">{item.label}</div>
            <StatusChip tone={item.configured ? "good" : item.editable ? "warning" : "neutral"}>
              {item.configured ? sourceLabel(item.source) : "fehlt"}
            </StatusChip>
            {item.runtime_applied ? <StatusChip tone="good">Runtime</StatusChip> : <StatusChip tone="neutral">Bootstrap</StatusChip>}
          </div>
          <p className="mt-1 text-xs leading-5 text-[#8e97a6]">{item.description}</p>
          {item.value_preview ? <div className="mt-2 text-xs tabular-nums text-[#77808f]">Aktuell: {item.value_preview}</div> : null}
          {item.restart_required ? (
            <div className="mt-2 flex gap-2 text-xs leading-5 text-amber-100">
              <ShieldAlert className="mt-0.5 size-3.5 shrink-0" />
              Änderung braucht `.env.nas`/Compose und Container-Neustart.
            </div>
          ) : null}
        </div>
        {item.configured && item.editable ? (
          <button
            className={[
              "inline-flex items-center justify-center gap-2 rounded border px-2.5 py-1.5 text-xs transition",
              clearSelected
                ? "border-rose-300/50 bg-rose-300/10 text-rose-100"
                : "border-[#2d333d] bg-[#111419] text-[#a0a7b4] hover:border-rose-300/50 hover:text-rose-100"
            ].join(" ")}
            type="button"
            onClick={onClear}
          >
            <Trash2 size={13} />
            {clearSelected ? "Wird gelöscht" : "Löschen"}
          </button>
        ) : null}
      </div>

      {item.editable ? (
        <div className="mt-3">
          <input
            className="input-dark"
            placeholder={item.placeholder || item.label}
            type={item.secret ? "password" : "text"}
            value={draftValue}
            onChange={(event) => onChange(event.target.value)}
          />
          <div className="mt-2 flex items-center gap-2 text-xs text-[#77808f]">
            <CheckCircle2 size={13} className="text-emerald-300" />
            Neuer Wert wird erst beim Speichern ersetzt.
          </div>
        </div>
      ) : (
        <div className="mt-3 rounded border border-dashed border-[#2d333d] bg-[#111419] p-3 text-sm leading-6 text-[#a0a7b4]">
          Dieser Wert kann nicht aus der laufenden App heraus gesetzt werden, weil er vor Start von Backend/Frontend/Worker benötigt wird.
        </div>
      )}
    </div>
  );
}

function cleanDraft(draft: Record<string, string>) {
  return Object.fromEntries(Object.entries(draft).filter(([, value]) => value.trim().length > 0));
}

function sourceLabel(source: RuntimeConfigItem["source"]) {
  if (source === "database") return "Web";
  if (source === "environment") return "ENV";
  if (source === "bootstrap_only") return "Bootstrap";
  return "fehlt";
}

function iconForCategory(category: RuntimeConfigItem["category"]) {
  if (category === "database") return <Database className="text-sky-200" size={18} />;
  if (category === "security") return <LockKeyhole className="text-amber-200" size={18} />;
  return <KeyRound className="text-emerald-300" size={18} />;
}
