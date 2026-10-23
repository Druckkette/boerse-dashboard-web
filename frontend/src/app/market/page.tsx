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
import { useState, Suspense, type ReactNode } from "react";
import { ArrowDown } from "lucide-react";
import { useSearchParams } from "next/navigation";

const indexes = [
  { ticker: "^GSPC", label: "S&P500" },
  { ticker: "^IXIC", label: "NASDAQ" },
  { ticker: "^RUT", label: "Russell 2000" }
] as const;

export type MarketIndexTicker = (typeof indexes)[number]["ticker"];

export default function MarketPage() {
  return <Suspense fallback={<div className="dashboard-section">Marktübersicht wird geladen …</div>}><MarketContent /></Suspense>;
}

function MarketContent() {
  const params = useSearchParams();
  const requested = params.get("ticker");
  const initial = indexes.find((index) => index.ticker === requested)?.ticker ?? "^GSPC";
  return <MarketDashboard key={initial} initialTicker={initial} />;
}

function MarketDashboard({ initialTicker }: { initialTicker: MarketIndexTicker }) {
  const [ticker, setTicker] = useState<MarketIndexTicker>(initialTicker);

  return (
    <div className="space-y-4">
      <nav aria-label="Marktübersicht Bereiche" className="product-market-jumps rounded-xl border border-[#e3e8ef] bg-white p-3 shadow-sm">
        <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-[#687386]">Direkt zum Bereich</p>
        <div className="product-market-jump-links">
          {[
            { href: "#trend", label: "Trend-Ampel" },
            { href: "#context-scores", label: "Kontext-Scores" },
            { href: "#warnings", label: "Früh- und Warnzeichen" },
            { href: "#breadth", label: "Marktbreite" },
            { href: "#sentiment", label: "Stimmung" },
          ].map((item) => (
            <a key={item.href} href={item.href}>
              <span>{item.label}</span>
              <ArrowDown size={16} aria-hidden="true" />
            </a>
          ))}
        </div>
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
