"use client";

import { MarketAmpelPanel } from "@/features/market/market-ampel-panel";
import { MarketBreadthOverviewPanel } from "@/features/market/market-breadth-overview-panel";
import { MarketOverviewPanel } from "@/features/market/market-overview-panel";
import {
  MarketRiskSectionsPanel,
  MarketSentimentPositioningPanel
} from "@/features/market/market-risk-sections-panel";
import { useState, type ReactNode } from "react";

const indexes = [
  { ticker: "^GSPC", label: "S&P 500" },
  { ticker: "^IXIC", label: "Nasdaq" },
  { ticker: "^RUT", label: "Russell 2000" }
] as const;

export type MarketIndexTicker = (typeof indexes)[number]["ticker"];

export default function MarketPage() {
  const [ticker, setTicker] = useState<MarketIndexTicker>("^GSPC");

  return (
    <div className="space-y-5">
      <MarketAmpelPanel indexes={indexes} ticker={ticker} onTickerChange={setTicker} />
      <MarketOverviewPanel ticker={ticker} />
      <MarketRiskSectionsPanel indexes={indexes} ticker={ticker} onTickerChange={setTicker} />
      <MarketArea
        title="Marktbreite"
        description="Russell-vs-S&P, Equal-Weight-ETFs, A/D, Volumen, McClellan, NH/NL, MA-Teilnahme und Deemer Ratio."
      >
        <MarketBreadthOverviewPanel ticker={ticker} />
      </MarketArea>
      <MarketArea
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
  title
}: {
  children: ReactNode;
  description: string;
  title: string;
}) {
  return (
    <section className="space-y-3">
      <div>
        <h2 className="text-lg font-semibold tracking-normal">{title}</h2>
        <p className="mt-1 max-w-4xl text-sm leading-6 text-[#a0a7b4]">{description}</p>
      </div>
      {children}
    </section>
  );
}
