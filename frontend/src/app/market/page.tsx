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
      <MarketAmpelPanel indexes={indexes} ticker={ticker} onTickerChange={setTicker} />
      <MarketRiskSectionsPanel ticker={ticker} />
      <MarketArea
        marker="03"
        tone="breadth"
        title="Marktbreite"
        description="Russell-vs-S&P, Equal-Weight-ETFs, A/D, Volumen, McClellan, NH/NL, MA-Teilnahme und Deemer Ratio."
      >
        <MarketBreadthOverviewPanel ticker={ticker} />
      </MarketArea>
      <MarketArea
        marker="04"
        tone="sentiment"
        title="Stimmungs- und Positionierungsindikatoren"
        description="VIX, VXX und Margin Debt als separate Sentiment- und Positionierungsprüfung."
      >
        <MarketSentimentPositioningPanel ticker={ticker} />
      </MarketArea>
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
