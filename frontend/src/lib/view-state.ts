"use client";
import { useSearchParams } from "next/navigation";

export function parseViewState<T extends Record<string, unknown>>(raw: string | null, defaults: T): T {
  const value = { ...defaults };
  try {
    const stored = JSON.parse(raw || "null");
    if (!stored || typeof stored !== "object" || Array.isArray(stored) || stored.version !== 1) return value;
    for (const key of Object.keys(defaults)) {
      const candidate = stored[key], fallback = defaults[key];
      if (Array.isArray(fallback)) {
        if (Array.isArray(candidate) && candidate.length <= 100 && candidate.every(item => typeof item === "string" && item.length <= 200)) value[key as keyof T] = candidate as T[keyof T];
      } else if (typeof candidate === typeof fallback && (typeof candidate !== "number" || Number.isFinite(candidate)) && (typeof candidate !== "string" || candidate.length <= 1000)) value[key as keyof T] = candidate;
    }
  } catch { /* Malformed links retain safe current defaults. */ }
  return value;
}

export function useViewState<T extends Record<string, unknown>>(scope: string, defaults: T): [T, (patch: Partial<T>) => void] {
  const params = useSearchParams();
  const value = parseViewState(params.get(scope), defaults);
  function update(patch: Partial<T>) {
    const next = new URLSearchParams(window.location.search);
    const current = parseViewState(next.get(scope), defaults);
    next.set(scope, JSON.stringify({ ...current, ...patch, version: 1 }));
    window.history.replaceState(null, "", `${window.location.pathname}?${next}${window.location.hash}`);
  }
  return [value, update];
}
