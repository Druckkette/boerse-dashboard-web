export type StockNews = {
  ticker: string;
  articles: {
    uuid: string;
    title: string;
    description: string | null;
    url: string;
    source: string;
    published_at: string;
    entities: { symbol: string; name: string; exchange: string | null; match_score: number | null; sentiment_score: number | null }[];
    match_score: number | null;
    sentiment_score: number | null;
  }[];
  updated_at: string | null;
  status: "ok" | "empty" | "stale" | "not_configured" | "limit_reached" | "unavailable" | "unsupported";
  cached: boolean;
  message: string | null;
};
