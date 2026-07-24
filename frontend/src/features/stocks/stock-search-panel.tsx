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
    <section className="rounded-[14px] border border-[#dce5eb] bg-white p-4 shadow-[0_5px_18px_rgba(15,23,42,0.05)]">
      <div className="mb-3 flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
        <div>
          <h2 className="text-base font-semibold text-[#172033]">Aktie bewerten</h2>
          <p className="mt-0.5 text-xs leading-5 text-[#687386]">
            Ticker oder Firmenname eingeben und direkt in den Bewertungsscreen springen.
          </p>
        </div>
        <div className="text-[10px] font-semibold uppercase tracking-[0.1em] text-[#687386]">
          {ranking.isLoading ? "Suche lädt" : `${ranking.data?.rows.length ?? 0} Werte`}
        </div>
      </div>
      <form className="flex flex-col gap-2 md:flex-row" onSubmit={submit}>
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
          className="inline-flex h-10 items-center justify-center gap-2 rounded-[10px] bg-[#0f766e] px-4 text-sm font-semibold text-white transition hover:bg-[#0b655f]"
          type="submit"
        >
          Bewertung öffnen
          <ArrowRight size={16} />
        </button>
      </form>
      {message && <div className="mt-2 text-sm text-[#b7791f]">{message}</div>}
      {trimmed && suggestions.length > 0 && (
        <div className="mt-2.5 flex flex-wrap gap-1.5">
          {suggestions.map((item) => (
            <button
              className="rounded-[9px] border border-[#e3e8ef] bg-[#f9fbfd] px-2.5 py-1.5 text-left text-sm transition hover:border-[#9ccfc6] hover:bg-[#f3faf8]"
              key={item.ticker}
              type="button"
              onClick={() => router.push(`/stocks/${encodeURIComponent(item.ticker.toUpperCase())}`)}
            >
              <span className="font-semibold text-[#172033]">{item.ticker}</span>
              <span className="ml-2 text-[#687386]">{item.name}</span>
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
