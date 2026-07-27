"use client";

import { BarChart3, Building2, ChartCandlestick, Gauge, TrendingUp } from "lucide-react";
import { useState } from "react";
import { Institutional13FPanel } from "@/features/stocks/institutional-13f-panel";
import { StockAssessmentPanel } from "@/features/stocks/stock-assessment-panel";
import { StockDetailActions } from "@/features/stocks/stock-detail-actions";
import { StockFundamentalsPanel } from "@/features/stocks/stock-fundamentals-panel";
import { StockPricePanel } from "@/features/stocks/stock-price-panel";
import { StockRsPanel } from "@/features/stocks/stock-rs-panel";
import { StockSignalChangesPanel } from "@/features/stocks/stock-signal-changes-panel";

const tabs = [
  { key: "overview", label: "Übersicht", icon: Gauge },
  { key: "technical", label: "Technik", icon: TrendingUp },
  { key: "fundamental", label: "Fundamental", icon: BarChart3 },
  { key: "chart", label: "Chart", icon: ChartCandlestick },
  { key: "institutions", label: "Institutionen", icon: Building2 }
] as const;
type TabKey = (typeof tabs)[number]["key"];

export function StockDetailTabs({ ticker }: { ticker: string }) {
  const [active, setActive] = useState<TabKey>("overview");
  return <div className="space-y-4">
    <nav aria-label="Aktienanalyse Bereiche" className="sticky top-[88px] z-[8] flex gap-1 overflow-x-auto rounded-[12px] border border-[#e3e8ef] bg-white/95 p-1.5 shadow-[0_4px_14px_rgba(15,23,42,0.05)] backdrop-blur">
      {tabs.map((tab) => { const Icon = tab.icon; const selected = active === tab.key; return <button key={tab.key} aria-current={selected ? "page" : undefined} className={`inline-flex h-9 min-w-fit items-center gap-2 rounded-[9px] px-3 text-sm font-semibold transition ${selected ? "bg-[#0f766e] text-white" : "text-[#687386] hover:bg-[#f3f6f8] hover:text-[#172033]"}`} type="button" onClick={() => setActive(tab.key)}><Icon size={15} />{tab.label}</button>; })}
    </nav>
    {active === "overview" ? <><StockDetailActions ticker={ticker} /><StockAssessmentPanel ticker={ticker} mode="overview" /><StockSignalChangesPanel ticker={ticker} /></> : null}
    {active === "technical" ? <><StockAssessmentPanel ticker={ticker} mode="technical" /><StockRsPanel ticker={ticker} /></> : null}
    {active === "fundamental" ? <StockFundamentalsPanel ticker={ticker} /> : null}
    {active === "chart" ? <StockPricePanel ticker={ticker} title="Kurs und Relative Stärke" /> : null}
    {active === "institutions" ? <Institutional13FPanel ticker={ticker} /> : null}
  </div>;
}
