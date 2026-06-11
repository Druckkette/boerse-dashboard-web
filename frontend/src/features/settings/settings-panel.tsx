"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Minus, Plus, SlidersHorizontal } from "lucide-react";
import { useEffect, useState } from "react";
import { StatusChip } from "@/components/ui/status-chip";
import { api } from "@/lib/api/client";
import type { AppSettings } from "@/lib/types/api";

const fallbackSettings: AppSettings = {
  atr_threshold: 1.5,
  position_monitor_enabled: false,
  position_monitor_interval_minutes: 5,
  position_monitor_threshold_atr: 1.5,
  position_monitor_atr_period: 21,
  position_monitor_lookback_days: 120,
  position_monitor_cooldown_hours: 12,
  position_monitor_reference: "high_since_buy",
  pushover_enabled: false,
  pushover_configured: false,
  rs_rating_source: "computed",
  data_jobs_enabled: true
};

export function SettingsPanel() {
  const queryClient = useQueryClient();
  const { data } = useQuery({ queryKey: ["settings"], queryFn: api.settings });
  const [local, setLocal] = useState<AppSettings | null>(null);
  const [dirty, setDirty] = useState(false);
  const settings = local ?? data ?? fallbackSettings;

  const mutation = useMutation({
    mutationFn: api.patchSettings,
    onSuccess: (updated) => {
      queryClient.setQueryData(["settings"], updated);
      setLocal(null);
      setDirty(false);
    }
  });

  useEffect(() => {
    if (!dirty) return;
    const handle = window.setTimeout(() => {
      mutation.mutate(settings);
    }, 550);
    return () => window.clearTimeout(handle);
  }, [dirty, mutation, settings]);

  function update<K extends keyof AppSettings>(key: K, value: AppSettings[K]) {
    setLocal((current) => ({ ...(current ?? data ?? fallbackSettings), [key]: value }));
    setDirty(true);
  }

  function updateNumber(key: keyof AppSettings, value: number, min: number, max: number, step = 0.1) {
    const rounded = Math.round(value / step) * step;
    update(key, Math.max(min, Math.min(max, Number(rounded.toFixed(4)))) as never);
  }

  return (
    <div className="space-y-5">
      <section className="rounded border border-[#2d333d] bg-[#171a20] p-5">
        <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
          <div>
            <h1 className="text-2xl font-semibold">Settings</h1>
            <p className="mt-1 max-w-3xl text-sm leading-6 text-[#a0a7b4]">
              Änderungen wirken lokal sofort und werden debounced in Postgres gespeichert.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <StatusChip tone={mutation.isPending ? "warning" : dirty ? "neutral" : "good"}>
              {mutation.isPending ? "speichert" : dirty ? "lokal geändert" : "persistiert"}
            </StatusChip>
            <SlidersHorizontal className="text-emerald-300" size={22} />
          </div>
        </div>
      </section>

      <div className="grid gap-4 xl:grid-cols-[1fr_380px]">
        <section className="space-y-4">
          <SettingCard
            description="Schneller UI-Regler für ATR-/Stop-Schwellen ohne globalen Reload."
            title="ATR-Schwellenwert"
            value={settings.atr_threshold.toFixed(1)}
          >
            <Stepper
              max={5}
              min={0.5}
              step={0.1}
              value={settings.atr_threshold}
              onChange={(value) => updateNumber("atr_threshold", value, 0.5, 5)}
            />
          </SettingCard>

          <SettingCard
            description="Positionsmonitor läuft im Worker/Scheduler und nutzt gespeicherte Parameter."
            title="Positionsmonitor"
            value={settings.position_monitor_enabled ? "aktiv" : "aus"}
          >
            <div className="grid gap-3 md:grid-cols-2">
              <label className="flex items-center justify-between gap-3 rounded border border-[#2d333d] bg-[#111419] px-3 py-2 text-sm">
                <span>Monitor aktiv</span>
                <input
                  checked={settings.position_monitor_enabled}
                  className="size-4 accent-emerald-300"
                  type="checkbox"
                  onChange={(event) => update("position_monitor_enabled", event.target.checked)}
                />
              </label>
              <Field label="Referenz">
                <select
                  className="input-dark"
                  value={settings.position_monitor_reference}
                  onChange={(event) =>
                    update(
                      "position_monitor_reference",
                      event.target.value as AppSettings["position_monitor_reference"]
                    )
                  }
                >
                  <option value="high_since_buy">High seit Kauf</option>
                  <option value="close_since_buy">Close seit Kauf</option>
                  <option value="entry_price">Einstand</option>
                </select>
              </Field>
              <NumberField
                label="Intervall Minuten"
                max={240}
                min={1}
                step={1}
                value={settings.position_monitor_interval_minutes}
                onChange={(value) => updateNumber("position_monitor_interval_minutes", value, 1, 240, 1)}
              />
              <NumberField
                label="ATR Schwelle"
                max={10}
                min={0.5}
                step={0.1}
                value={settings.position_monitor_threshold_atr}
                onChange={(value) => updateNumber("position_monitor_threshold_atr", value, 0.5, 10)}
              />
              <NumberField
                label="ATR Periode"
                max={63}
                min={5}
                step={1}
                value={settings.position_monitor_atr_period}
                onChange={(value) => updateNumber("position_monitor_atr_period", value, 5, 63, 1)}
              />
              <NumberField
                label="Lookback Tage"
                max={740}
                min={30}
                step={5}
                value={settings.position_monitor_lookback_days}
                onChange={(value) => updateNumber("position_monitor_lookback_days", value, 30, 740, 5)}
              />
              <NumberField
                label="Cooldown Stunden"
                max={168}
                min={1}
                step={1}
                value={settings.position_monitor_cooldown_hours}
                onChange={(value) => updateNumber("position_monitor_cooldown_hours", value, 1, 168, 1)}
              />
            </div>
          </SettingCard>

          <SettingCard description="Worker dürfen schwere Datenjobs starten; UI-Clicks bleiben davon getrennt." title="Datenjobs" value={settings.data_jobs_enabled ? "aktiv" : "aus"}>
            <div className="grid gap-3 md:grid-cols-2">
              <label className="flex items-center justify-between gap-3 rounded border border-[#2d333d] bg-[#111419] px-3 py-2 text-sm">
                <span>Datenjobs aktiv</span>
                <input
                  checked={settings.data_jobs_enabled}
                  className="size-4 accent-emerald-300"
                  type="checkbox"
                  onChange={(event) => update("data_jobs_enabled", event.target.checked)}
                />
              </label>
              <Field label="RS Quelle">
                <select
                  className="input-dark"
                  value={settings.rs_rating_source}
                  onChange={(event) => update("rs_rating_source", event.target.value as AppSettings["rs_rating_source"])}
                >
                  <option value="computed">Computed aus Price Cache</option>
                  <option value="csv_latest">CSV Latest</option>
                </select>
              </Field>
            </div>
          </SettingCard>
        </section>

        <aside className="rounded border border-[#2d333d] bg-[#171a20] p-5">
          <h2 className="text-base font-semibold">Runtime Status</h2>
          <div className="mt-4 space-y-3 text-sm">
            <InfoRow label="Monitor" value={settings.position_monitor_enabled ? "aktiv" : "aus"} tone={settings.position_monitor_enabled ? "good" : "neutral"} />
            <InfoRow label="Intervall" value={`${settings.position_monitor_interval_minutes} min`} />
            <InfoRow label="ATR Schwelle" value={`${settings.position_monitor_threshold_atr.toFixed(1)} ATR`} />
            <InfoRow label="RS Quelle" value={settings.rs_rating_source} />
            <InfoRow label="Pushover" value={settings.pushover_configured ? "konfiguriert" : "nicht konfiguriert"} tone={settings.pushover_configured ? "good" : "neutral"} />
          </div>
        </aside>
      </div>
    </div>
  );
}

