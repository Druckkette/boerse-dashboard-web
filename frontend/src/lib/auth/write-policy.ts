/** Browser writes require the same public origin, including behind TLS termination. */
export function privateWriteOriginAllowed(headers: Headers, internalOrigin: string) {
  const site = headers.get("sec-fetch-site");
  if (site && site !== "same-origin") return false;
  const supplied = headers.get("origin");
  if (!supplied) return false;
  try {
    const actual = new URL(supplied);
    const configured = process.env.APP_PUBLIC_ORIGIN;
    if (configured) return actual.origin === new URL(configured).origin;
    const internal = new URL(internalOrigin);
    return actual.host === (headers.get("host") || internal.host) && ["http:", "https:"].includes(actual.protocol)
      && (actual.protocol === internal.protocol || actual.protocol === "https:");
  } catch { return false; }
}
