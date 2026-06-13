"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Database, KeyRound, LockKeyhole, RotateCw, Save, ShieldAlert, TestTube2, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";
import { StatusChip } from "@/components/ui/status-chip";
import { api } from "@/lib/api/client";
import type { DatabaseTarget, DatabaseTargetResponse, RuntimeConfigItem, RuntimeConfigTestResponse } from "@/lib/types/api";

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
  const databaseTargetQuery = useQuery({ queryKey: ["database-target"], queryFn: api.databaseTarget, staleTime: 15_000 });
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [clearKeys, setClearKeys] = useState<string[]>([]);
  const [testResults, setTestResults] = useState<Record<string, RuntimeConfigTestResponse>>({});
  const mutation = useMutation({
    mutationFn: () => api.patchRuntimeConfig({ values: cleanDraft(draft), clear_keys: clearKeys }),
    onSuccess: (updated) => {
      queryClient.setQueryData(["runtime-config"], updated);
      queryClient.invalidateQueries({ queryKey: ["settings"] });
      setDraft({});
      setClearKeys([]);
    }
  });
  const testMutation = useMutation({
    mutationFn: ({ key, value }: { key: string; value?: string }) => api.testRuntimeConfig({ key, value }),
    onSuccess: (result) => setTestResults((current) => ({ ...current, [result.key]: result }))
  });
  const switchDatabaseMutation = useMutation({
    mutationFn: (target: DatabaseTarget) => api.switchDatabaseTarget({ target }),
    onSuccess: (updated) => {
      queryClient.setQueryData(["database-target"], updated);
      queryClient.invalidateQueries({ queryKey: ["runtime-config"] });
    }
  });
  const restartServicesMutation = useMutation({
    mutationFn: api.restartRuntimeServices,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["database-target"] })
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
      <DatabaseTargetControls
        data={databaseTargetQuery.data}
        isFetching={databaseTargetQuery.isFetching}
        restartError={
          restartServicesMutation.error instanceof Error ? restartServicesMutation.error.message : ""
        }
        restartPending={restartServicesMutation.isPending}
        restartResult={restartServicesMutation.data}
        switchError={
          switchDatabaseMutation.error instanceof Error ? switchDatabaseMutation.error.message : ""
        }
        switchPending={switchDatabaseMutation.isPending ? switchDatabaseMutation.variables : null}
        onRefresh={() => databaseTargetQuery.refetch()}
        onRestart={() => restartServicesMutation.mutate()}
        onSwitch={(target) => switchDatabaseMutation.mutate(target)}
      />

      <div className="mt-5 space-y-4">
        {grouped.map((group) => (
          <RuntimeConfigGroup
            category={group.category}
            clearKeys={clearKeys}
            draft={draft}
            items={group.items}
            key={group.category}
            onClear={toggleClear}
            onChange={setValue}
            onTest={(key) => testMutation.mutate({ key, value: draft[key] })}
            testPendingKey={testMutation.isPending ? testMutation.variables?.key : undefined}
            testResults={testResults}
          />
        ))}
      </div>
    </section>
  );
}

function RuntimeConfigGroup({
  category,
  clearKeys,
  draft,
  items,
  onChange,
  onClear,
  onTest,
  testPendingKey,
  testResults
}: {
  category: RuntimeConfigItem["category"];
  clearKeys: string[];
  draft: Record<string, string>;
  items: RuntimeConfigItem[];
  onChange: (key: string, value: string) => void;
  onClear: (key: string) => void;
  onTest: (key: string) => void;
  testPendingKey?: string;
  testResults: Record<string, RuntimeConfigTestResponse>;
}) {
  const [open, setOpen] = useState(category !== "security");
  return (
    <details
      className="group rounded border border-[#242a33] bg-[#111419] p-4"
      open={open}
      onToggle={(event) => setOpen(event.currentTarget.open)}
    >
      <summary className="flex cursor-pointer list-none items-center justify-between gap-3">
        <span className="flex items-center gap-2">
          {iconForCategory(category)}
          <span className="text-base font-semibold">{categoryLabels[category]}</span>
          <StatusChip tone="neutral">{items.length}</StatusChip>
        </span>
        <span className="text-xs text-[#77808f] group-open:hidden">aufklappen</span>
        <span className="hidden text-xs text-[#77808f] group-open:inline">einklappen</span>
      </summary>
      <div className="mt-3 grid gap-3 xl:grid-cols-2">
        {items.map((item) => (
          <RuntimeConfigField
            clearSelected={clearKeys.includes(item.key)}
            draftValue={draft[item.key] ?? ""}
            item={item}
            key={item.key}
            onClear={() => onClear(item.key)}
            onChange={(value) => onChange(item.key, value)}
            onTest={() => onTest(item.key)}
            testPending={testPendingKey === item.key}
            testResult={testResults[item.key]}
          />
        ))}
      </div>
    </details>
  );
}

