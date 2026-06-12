import type { NextRequest } from "next/server";

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
  const target = buildTargetUrl(path, request.nextUrl.search);
  let response: Response;
  try {
    response = await fetch(target, {
      method: request.method,
      headers: forwardedHeaders(request.headers),
      body: request.method === "GET" || request.method === "HEAD" ? undefined : await request.arrayBuffer(),
      cache: "no-store"
    });
  } catch {
    return Response.json(
      { detail: "Backend service is currently unavailable" },
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

function forwardedHeaders(headers: Headers) {
  const nextHeaders = new Headers();
  headers.forEach((value, key) => {
    if (!HOP_BY_HOP_HEADERS.has(key.toLowerCase())) {
      nextHeaders.set(key, value);
    }
  });
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
