import { timingSafeEqual } from "node:crypto";

export function betaAccessConfigured() {
  if (process.env.APP_BETA_MODE !== "1" || (process.env.BETA_PROXY_SECRET || "").length < 32) return false;
  if (process.env.BETA_ACCESS_MODE === "public") return process.env.BETA_PUBLIC_ENABLED === "1";
  return (process.env.BETA_ACCESS_MODE || "password") === "password" && (process.env.BETA_AUTH_PASSWORD || "").length >= 12;
}
export function betaAuthorized(headers: Headers) {
  if (!betaAccessConfigured()) return false;
  if (process.env.BETA_ACCESS_MODE === "public") return true;
  const value = headers.get("authorization") || "";
  if (!/^Basic [A-Za-z0-9+/]+=*$/.test(value)) return false;
  const actual = Buffer.from(value.slice(6), "base64");
  const expected = Buffer.from(`beta:${process.env.BETA_AUTH_PASSWORD}`);
  return actual.length === expected.length && timingSafeEqual(actual, expected);
}
export function betaDenied() {
  return new Response(betaAccessConfigured() ? "Beta-Zugang erforderlich" : "Beta-Zugang ist nicht konfiguriert", {
    status: betaAccessConfigured() ? 401 : 503,
    headers: { "WWW-Authenticate": 'Basic realm="Boerse Beta", charset="UTF-8"', "Cache-Control": "no-store" }
  });
}
