from __future__ import annotations

import time
from collections import defaultdict, deque
from collections.abc import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp


DEFAULT_EXEMPT_PATHS = ("/api/v1/health", "/docs", "/redoc", "/api/v1/openapi.json", "/openapi.json")


class InMemoryRateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app: ASGIApp,
        *,
        max_requests: int,
        window_seconds: int,
        exempt_paths: tuple[str, ...] = DEFAULT_EXEMPT_PATHS,
    ) -> None:
        super().__init__(app)
        self.max_requests = max(1, int(max_requests))
        self.window_seconds = max(1, int(window_seconds))
        self.exempt_paths = exempt_paths
        self._requests: dict[str, deque[float]] = defaultdict(deque)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if self._is_exempt(request.url.path):
            return await call_next(request)

        now = time.monotonic()
        key = self._client_key(request)
        bucket = self._requests[key]
        threshold = now - self.window_seconds
        while bucket and bucket[0] <= threshold:
            bucket.popleft()

        if len(bucket) >= self.max_requests:
            retry_after = max(1, int(self.window_seconds - (now - bucket[0]))) if bucket else self.window_seconds
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Rate limit exceeded.",
                    "limit": self.max_requests,
                    "window_seconds": self.window_seconds,
                    "retry_after_seconds": retry_after,
                },
                headers={"Retry-After": str(retry_after)},
            )

        bucket.append(now)
        return await call_next(request)

    def _is_exempt(self, path: str) -> bool:
        return any(path == exempt or path.startswith(f"{exempt}/") for exempt in self.exempt_paths)

    def _client_key(self, request: Request) -> str:
        forwarded_for = request.headers.get("x-forwarded-for", "")
        if forwarded_for:
            return forwarded_for.split(",", 1)[0].strip()
        if request.client and request.client.host:
            return request.client.host
        return "unknown"
