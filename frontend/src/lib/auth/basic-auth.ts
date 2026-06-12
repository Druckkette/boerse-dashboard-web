import type { NextRequest } from "next/server";

export function isAuthEnabled() {
  return process.env.APP_AUTH_ENABLED === "1" || process.env.APP_AUTH_ENABLED === "true";
}

export function isAuthorized(request: NextRequest) {
  if (!isAuthEnabled()) return true;
  const expectedUser = process.env.APP_AUTH_USER || "";
  const expectedPassword = process.env.APP_AUTH_PASSWORD || "";
  if (!expectedUser || !expectedPassword) return false;

  const authorization = request.headers.get("authorization") || "";
  if (!authorization.startsWith("Basic ")) return false;
  const decoded = decodeBasicAuth(authorization.slice("Basic ".length));
  if (!decoded) return false;
  return timingSafeEqual(decoded.user, expectedUser) && timingSafeEqual(decoded.password, expectedPassword);
}

export function unauthorizedResponse() {
  return new Response("Authentication required", {
    status: 401,
    headers: {
      "WWW-Authenticate": 'Basic realm="boerse-dashboard-web", charset="UTF-8"',
      "Cache-Control": "no-store"
    }
  });
}

function decodeBasicAuth(value: string) {
  try {
    const decoded = atob(value);
    const separator = decoded.indexOf(":");
    if (separator < 0) return null;
    return {
      user: decoded.slice(0, separator),
      password: decoded.slice(separator + 1)
    };
  } catch {
    return null;
  }
}

function timingSafeEqual(left: string, right: string) {
  const maxLength = Math.max(left.length, right.length);
  let diff = left.length ^ right.length;
  for (let index = 0; index < maxLength; index += 1) {
    diff |= (left.charCodeAt(index) || 0) ^ (right.charCodeAt(index) || 0);
  }
  return diff === 0;
}
