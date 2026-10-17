"use client";
import { useProductUi } from "./ui-mode-provider";
import type { ReactNode } from "react";

export function QueryState({ loading, error, hasData, onRetry, children }: { loading?: boolean; error?: unknown; hasData: boolean; onRetry: () => unknown; children?: ReactNode }) {
  const product=useProductUi();
  if (hasData) return error ? <p role="alert" className="app-notice">Aktualisierung fehlgeschlagen. Der letzte geladene Stand bleibt sichtbar. <button type="button" className="underline" onClick={onRetry}>Erneut versuchen</button></p> : null;
  if (error) return <section className="dashboard-section" role="alert"><p>Daten derzeit nicht verfügbar. Fehlende Werte werden nicht als Null dargestellt.</p><p className="mt-1 text-sm text-[#687386]">{error instanceof Error ? error.message : "Abruf fehlgeschlagen"}</p><button type="button" className="app-button mt-3" onClick={onRetry}>Erneut versuchen</button></section>;
  if(product && loading && !children) return <div className="dashboard-section" role="status" aria-busy="true"><p className="sr-only">Daten werden geladen …</p><div className="grid gap-3 sm:grid-cols-3" aria-hidden="true">{[0,1,2].map(key=><div key={key} className="h-24 animate-pulse rounded-xl bg-[#e9eef3]"/>)}</div></div>;
  return <div className="dashboard-section" role="status" aria-busy={loading}>{children ?? "Daten werden geladen …"}</div>;
}