function SettingCard({
  title,
  description,
  value,
  children
}: {
  title: string;
  description: string;
  value: string;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded border border-[#2d333d] bg-[#171a20] p-5">
      <div className="mb-4 flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
        <div>
          <h2 className="text-base font-semibold">{title}</h2>
          <p className="mt-1 text-sm text-[#a0a7b4]">{description}</p>
        </div>
        <StatusChip tone="neutral">{value}</StatusChip>
      </div>
      {children}
    </div>
  );
}

function Stepper({
  value,
  min,
  max,
  step,
  onChange
}: {
  value: number;
  min: number;
  max: number;
  step: number;
  onChange: (value: number) => void;
}) {
  return (
    <div className="flex items-center gap-3">
      <button
        aria-label="Wert senken"
        className="flex size-10 items-center justify-center rounded border border-[#2d333d] bg-[#111419] transition hover:border-emerald-300/60"
        type="button"
        onClick={() => onChange(value - step)}
      >
        <Minus size={17} />
      </button>
      <input
        className="w-full accent-emerald-300"
        max={max}
        min={min}
        step={step}
        type="range"
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
        onInput={(event) => onChange(Number(event.currentTarget.value))}
      />
      <div className="w-16 rounded border border-[#2d333d] bg-[#111419] px-3 py-2 text-right tabular-nums">
        {value.toFixed(1)}
      </div>
      <button
        aria-label="Wert erhöhen"
        className="flex size-10 items-center justify-center rounded border border-[#2d333d] bg-[#111419] transition hover:border-emerald-300/60"
        type="button"
        onClick={() => onChange(value + step)}
      >
        <Plus size={17} />
      </button>
    </div>
  );
}

function NumberField({
  label,
  value,
  min,
  max,
  step,
  onChange
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  onChange: (value: number) => void;
}) {
  return (
    <Field label={label}>
      <input
        className="input-dark"
        max={max}
        min={min}
        step={step}
        type="number"
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
      />
    </Field>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block text-sm">
      <span className="mb-1 block text-[#a0a7b4]">{label}</span>
      {children}
    </label>
  );
}

function InfoRow({
  label,
  value,
  tone = "neutral"
}: {
  label: string;
  value: string;
  tone?: "good" | "neutral" | "warning" | "bad";
}) {
  return (
    <div className="flex items-center justify-between gap-3 border-b border-[#242a33] pb-3 last:border-b-0">
      <span className="text-[#a0a7b4]">{label}</span>
      <StatusChip tone={tone}>{value}</StatusChip>
    </div>
  );
}
