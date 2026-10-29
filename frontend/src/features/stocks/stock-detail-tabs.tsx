"use client";

import { useProductUi } from "@/components/ui/ui-mode-provider";
import { ProductDetails } from "@/components/ui/product-details";
import { StockIdentity } from "./stock-identity";
import { StockNewsPanel } from "./stock-news-panel";
import { useBetaMode } from "@/components/beta-mode-provider";
import { BetaStockDetailActions } from "./beta-stock-detail-actions";
import { BarChart3, Building2, ChartCandlestick, Gauge, TrendingUp } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { Institutional13FPanel } from "@/features/stocks/institutional-13f-panel";
import { IndustryGroupPanel } from "@/features/stocks/industry-group-panel";
import { StockAssessmentPanel } from "@/features/stocks/stock-assessment-panel";
import { StockDetailActions } from "@/features/stocks/stock-detail-actions";
import { StockFundamentalsPanel } from "@/features/stocks/stock-fundamentals-panel";
import { StockPricePanel } from "@/features/stocks/stock-price-panel";
import { StockRsPanel } from "@/features/stocks/stock-rs-panel";
import { StockSignalChangesPanel } from "@/features/stocks/stock-signal-changes-panel";
import { StockQuickActions } from "@/features/desk/stock-actions";

const tabs = [
  { key: "overview", label: "Übersicht", icon: Gauge },
  { key: "technical", label: "Technik", icon: TrendingUp },
  { key: "fundamental", label: "Fundamental", icon: BarChart3 },
  { key: "chart", label: "Chart", icon: ChartCandlestick },
  { key: "institutions", label: "Institutionen", icon: Building2 }
] as const;
type TabKey = (typeof tabs)[number]["key"];

export function StockDetailTabs({ ticker }: { ticker: string }) {
  const product = useProductUi();
  const beta = useBetaMode();
  const params = useSearchParams();
  const requested = params.get("tab");
  const active = tabs.some(tab => tab.key === requested) ? requested as TabKey : "overview";
  const setActive = (key: TabKey) => { const next = new URLSearchParams(window.location.search); next.set("tab", key); window.history.pushState(null, "", `${window.location.pathname}?${next}`); };
  return <div className="space-y-4">
    {product && <StockIdentity ticker={ticker} />}
    {!beta && <StockQuickActions ticker={ticker}/>}
    {beta && <BetaStockDetailActions key={ticker} ticker={ticker} />}
    {product && <label className="block text-xs font-medium text-[#687386] lg:hidden">Analysebereich<select aria-label="Aktienanalyse Bereich" className="input-dark mt-1" value={active} onChange={event=>setActive(event.target.value as TabKey)}>{tabs.map(tab=><option key={tab.key} value={tab.key}>{tab.label}</option>)}</select></label>}
    <nav aria-label="Aktienanalyse Bereiche" className={`${product ? "hidden lg:flex" : "flex"} sticky top-[var(--app-header-height,88px)] z-[8] gap-1 overflow-x-auto rounded-[12px] border border-[#e3e8ef] bg-white/95 p-1.5 shadow-[0_4px_14px_rgba(15,23,42,0.05)] backdrop-blur`}>
      {tabs.map((tab) => { const Icon = tab.icon; const selected = active === tab.key; return <button key={tab.key} aria-current={selected ? "page" : undefined} className={`inline-flex h-9 min-w-fit items-center gap-2 rounded-[9px] px-3 text-sm font-semibold transition ${selected ? "bg-[#0f766e] text-white" : "text-[#687386] hover:bg-[#f3f6f8] hover:text-[#172033]"}`} type="button" onClick={() => setActive(tab.key)}><Icon size={15} />{tab.label}</button>; })}
    </nav>
    {!beta && !product && <StockDetailActions key={ticker} ticker={ticker} />}
    <StockNewsPanel key={ticker} ticker={ticker} />
    {active === "overview" ? <>{!product && <IndustryGroupPanel ticker={ticker} />}<StockAssessmentPanel ticker={ticker} mode="overview" />{product && <><StockPricePanel ticker={ticker} title="Kurs und Relative Stärke" /><ProductDetails title="Branche & Einordnung"><IndustryGroupPanel ticker={ticker} /></ProductDetails></>}<StockSignalChangesPanel ticker={ticker} /></> : null}
    {active === "technical" ? <><StockAssessmentPanel ticker={ticker} mode="technical" /><StockRsPanel ticker={ticker} /></> : null}
    {active === "fundamental" ? <StockFundamentalsPanel ticker={ticker} /> : null}
    {active === "chart" ? <StockPricePanel ticker={ticker} title="Kurs und Relative Stärke" /> : null}
    {active === "institutions" ? <Institutional13FPanel ticker={ticker} /> : null}
    {!beta && product && <ProductDetails title="Daten aktualisieren & weitere Aktionen"><StockDetailActions key={ticker} ticker={ticker} /></ProductDetails>}
  </div>;
}
