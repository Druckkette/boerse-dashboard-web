import { ChartPlaceholder } from "@/components/ui/chart-placeholder";
import { StatusChip } from "@/components/ui/status-chip";

const rows = ["NVDA", "MSFT", "PLTR", "LLY", "AAPL", "META"];

export default function StocksPage() {
  return (
    <div className="space-y-5">
      <div className="flex flex-col justify-between gap-4 rounded border border-[#2d333d] bg-[#171a20] p-5 md:flex-row md:items-center">
        <div>
          <h1 className="text-2xl font-semibold">Stocks</h1>
          <p className="mt-1 text-sm text-[#a0a7b4]">Screening, Vergleich und Detailanalyse werden hier angebunden.</p>
        </div>
        <StatusChip tone="neutral">Dummy universe</StatusChip>
      </div>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {rows.map((ticker) => (
          <a key={ticker} href={`/stocks/${ticker}`} className="rounded border border-[#2d333d] bg-[#171a20] p-4 transition hover:border-emerald-300/60 hover:bg-[#1f242c]">
            <div className="text-lg font-semibold">{ticker}</div>
            <div className="mt-2 text-sm text-[#a0a7b4]">Technik, RS, Fundamentals</div>
          </a>
        ))}
      </div>
      <ChartPlaceholder title="Stock Compare" caption="Ranking-Chart-Platzhalter" />
    </div>
  );
}

