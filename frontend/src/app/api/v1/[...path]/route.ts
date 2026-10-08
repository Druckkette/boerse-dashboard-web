import type { NextRequest } from "next/server";
import { isAuthorized, unauthorizedResponse } from "@/lib/auth/basic-auth";
import { betaAuthorized, betaDenied } from "@/lib/beta/auth";
import { betaApiAllowed, betaWriteOriginAllowed, isBetaMode } from "@/lib/beta/policy";

type RouteContext = {
  params: Promise<{ path: string[] }>;
};

const HOP_BY_HOP_HEADERS = new Set([
  "authorization",
  "connection",
  "content-length",
  "host",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailer",
  "transfer-encoding",
  "upgrade"
]);

export async function GET(request: NextRequest, context: RouteContext) {
  return forwardToBackend(request, context);
}

export async function POST(request: NextRequest, context: RouteContext) {
  return forwardToBackend(request, context);
}

export async function PATCH(request: NextRequest, context: RouteContext) {
  return forwardToBackend(request, context);
}

export async function PUT(request: NextRequest, context: RouteContext) {
  return forwardToBackend(request, context);
}

export async function DELETE(request: NextRequest, context: RouteContext) {
  return forwardToBackend(request, context);
}

async function forwardToBackend(request: NextRequest, context: RouteContext) {
  const { path } = await context.params;
  const beta = isBetaMode();
  if (beta && !betaAuthorized(request.headers)) return betaDenied();
  if (!beta && !isAuthorized(request)) return unauthorizedResponse();
  if (beta && (!betaApiAllowed(request.method, path.join("/"), request.nextUrl.search)
    || (request.method === "POST" && !betaWriteOriginAllowed(request.headers, request.nextUrl.origin)))) {
    return Response.json({ detail: "In der Beta nicht verfügbar" }, { status: 403 });
  }
  let body: ArrayBuffer | Uint8Array | undefined;
  if (!["GET", "HEAD"].includes(request.method)) {
    if (beta) {
      const reader = request.body?.getReader();
      const parts: Uint8Array[] = [];
      let length = 0;
      if (reader) {
        while (true) {
          const part = await reader.read();
          if (part.done) break;
          length += part.value.length;
          if (length > 4096) {
            await reader.cancel();
            return Response.json({ detail: "Anfrage zu groß" }, { status: 413 });
          }
          parts.push(part.value);
        }
      }
      const bytes = new Uint8Array(length);
      let offset = 0;
      for (const part of parts) { bytes.set(part, offset); offset += part.length; }
      body = bytes;
    } else body = await request.arrayBuffer();
  }
  const target = buildTargetUrl(path, request.nextUrl.search);
  let response: Response;
  try {
    response = await fetch(target, {
      method: request.method,
      headers: forwardedHeaders(request.headers, beta),
      body: body as BodyInit | undefined,
      redirect: "error",
      signal: AbortSignal.timeout(60_000),
      cache: "no-store"
    });
  } catch (error) {
    if (beta) return Response.json({ detail: "Beta-Daten derzeit nicht verfügbar" }, { status: 502 });
    return Response.json(
      {
        detail: "Backend service is currently unavailable",
        hint: "The Next.js frontend proxy could not reach the FastAPI backend. Check backend container health, API_INTERNAL_BASE_URL and Docker network DNS.",
        target_origin: safeTargetOrigin(target),
        error: compactError(error)
      },
      {
        status: 502,
        headers: {
          "Cache-Control": "no-store"
        }
      }
    );
  }

  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers: responseHeaders(response.headers)
  });
}

function buildTargetUrl(path: string[], search: string) {
  const base = (process.env.API_INTERNAL_BASE_URL || "http://localhost:8000")
    .replace(/\/api\/v1\/?$/, "")
    .replace(/\/$/, "");
  const cleanPath = path.map((part) => encodeURIComponent(part)).join("/");
  return `${base}/api/v1/${cleanPath}${search}`;
}

function safeTargetOrigin(target: string) {
  try {
    const url = new URL(target);
    return url.origin;
  } catch {
    return "unparseable";
  }
}

function compactError(error: unknown) {
  if (error instanceof Error) {
    return `${error.name}: ${error.message}`.slice(0, 300);
  }
  return String(error).slice(0, 300);
}

function forwardedHeaders(headers: Headers, beta: boolean) {
  const nextHeaders = new Headers();
  headers.forEach((value, key) => {
    const lower = key.toLowerCase();
    if (beta ? ["content-type", "accept", "x-beta-capability"].includes(lower)
      : !HOP_BY_HOP_HEADERS.has(lower) && !lower.startsWith("x-beta-") && lower !== "x-role") {
      nextHeaders.set(key, value);
    }
  });
  if (beta) nextHeaders.set("x-beta-proxy-key", process.env.BETA_PROXY_SECRET || "");
  return nextHeaders;
}

function responseHeaders(headers: Headers) {
  const nextHeaders = new Headers();
  headers.forEach((value, key) => {
    const lower = key.toLowerCase();
    if (lower !== "content-encoding" && lower !== "content-length" && lower !== "transfer-encoding") {
      nextHeaders.set(key, value);
    }
  });
  nextHeaders.set("Cache-Control", "no-store");
  return nextHeaders;
}
