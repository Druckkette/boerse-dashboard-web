import { Suspense } from "react";
import { TradeJournalWorkspace } from "@/features/trade-journal/trade-journal-workspace";

export default function Page() {
  return <Suspense fallback={<div className="h-72 animate-pulse rounded-[16px] bg-white" />}><TradeJournalWorkspace /></Suspense>;
}
