"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowRight, Search } from "lucide-react";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { api } from "@/lib/api/client";
import type { FormEvent } from "react";
import type { StockAssessmentRankingItem } from "@/lib/types/api";

export function StockSearchPanel() {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const ranking = useQuery({
    queryKey: ["stock-assessment-ranking", "stock-search"],
    queryFn: () => api.stockAssessmentRanking(500),
    staleTime: 5 * 60_000
  });
  const trimmed = query.trim();
  const suggestions = useMemo(
    () => findStockMatches(trimmed, ranking.data?.rows ?? []).slice(0, 6),
    [ranking.data?.rows, trimmed]
  );

  function submit(event?: FormEvent<HTMLFormElement>) {
    event?.preventDefault();
    const input = query.trim();
    if (!input) {
      setMessage("Ticker oder Firmenname eingeben.");
      return;
    }
    const match = findBestStockMatch(input, ranking.data?.rows ?? []);
    if (match) {
      router.push(`/stocks/${encodeURIComponent(match.ticker.toUpperCase())}`);
      return;
    }
    if (looksLikeTicker(input)) {
      router.push(`/stocks/${encodeURIComponent(normalizeTickerInput(input))}`);
      return;
    }
    setMessage("Keine eindeutige Aktie im Ranking gefunden. Bitte Ticker eingeben.");
  }

  return (
    <section className="rounded border border-[#2d333d] bg-[#171a20] p-5">
      <div className="mb-4 flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
        <div>
          <h2 className="text-base font-semibold">Aktie bewerten</h2>
          <p className="mt-1 text-sm leading-5 text-[#a0a7b4]">
            Ticker oder Firmenname eingeben und direkt in den Bewertungsscreen springen.
          </p>
        </div>
        <div className="text-xs uppercase tracking-[0.18em] text-[#77808f]">
          {ranking.isLoading ? "Suche lädt" : `${ranking.data?.rows.length ?? 0} Werte`}
        </div>
      </div>
      <form className="flex flex-col gap-3 md:flex-row" onSubmit={submit}>
        <label className="relative flex-1">
          <Search className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-[#77808f]" size={17} />
          <input
            className="input-dark w-full pl-10"
            placeholder="z. B. NVDA, Apple oder Bloom Energy"
            value={query}
            onChange={(event) => {
              setQuery(event.target.value);
              setMessage(null);
            }}
          />
        </label>
        <button
          className="inline-flex items-center justify-center gap-2 rounded border border-emerald-300/50 bg-emerald-300 px-4 py-2 text-sm font-semibold text-[#111419] transition hover:bg-emerald-200"
          type="submit"
        >
          Bewertung öffnen
          <ArrowRight size={16} />
        </button>
      </form>
      {message && <div className="mt-3 text-sm text-amber-200">{message}</div>}
      {trimmed && suggestions.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-2">
          {suggestions.map((item) => (
            <button
              className="rounded border border-[#2d333d] bg-[#111419] px-3 py-2 text-left text-sm transition hover:border-emerald-300/60"
              key={item.ticker}
              type="button"
              onClick={() => router.push(`/stocks/${encodeURIComponent(item.ticker.toUpperCase())}`)}
            >
              <span className="font-semibold text-[#f2f5f9]">{item.ticker}</span>
              <span className="ml-2 text-[#a0a7b4]">{item.name}</span>
            </button>
          ))}
        </div>
      )}
    </section>
  );
}

function findStockMatches(input: string, rows: StockAssessmentRankingItem[]) {
  const clean = normalizeSearchText(input);
  if (!clean) return [];
  return rows
    .filter((row) => {
      const ticker = normalizeSearchText(row.ticker);
      const name = normalizeSearchText(row.name);
      return ticker.startsWith(clean) || name.includes(clean);
    })
    .sort((left, right) => scoreMatch(input, right) - scoreMatch(input, left));
}

function findBestStockMatch(input: string, rows: StockAssessmentRankingItem[]) {
  const matches = findStockMatches(input, rows);
  if (!matches.length) return null;
  const clean = normalizeSearchText(input);
  return (
    matches.find((row) => normalizeSearchText(row.ticker) === clean) ??
    matches.find((row) => normalizeSearchText(row.name) === clean) ??
    matches[0]
  );
}

function scoreMatch(input: string, row: StockAssessmentRankingItem) {
  const clean = normalizeSearchText(input);
  const ticker = normalizeSearchText(row.ticker);
  const name = normalizeSearchText(row.name);
  if (ticker === clean) return 1000;
  if (name === clean) return 900;
  if (ticker.startsWith(clean)) return 800 - ticker.length;
  if (name.startsWith(clean)) return 700 - name.length / 100;
  return 500 - name.indexOf(clean);
}

function looksLikeTicker(value: string) {
  const clean = normalizeTickerInput(value);
  return /^[A-Z0-9.^=-]{1,12}$/.test(clean);
}

function normalizeTickerInput(value: string) {
  return value.trim().toUpperCase().replace(/\s+/g, "");
}

function normalizeSearchText(value: string) {
  return value.trim().toLowerCase().replace(/\s+/g, " ");
}
