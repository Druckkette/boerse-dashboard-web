type RefreshState = { finished: boolean };
export function shouldAutoRefresh(data: { fresh: boolean; refresh_needed?: boolean } | undefined, attempted: boolean) {
  return Boolean(data && (data.refresh_needed ?? !data.fresh) && !attempted);
}
export function refreshPollInterval(job: RefreshState | undefined) { return job?.finished ? false : 6000; }
export function betaRefreshQueryKeys(ticker: string) {
  return [["stock-prices", ticker], ["stock-fundamentals", ticker], ["stock-assessment", ticker],
    ["stock-rs", ticker], ["institutional-13f", ticker], ["stock-signal-changes", ticker],
    ["stock-assessment-ranking"], ["stock-screening"], ["stock-assessment-compare"], ["beta-freshness", ticker]];
}
