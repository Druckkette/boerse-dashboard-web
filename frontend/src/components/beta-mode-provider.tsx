"use client";
import { configureBetaApiRequests } from "@/lib/beta/request-limiter";
import { createContext, useContext, type ReactNode } from "react";
const BetaMode = createContext(false);
export function BetaModeProvider({ beta, children }: { beta: boolean; children: ReactNode }) {
  if (typeof window !== "undefined") configureBetaApiRequests(beta);
  return <BetaMode.Provider value={beta}>{children}</BetaMode.Provider>;
}
export function useBetaMode() { return useContext(BetaMode); }
