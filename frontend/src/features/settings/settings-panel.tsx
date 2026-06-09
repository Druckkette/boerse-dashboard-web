"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Minus, Plus, SlidersHorizontal } from "lucide-react";
import { useEffect, useState } from "react";
import { StatusChip } from "@/components/ui/status-chip";
import { api } from "@/lib/api/client";

export function SettingsPanel() {
  const queryClient = useQueryClient();
  const { data } = useQuery({ queryKey: ["settings"], queryFn: api.settings });
  const [localAtrThreshold, setLocalAtrThreshold] = useState<number | null>(null);
  const atrThreshold = localAtrThreshold ?? data?.atr_threshold ?? 1.5;

  const mutation = useMutation({
    mutationFn: api.patchSettings,
    onSuccess: (updated) => {
      queryClient.setQueryData(["settings"], updated);
      setLocalAtrThreshold(updated.atr_threshold);
    }
  });

  function updateAtrThreshold(nextValue: number) {
    const clamped = Math.max(0.5, Math.min(5, Math.round(nextValue * 10) / 10));
    setLocalAtrThreshold(clamped);
  }

  useEffect(() => {
    if (!data || localAtrThreshold == null) return;
    const handle = window.setTimeout(() => {
      if (localAtrThreshold !== data.atr_threshold) {
        mutation.mutate({ atr_threshold: localAtrThreshold });
      }
    }, 450);
    return () => window.clearTimeout(handle);
  }, [data, localAtrThreshold, mutation]);

  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_360px]">
      <section className="rounded border border-[#2d333d] bg-[#171a20] p-5">
        <div className="mb-5 flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-semibold">Settings</h1>
            <p className="mt-1 text-sm text-[#a0a7b4]">Lokale UI-Änderungen reagieren sofort; Jobs übernehmen Werte beim nächsten Lauf.</p>
          </div>
          <SlidersHorizontal size={22} className="text-emerald-300" />
        </div>
        <div className="rounded border border-[#2d333d] bg-[#111419] p-4">
          <div className="mb-3 flex items-center justify-between">
            <div>
              <div className="text-sm font-medium">ATR-Schwellenwert</div>
              <div className="text-xs text-[#a0a7b4]">Debounced API-Patch, kein globaler Reload</div>
            </div>
            <StatusChip tone={mutation.isPending ? "warning" : "good"}>
              {mutation.isPending ? "speichert" : "lokal aktiv"}
            </StatusChip>
          </div>
          <div className="flex items-center gap-3">
            <button
              aria-label="ATR-Schwellenwert senken"
              className="flex size-10 items-center justify-center rounded border border-[#2d333d] bg-[#171a20] text-[#f4f6f8] transition hover:border-emerald-300/60"
              type="button"
              onClick={() => updateAtrThreshold(atrThreshold - 0.1)}
            >
              <Minus size={17} />
            </button>
            <input
              aria-label="ATR-Schwellenwert"
              className="w-full accent-emerald-300"
              type="range"
              min="0.5"
              max="5"
              step="0.1"
              value={atrThreshold}
              onChange={(event) => updateAtrThreshold(Number(event.target.value))}
              onInput={(event) => updateAtrThreshold(Number(event.currentTarget.value))}
            />
            <div className="w-16 rounded border border-[#2d333d] bg-[#171a20] px-3 py-2 text-right tabular-nums">
              {atrThreshold.toFixed(1)}
            </div>
            <button
              aria-label="ATR-Schwellenwert erhöhen"
              className="flex size-10 items-center justify-center rounded border border-[#2d333d] bg-[#171a20] text-[#f4f6f8] transition hover:border-emerald-300/60"
              type="button"
              onClick={() => updateAtrThreshold(atrThreshold + 0.1)}
            >
              <Plus size={17} />
            </button>
          </div>
        </div>
      </section>
      <aside className="rounded border border-[#2d333d] bg-[#171a20] p-5">
        <h2 className="text-base font-semibold">Datenjobs</h2>
        <div className="mt-4 space-y-3 text-sm">
          <div className="flex justify-between border-b border-[#242a33] pb-3">
            <span className="text-[#a0a7b4]">Monitor</span>
            <StatusChip tone={data?.position_monitor_enabled ? "good" : "neutral"}>
              {data?.position_monitor_enabled ? "aktiv" : "aus"}
            </StatusChip>
          </div>
          <div className="flex justify-between border-b border-[#242a33] pb-3">
            <span className="text-[#a0a7b4]">Intervall</span>
            <span>{data?.position_monitor_interval_minutes ?? 5} min</span>
          </div>
          <div className="flex justify-between">
            <span className="text-[#a0a7b4]">RS Quelle</span>
            <span>{data?.rs_rating_source ?? "csv_latest"}</span>
          </div>
        </div>
      </aside>
    </div>
  );
}
