from __future__ import annotations

import time
from collections import OrderedDict, deque
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
        max_clients: int = 10000,
    ) -> None:
        super().__init__(app)
        self.max_requests = max(1, int(max_requests))
        self.window_seconds = max(1, int(window_seconds))
        self.exempt_paths = exempt_paths
        self.max_clients = max(1, max_clients)
        self._requests: OrderedDict[str, deque[float]] = OrderedDict()

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if self._is_exempt(request.url.path):
            return await call_next(request)

        now = time.monotonic()
        threshold = now - self.window_seconds
        while self._requests:
            oldest = next(iter(self._requests.values()))
            if oldest and oldest[-1] > threshold:
                break
            self._requests.popitem(last=False)
        key = self._client_key(request)
        if key not in self._requests:
            if len(self._requests) >= self.max_clients:
                return JSONResponse({"detail": "Rate limit capacity reached."}, status_code=429,
                                    headers={"Retry-After": str(self.window_seconds)})
            self._requests[key] = deque()
        bucket = self._requests[key]
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
        self._requests.move_to_end(key)
        return await call_next(request)

    def _is_exempt(self, path: str) -> bool:
        return any(path == exempt or path.startswith(f"{exempt}/") for exempt in self.exempt_paths)

    def _client_key(self, request: Request) -> str:
        # Trust the ASGI transport identity only. Uvicorn proxy headers are
        # disabled in deployment; the frontend is one intentionally shared
        # budget. Browser-controlled forwarding headers cannot mint new budgets.
        if request.client and request.client.host:
            return request.client.host
        return "unknown"
