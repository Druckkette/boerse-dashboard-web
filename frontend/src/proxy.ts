import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";
import { isAuthorized, isAuthEnabled, unauthorizedResponse } from "@/lib/auth/basic-auth";

export function proxy(request: NextRequest) {
  if (!isAuthEnabled() || isAuthorized(request)) {
    return NextResponse.next();
  }
  return unauthorizedResponse();
}

export const config = {
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|robots.txt|sitemap.xml|.*\\.(?:png|jpg|jpeg|gif|webp|svg|ico|css|js|map)$).*)"
  ]
};
