"use client";

import { MarketAmpelPanel } from "@/features/market/market-ampel-panel";
import { MarketBreadthOverviewPanel } from "@/features/market/market-breadth-overview-panel";
import {
  MarketCategorySection,
  type MarketCategoryTone
} from "@/features/market/market-category-section";
import {
  MarketRiskSectionsPanel,
  MarketSentimentPositioningPanel
} from "@/features/market/market-risk-sections-panel";
import { useState, type ReactNode } from "react";

const indexes = [
  { ticker: "^GSPC", label: "S&P500" },
  { ticker: "^IXIC", label: "NASDAQ" },
  { ticker: "^RUT", label: "Russell 2000" }
] as const;

export type MarketIndexTicker = (typeof indexes)[number]["ticker"];

export default function MarketPage() {
  const [ticker, setTicker] = useState<MarketIndexTicker>("^GSPC");

  return (
    <div className="space-y-4">
      <nav aria-label="Marktübersicht Bereiche" className="sticky top-[88px] z-[8] flex gap-1 overflow-x-auto rounded-[12px] border border-[#e3e8ef] bg-white/95 p-1.5 shadow-[0_4px_14px_rgba(15,23,42,0.05)] backdrop-blur">
        {[{ href: "#trend", label: "Trend-Ampel" }, { href: "#warnings", label: "Früh- und Warnzeichen" }, { href: "#breadth", label: "Marktbreite" }, { href: "#sentiment", label: "Stimmung" }].map((item) => <a key={item.href} className="inline-flex h-9 min-w-fit items-center rounded-[9px] px-3 text-sm font-semibold text-[#687386] transition hover:bg-[#e8f4f2] hover:text-[#0f766e]" href={item.href}>{item.label}</a>)}
      </nav>
      <section id="trend" className="scroll-mt-36"><MarketAmpelPanel indexes={indexes} ticker={ticker} onTickerChange={setTicker} /></section>
      <section id="warnings" className="scroll-mt-36"><MarketRiskSectionsPanel ticker={ticker} /></section>
      <div id="breadth" className="scroll-mt-36"><MarketArea
        marker="03"
        tone="breadth"
        title="Marktbreite"
        description="Russell-vs-S&P, Equal-Weight-ETFs, A/D, Volumen, McClellan, NH/NL, MA-Teilnahme und Deemer Ratio."
      >
        <MarketBreadthOverviewPanel ticker={ticker} />
      </MarketArea></div>
      <div id="sentiment" className="scroll-mt-36"><MarketArea
        marker="04"
        tone="sentiment"
        title="Stimmungs- und Positionierungsindikatoren"
        description="VIX, VXX und Margin Debt als separate Sentiment- und Positionierungsprüfung."
      >
        <MarketSentimentPositioningPanel ticker={ticker} />
      </MarketArea></div>
    </div>
  );
}

function MarketArea({
  children,
  description,
  marker,
  tone,
  title
}: {
  children: ReactNode;
  description: string;
  marker: string;
  tone: MarketCategoryTone;
  title: string;
}) {
  return (
    <MarketCategorySection description={description} marker={marker} title={title} tone={tone}>
      {children}
    </MarketCategorySection>
  );
}
