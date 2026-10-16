"use client";
import { GlobalStockSearch } from "@/components/ui/header-tools";
export function StockSearchPanel() {
  return <section className="dashboard-section"><h2 className="font-semibold">Aktie bewerten</h2><p className="mb-3 mt-1 text-sm text-[#687386]">Ticker oder Firmenname im gesamten gespeicherten Universum suchen.</p><GlobalStockSearch label="Aktie für Bewertung suchen" /></section>;
}
