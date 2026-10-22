"use client";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api/client";
import { DateStatus, Failure } from "./shared";
import { useBetaMode } from "@/components/beta-mode-provider";
export function StockQuickActions({ ticker }: { ticker: string }) {
  const beta = useBetaMode(),
    client = useQueryClient();
  const workspace = useQuery({
    queryKey: ["workspace"],
    queryFn: api.workspace,
    enabled: !beta,
    staleTime: 30_000,
  });
  const price = useQuery({
    queryKey: ["stock-prices", ticker, "1y"],
    queryFn: () => api.stockPrices(ticker, "1y"),
    staleTime: 60_000,
  });
  const save = useMutation({
    mutationFn: () => api.addWorkspaceTicker(ticker),
    onSuccess: async (state) => {
      if (state.source !== "database")
        throw new Error("Watchlist wurde nicht gespeichert.");
      client.setQueryData(["workspace"], state);
      await Promise.all([
        client.invalidateQueries({ queryKey: ["desk"] }),
        client.invalidateQueries({ queryKey: ["home-dashboard"] }),
      ]);
    },
  });
  if (beta) return null;
  const observed = workspace.data?.watchlist.includes(ticker);
  const compare = encodeURIComponent(
    JSON.stringify({
      version: 1,
      tickers: [ticker, "SPY"],
      category: "Gesamtscore",
    }),
  );
  const params = new URLSearchParams({ ticker });
  if (price.data?.last_close)
    params.set("entry", String(price.data.last_close));
  if (price.data?.currency) params.set("currency", price.data.currency);
  return (
    <section
      aria-label="Aktionen für diese Aktie"
      className="dashboard-section space-y-3"
    >
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          className="app-button"
          disabled={
            save.isPending || observed || workspace.data?.source !== "database"
          }
          onClick={() => save.mutate()}
        >
          {observed ? "Auf der Watchlist" : "Beobachten"}
        </button>
        <Link
          className="app-button"
          href={`/stocks?compare=${compare}#aktienvergleich`}
        >
          Vergleichen
        </Link>
        <Link
          className="app-button app-button-primary"
          href={`/workspace?${params}#einstieg`}
        >
          Einstieg planen
        </Link>
        <Link className="app-button" href="/workspace#watchlists">
          Watchlists verwalten
        </Link>
      </div>
      {price.data && (
        <DateStatus
          asOf={price.data.last_date || price.data.as_of}
          limited={price.data.data_status !== "fresh"}
        >
          Kurswährung {price.data.currency} ·{" "}
          {price.data.source === "database"
            ? "Kursdatenbank"
            : "Kursdaten fehlen"}
        </DateStatus>
      )}
      <Failure error={save.error} />
    </section>
  );
}