function DatabaseTargetControls({
  data,
  isFetching,
  onRefresh,
  onRestart,
  onSwitch,
  restartError,
  restartPending,
  restartResult,
  switchError,
  switchPending
}: {
  data?: DatabaseTargetResponse;
  isFetching: boolean;
  onRefresh: () => void;
  onRestart: () => void;
  onSwitch: (target: DatabaseTarget) => void;
  restartError: string;
  restartPending: boolean;
  restartResult?: { ok: boolean; status: string; detail: string; services: string[] };
  switchError: string;
  switchPending: DatabaseTarget | null;
}) {
  return (
    <div className="mt-5 rounded border border-[#242a33] bg-[#111419] p-4">
      <div className="flex flex-col gap-3 xl:flex-row xl:items-start xl:justify-between">
        <div>
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <Database className="text-sky-200" size={18} />
            <h3 className="text-base font-semibold">Datenbank-Ziel</h3>
            <StatusChip tone={data?.target === "neon" ? "warning" : "good"}>
              Ziel: {data?.target === "neon" ? "Neon" : "lokal"}
            </StatusChip>
            <StatusChip tone={data?.running_target === "neon" ? "warning" : "good"}>
              Läuft: {data?.running_target === "neon" ? "Neon" : "lokal"}
            </StatusChip>
            {data?.restart_required ? <StatusChip tone="warning">Neustart nötig</StatusChip> : <StatusChip tone="good">aktiv</StatusChip>}
          </div>
          <p className="max-w-4xl text-sm leading-6 text-[#a0a7b4]">
            Die Neon-Adresse kann gespeichert und getestet werden, ohne die laufende App umzuschalten.
            Der Wechsel passiert erst über diese Buttons und wird nach dem Neustart der betroffenen Dienste aktiv.
          </p>
          <div className="mt-3 grid gap-2 text-xs text-[#77808f] md:grid-cols-3">
            <span>Aktiv: {data?.active_value_preview || "n/a"}</span>
            <span>Lokal: {data?.local_value_preview || "aus ENV/Default"}</span>
            <span>Neon: {data?.neon_configured ? data.neon_value_preview : "nicht gespeichert"}</span>
          </div>
          {data?.message ? <div className="mt-3 text-sm text-amber-100">{data.message}</div> : null}
        </div>
        <div className="flex flex-col gap-2 sm:flex-row xl:flex-col">
          <button
            className="inline-flex items-center justify-center gap-2 rounded border border-[#2d333d] bg-[#171a20] px-3 py-2 text-sm transition hover:border-emerald-300/60 disabled:cursor-not-allowed disabled:opacity-50"
            disabled={switchPending !== null || data?.target === "local"}
            type="button"
            onClick={() => onSwitch("local")}
          >
            Lokale Postgres verwenden
          </button>
          <button
            className="inline-flex items-center justify-center gap-2 rounded border border-sky-300/35 bg-sky-300/10 px-3 py-2 text-sm text-sky-100 transition hover:border-sky-200 disabled:cursor-not-allowed disabled:opacity-50"
            disabled={switchPending !== null || data?.target === "neon" || !data?.neon_configured}
            type="button"
            onClick={() => onSwitch("neon")}
          >
            Neon verwenden
          </button>
          <button
            className="inline-flex items-center justify-center gap-2 rounded border border-amber-300/35 bg-amber-300/10 px-3 py-2 text-sm text-amber-100 transition hover:border-amber-200 disabled:cursor-not-allowed disabled:opacity-50"
            disabled={restartPending}
            type="button"
            onClick={onRestart}
          >
            <RotateCw size={15} className={restartPending || isFetching ? "animate-spin" : ""} />
            Dienste neu starten
          </button>
          <button
            className="inline-flex items-center justify-center gap-2 rounded border border-[#2d333d] bg-[#171a20] px-3 py-2 text-sm transition hover:border-emerald-300/60"
            type="button"
            onClick={onRefresh}
          >
            Status prüfen
          </button>
        </div>
      </div>
      {switchError ? (
        <div className="mt-3 rounded border border-rose-300/30 bg-rose-300/10 p-3 text-sm text-rose-100">{switchError}</div>
      ) : null}
      {restartError ? (
        <div className="mt-3 rounded border border-rose-300/30 bg-rose-300/10 p-3 text-sm text-rose-100">{restartError}</div>
      ) : null}
      {restartResult ? (
        <div className={["mt-3 rounded border p-3 text-sm leading-6", restartResult.ok ? "border-emerald-300/25 bg-emerald-300/10 text-emerald-100" : "border-amber-300/30 bg-amber-300/10 text-amber-100"].join(" ")}>
          {restartResult.detail}
        </div>
      ) : null}
    </div>
  );
}

function RuntimeConfigField({
  clearSelected,
  draftValue,
  item,
  onChange,
  onClear,
  onTest,
  testPending,
  testResult
}: {
  clearSelected: boolean;
  draftValue: string;
  item: RuntimeConfigItem;
  onChange: (value: string) => void;
  onClear: () => void;
  onTest: () => void;
  testPending: boolean;
  testResult?: RuntimeConfigTestResponse;
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
              Änderung wird gespeichert, greift aber erst nach Container-Neustart.
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
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <button
              className="inline-flex items-center gap-2 rounded border border-sky-300/35 bg-sky-300/10 px-3 py-2 text-xs text-sky-100 transition hover:border-sky-200 disabled:cursor-not-allowed disabled:opacity-50"
              disabled={testPending}
              type="button"
              onClick={onTest}
            >
              <TestTube2 size={13} />
              {testPending ? "Prüft" : item.key === "NEON_DATABASE_URL" ? "Neon testen" : "Testen"}
            </button>
            {testResult ? (
              <StatusChip tone={testResult.ok ? "good" : "bad"}>{testResult.status}</StatusChip>
            ) : null}
          </div>
          {testResult ? (
            <div className={["mt-2 rounded border p-3 text-xs leading-5", testResult.ok ? "border-emerald-300/25 bg-emerald-300/10 text-emerald-100" : "border-rose-300/30 bg-rose-300/10 text-rose-100"].join(" ")}>
              {testResult.detail}
            </div>
          ) : null}
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
