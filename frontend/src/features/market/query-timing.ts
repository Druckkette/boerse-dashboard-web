"use client";
import { useBetaMode } from "@/components/beta-mode-provider";
export const MARKET_REFETCH_INTERVAL_MS = 60_000;
export function useMarketRefetchInterval() { return useBetaMode() ? false : MARKET_REFETCH_INTERVAL_MS; }
