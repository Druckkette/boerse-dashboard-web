"use client";

import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, Database, Search, XCircle } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";
import { api } from "@/lib/api/client";
import { qualityLabel } from "@/lib/format";

export function HeaderTools() {
  return (
    <div className="flex w-full flex-col gap-2 sm:flex-row xl:w-auto">
      <GlobalStockSearch />
      <DataQualityLink />
    </div>
  );
}

function GlobalStockSearch() {
  const router = useRouter();
  const [value, setValue] = useState("");
  const [query, setQuery] = useState("");
  useEffect(() => {
    const timer = window.setTimeout(() => setQuery(value.trim()), 180);
    return () => window.clearTimeout(timer);
  }, [value]);
  const results = useQuery({
    queryKey: ["global-stock-search", query],
    queryFn: () => api.stockSearch(query),
    enabled: query.length >= 1,
    staleTime: 5 * 60_000
  });

  function openTicker(ticker: string) {
    setValue("");
    setQuery("");
    router.push(`/stocks/${encodeURIComponent(ticker.toUpperCase())}`);
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    const direct = query.toUpperCase().replace(/\s+/g, "");
    const match = results.data?.rows[0];
    if (match) openTicker(match.ticker);
    else if (/^[A-Z0-9.^=-]{1,16}$/.test(direct)) openTicker(direct);
  }

  return (
    <form className="relative min-w-0 sm:w-[310px]" onSubmit={submit}>
      <Search className="pointer-events-none absolute left-3 top-1/2 z-10 size-4 -translate-y-1/2 text-[#687386]" />
      <input
        aria-label="Aktie global suchen"
        className="h-9 w-full rounded-[10px] border border-[#d8e1ea] bg-white pl-9 pr-3 text-sm text-[#172033] outline-none transition placeholder:text-[#8b95a5] focus:border-[#0f766e] focus:ring-2 focus:ring-[#0f766e]/10"
        placeholder="Ticker oder Unternehmen"
        value={value}
        onChange={(event) => setValue(event.target.value)}
      />
      {query && results.data?.rows.length ? (
        <div className="absolute right-0 top-11 z-30 w-full overflow-hidden rounded-[12px] border border-[#d8e1ea] bg-white p-1.5 shadow-[0_16px_40px_rgba(15,23,42,0.14)]">
          {results.data.rows.map((item) => (
            <button
              key={item.ticker}
              className="flex w-full items-center justify-between gap-3 rounded-[8px] px-2.5 py-2 text-left transition hover:bg-[#f3f8f7]"
              type="button"
              onClick={() => openTicker(item.ticker)}
            >
              <span className="min-w-0">
                <span className="font-semibold text-[#172033]">{item.ticker}</span>
                <span className="ml-2 truncate text-xs text-[#687386]">{item.name}</span>
              </span>
              <span className="shrink-0 text-[10px] uppercase text-[#8b95a5]">{item.exchange}</span>
            </button>
          ))}
        </div>
      ) : null}
    </form>
  );
}

function DataQualityLink() {
  const diagnostics = useQuery({
    queryKey: ["data-quality-header"],
    queryFn: api.dataDiagnostics,
    staleTime: 60_000,
    refetchInterval: 5 * 60_000
  });
  const status = diagnostics.data?.decision_status ?? "limited";
  const Icon = status === "trusted" ? CheckCircle2 : status === "blocked" ? XCircle : AlertTriangle;
  const tone = status === "trusted"
    ? "border-[#b7e2cf] bg-[#eaf7ef] text-[#138a57]"
    : status === "blocked"
      ? "border-[#f0b9b5] bg-[#fff0ef] text-[#c2413b]"
      : "border-[#efd58f] bg-[#fff7df] text-[#9a650f]";
  return (
    <Link
      className={`inline-flex h-9 shrink-0 items-center justify-center gap-2 rounded-[10px] border px-3 text-sm font-semibold transition hover:brightness-[0.98] ${tone}`}
      href="/settings#data-quality"
      title={diagnostics.data?.summary ?? "Datenqualität wird geprüft"}
    >
      {diagnostics.isLoading ? <Database className="size-4 animate-pulse" /> : <Icon className="size-4" />}
      {diagnostics.isLoading ? "Daten prüfen" : qualityLabel(status)}
    </Link>
  );
}
