import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";
import { isAuthorized, isAuthEnabled, unauthorizedResponse } from "@/lib/auth/basic-auth";
import { betaAuthorized, betaDenied } from "@/lib/beta/auth";
import { betaApiAllowed, betaPageAllowed, betaWriteOriginAllowed, isBetaMode } from "@/lib/beta/policy";

export function proxy(request: NextRequest) {
  if (isBetaMode()) {
    if (!betaAuthorized(request.headers)) return betaDenied();
    const path = request.nextUrl.pathname;
    const api = path.startsWith("/api/v1/");
    const asset = path.startsWith("/_next/static/") || path === "/favicon.ico";
    const allowed = api ? betaApiAllowed(request.method, path.slice(8), request.nextUrl.search)
      : (request.method === "GET" || request.method === "HEAD") && (asset || betaPageAllowed(path));
    if (!allowed || (request.method === "POST" && !betaWriteOriginAllowed(request.headers, request.nextUrl.origin))) {
      return new NextResponse("In der Beta nicht verfügbar", { status: 403, headers: { "Cache-Control": "no-store" } });
    }
    const response = NextResponse.next();
    response.headers.set("Cache-Control", "no-store");
    response.headers.set("X-Robots-Tag", "noindex, nofollow");
    response.headers.set("Referrer-Policy", "same-origin");
    return response;
  }
  if (!isAuthEnabled() || isAuthorized(request)) return NextResponse.next();
  return unauthorizedResponse();
}
// No file-extension bypasses: private URLs and RSC requests use the same gate.
export const config = { matcher: ["/:path*"] };
