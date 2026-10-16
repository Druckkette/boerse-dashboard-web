export function portfolioYearStart(now = new Date()): string {
  const year = new Intl.DateTimeFormat("en", { timeZone: "Europe/Berlin", year: "numeric" }).format(now);
  return `${year}-01-01`;
}

export function nextPortfolioYearCheck(now = new Date()): number {
  const nextYear = Number(portfolioYearStart(now).slice(0, 4)) + 1;
  const januaryUtc = Date.UTC(nextYear, 0, 1);
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: "Europe/Berlin", year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23"
  }).formatToParts(new Date(januaryUtc));
  const value = (name: string) => Number(parts.find(part => part.type === name)?.value);
  const offset = Date.UTC(value("year"), value("month") - 1, value("day"), value("hour"), value("minute"), value("second")) - januaryUtc;
  return Math.max(1, Math.min(60_000, januaryUtc - offset - now.getTime()));
}
