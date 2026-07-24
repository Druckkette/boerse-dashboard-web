"use client";

import { MarketAmpelPanel } from "@/features/market/market-ampel-panel";
import { MarketBreadthOverviewPanel } from "@/features/market/market-breadth-overview-panel";
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
    <section className="space-y-2.5">
      <div>
        <h2 className="text-base font-semibold text-[#172033]">{title}</h2>
        <p className="mt-0.5 max-w-4xl text-xs leading-5 text-[#687386]">{description}</p>
      </div>
      {children}
    </section>
  );
}
