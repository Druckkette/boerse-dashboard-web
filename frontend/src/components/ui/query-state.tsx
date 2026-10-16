"use client";
import type { ReactNode } from "react";

export function QueryState({ loading, error, hasData, onRetry, children }: { loading?: boolean; error?: unknown; hasData: boolean; onRetry: () => unknown; children?: ReactNode }) {
  if (hasData) return error ? <p role="alert" className="app-notice">Aktualisierung fehlgeschlagen. Der letzte geladene Stand bleibt sichtbar. <button type="button" className="underline" onClick={onRetry}>Erneut versuchen</button></p> : null;
  if (error) return <section className="dashboard-section" role="alert"><p>Daten derzeit nicht verfügbar. Fehlende Werte werden nicht als Null dargestellt.</p><p className="mt-1 text-sm text-[#687386]">{error instanceof Error ? error.message : "Abruf fehlgeschlagen"}</p><button type="button" className="app-button mt-3" onClick={onRetry}>Erneut versuchen</button></section>;
  return <div className="dashboard-section" role="status" aria-busy={loading}>{children ?? "Daten werden geladen …"}</div>;
}
