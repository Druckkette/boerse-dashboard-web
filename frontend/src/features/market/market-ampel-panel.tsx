"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api/client";
import { MarketJournalView, marketDayOptions, marketIndexes, type MarketJournalTicker } from "./market-journal-view";
import { useMarketRefetchInterval } from "./query-timing";
import styles from "./market-journal.module.css";

export function MarketAmpelPanel({ indexes = marketIndexes, onTickerChange, ticker = "^GSPC" }: {
  indexes?: readonly (typeof marketIndexes)[number][];
  onTickerChange?: (ticker: MarketJournalTicker) => void;
  ticker?: MarketJournalTicker;
}) {
  const refetchInterval = useMarketRefetchInterval();
  const [days, setDays] = useState<(typeof marketDayOptions)[number]>(90);
  const query = useQuery({
    queryKey: ["market-ampel", ticker, days],
    queryFn: () => api.marketAmpel(ticker, days),
    staleTime: 60_000,
    refetchInterval
  });
  if (query.isLoading || (query.data && query.data.ticker !== ticker)) {
    return <section className={styles.journal}><p className={styles.notices} role="status">Marktampel lädt …</p></section>;
  }
  if (!query.data) {
    return <section className={styles.journal}><p className={styles.notices} role="alert">Marktampel ist aktuell nicht erreichbar.</p></section>;
  }
  return <MarketJournalView
    key={query.data.ticker}
    data={query.data}
    days={days}
    indexes={indexes}
    isFetching={query.isFetching}
    updateFailed={query.isError}
    onDaysChange={setDays}
    onRefresh={() => { void query.refetch(); }}
    onTickerChange={onTickerChange}
  />;
}
