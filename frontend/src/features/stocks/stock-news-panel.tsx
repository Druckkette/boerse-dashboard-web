"use client";

import { useQuery } from "@tanstack/react-query";
import { ExternalLink, Newspaper } from "lucide-react";
import { api } from "@/lib/api/client";
import { formatDateTime } from "@/lib/format";
import { QueryState } from "@/components/ui/query-state";

function publishedLabel(value: string) {
  const time = new Date(value).getTime();
  if (!Number.isFinite(time)) return "Zeitpunkt nicht verfügbar";
  const seconds = Math.round((time - Date.now()) / 1000);
  if (seconds > 60 || seconds < -7 * 86400) return formatDateTime(value);
  const relative = new Intl.RelativeTimeFormat("de-DE", { numeric: "auto" });
  if (Math.abs(seconds) < 60) return relative.format(0, "second");
  if (Math.abs(seconds) < 3600) return relative.format(Math.round(seconds / 60), "minute");
  if (Math.abs(seconds) < 86400) return relative.format(Math.round(seconds / 3600), "hour");
  return relative.format(Math.round(seconds / 86400), "day");
}

function articleLink(value: string) {
  try {
    const url = new URL(value);
    return ["https:", "http:"].includes(url.protocol) && !url.username && !url.password ? url.href : null;
  } catch { return null; }
}

export function StockNewsPanel({ ticker }: { ticker: string }) {
  const clean = ticker.trim().toUpperCase();
  const query = useQuery({
    queryKey: ["stock-news", clean],
    queryFn: () => api.stockNews(clean),
    enabled: Boolean(clean),
    // Reopening checks the server's durable cache; no timer or focus request
    // can consume the provider budget while another page is being viewed.
    staleTime: 0,
    gcTime: 60 * 60 * 1000,
    refetchOnMount: true,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    refetchInterval: false,
    retry: false,
  });
  const data = query.data?.ticker === clean ? query.data : undefined;
  const articles = (data?.articles ?? []).slice(0, 3).flatMap(article => {
    const href = articleLink(article.url);
    return href ? [{ ...article, href }] : [];
  });
  return <section className="dashboard-section" aria-label={`Aktuelle Nachrichten zu ${clean}`} aria-busy={query.isLoading}>
    <div className="flex flex-wrap items-center justify-between gap-2">
      <h2 className="flex items-center gap-2 text-lg font-semibold text-[#172033]"><Newspaper size={19} aria-hidden="true" />Aktuelle Nachrichten</h2>
      <span className="text-xs text-[#687386]">{clean} · Marketaux</span>
    </div>
    {query.isLoading ? <div className="mt-3"><QueryState loading hasData={false} onRetry={() => query.refetch()} /></div> : null}
    {query.isError && !articles.length ? <p role="status" className="mt-3 text-sm text-[#687386]">Nachrichten sind derzeit nicht verfügbar. Die übrige Aktienanalyse steht weiter zur Verfügung.</p> : null}
    {data && !articles.length && !query.isError ? <p role="status" className="mt-3 text-sm text-[#687386]">{
      data.status === "empty" || data.status === "ok" ? "Aktuell keine Unternehmensnachrichten verfügbar."
        : data.message || "Nachrichten sind derzeit nicht verfügbar."
    }</p> : null}
    {articles.length > 0 ? <div className="mt-3 grid gap-3 lg:grid-cols-3">
      {articles.map(article => <article key={article.uuid} className="flex min-w-0 flex-col rounded-[10px] border border-[#e3e8ef] bg-[#f9fbfc] p-3 transition hover:border-[#0f766e]">
        <h3 className="break-words text-sm font-semibold leading-5 text-[#172033]">
          <a href={article.href} target="_blank" rel="noopener noreferrer" className="rounded-sm hover:text-[#0f766e] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#0f766e]">{article.title}<ExternalLink size={13} aria-hidden="true" className="ml-1 inline-block shrink-0" /><span className="sr-only"> (Originalartikel in neuem Tab)</span></a>
        </h3>
        {article.description ? <p className="mt-2 line-clamp-3 break-words text-xs leading-5 text-[#687386]">{article.description}</p> : null}
        <div className="mt-auto flex flex-wrap items-center justify-between gap-2 border-t border-[#e3e8ef] pt-2 text-[11px] text-[#687386]">
          <span className="mt-2 break-all font-medium">{article.source}</span>
          <time className="mt-2" dateTime={article.published_at} title={formatDateTime(article.published_at)}>{publishedLabel(article.published_at)}</time>
        </div>
      </article>)}
    </div> : null}
    {articles.length > 0 && (query.isError || data?.status !== "ok") ? <p role="status" className="mt-3 text-xs text-[#687386]">{data?.message || "Die Aktualisierung ist derzeit nicht möglich. Der letzte verfügbare Stand bleibt sichtbar."}</p> : null}
    {data?.updated_at ? <p className="mt-3 text-xs text-[#687386]">Zuletzt aktualisiert: <time dateTime={data.updated_at}>{formatDateTime(data.updated_at)}</time></p> : null}
  </section>;
}
