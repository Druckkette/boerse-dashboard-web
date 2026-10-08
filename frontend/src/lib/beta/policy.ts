import rawRules from "./api-policy.json";
const rules: { method: string; path: string; query: string[]; exclude?: string[] }[] = rawRules;

// Runtime-only: any malformed mode fails into the restricted beta surface.
export function isBetaMode() {
  return Boolean(process.env.APP_BETA_MODE && process.env.APP_BETA_MODE !== "0");
}
const ticker = "[A-Za-z0-9][A-Za-z0-9.=_^-]{0,31}";
function pattern(path: string) {
  return new RegExp("^" + path.replaceAll("/", "\\/")
    .replace("{ticker}", ticker).replace("{group}", "[A-Za-z0-9_-]{1,80}")
    .replace("{job}", "beta_[a-f0-9]{32}") + "$");
}
export function betaApiAllowed(method: string, path: string, search = "") {
  if (path.includes("%") || path.includes("\\") || path.includes("..")) return false;
  const rule = rules.find((item) => item.method === method && pattern(item.path).test(path) && !item.exclude?.some(excluded => excluded === path));
  if (!rule || search.length > 2048) return false;
  const params = new URLSearchParams(search);
  if ([...params].length > 32) return false;
  return [...params].every(([key, value]) => rule.query.includes(key) && value.length <= 400);
}
export function betaPageAllowed(path: string) {
  return ["/", "/market", "/sectors", "/industry-groups", "/stocks", "/sell-check"].includes(path)
    || new RegExp("^/stocks/" + ticker + "$").test(path)
    || /^\/industry-groups\/[A-Za-z0-9_-]{1,80}$/.test(path);
}
export function betaWriteOriginAllowed(headers: Headers, origin: string) {
  const site = headers.get("sec-fetch-site");
  if (site && site !== "same-origin") return false;
  const supplied = headers.get("origin");
  if (!supplied) return false;
  const configured = process.env.BETA_PUBLIC_ORIGIN;
  if (configured) return supplied === configured;
  // Next can normalize its internal URL to localhost. The original Host remains
  // the browser destination; HTTPS reverse proxies may terminate TLS upstream.
  try {
    const actual = new URL(supplied);
    const expected = new URL(origin);
    return actual.host === (headers.get("host") || expected.host)
      && (actual.protocol === expected.protocol || actual.protocol === "https:");
  } catch { return false; }
}
