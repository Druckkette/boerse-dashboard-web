"use client";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api/client";
import { formatMoney, formatDateTime } from "@/lib/format";
export function StockIdentity({ ticker }: { ticker: string }) {
  const price = useQuery({
    queryKey: ["stock-prices", ticker, "1y"],
    queryFn: () => api.stockPrices(ticker, "1y"),
    staleTime: 60_000,
  });
  const data = price.data;
  return (
    <section
      aria-label="Unternehmen und Kursstand"
      className="dashboard-section"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="break-words text-lg font-semibold">
            {data?.name || ticker}
          </h2>
          <p className="mt-1 text-xs text-[#687386]">
            {ticker} · Kursstand{" "}
            {data?.last_date || data?.as_of || "wird geladen"}
          </p>
        </div>
        <div className="text-right">
          <p className="text-xl font-semibold tabular-nums">
            {formatMoney(data?.last_close, data?.currency || "USD")}
          </p>
          <p className="text-xs text-[#687386]">
            Tageskurse ·{" "}
            {data?.data_status === "fresh"
              ? "aktuell bestätigt"
              : "Datenstand prüfen"}
          </p>
        </div>
      </div>
      {data && (
        <details className="mt-2 text-xs text-[#687386]">
          <summary className="cursor-pointer">Datenstand & Quelle</summary>
          <p className="mt-2">
            Kursbeobachtung {data.last_date || data.as_of} · erwartete
            Börsensitzung {data.expected_as_of || "nicht bekannt"}
          </p>
          <p className="mt-1">
            Gespeichert / abgerufen {formatDateTime(data.cache_updated_at)} ·
            Quelle{" "}
            {data.source === "database" ? "Kursdatenbank" : "nicht verfügbar"}
          </p>
        </details>
      )}
    </section>
  );
}
