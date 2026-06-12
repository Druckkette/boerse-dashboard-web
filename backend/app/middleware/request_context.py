from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from contextvars import ContextVar
from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp


request_id_var: ContextVar[str] = ContextVar("request_id", default="")
logger = logging.getLogger("app.access")


class RequestContextMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, *, access_log_enabled: bool = False) -> None:
        super().__init__(app)
        self.access_log_enabled = access_log_enabled

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        request_id = _clean_request_id(request.headers.get("x-request-id")) or uuid4().hex
        token = request_id_var.set(request_id)
        start = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers["X-Request-ID"] = request_id
            return response
        except Exception:
            self._log(request, request_id, status_code, start, exc_info=True)
            raise
        finally:
            if self.access_log_enabled:
                self._log(request, request_id, status_code, start)
            request_id_var.reset(token)

    def _log(
        self,
        request: Request,
        request_id: str,
        status_code: int,
        start: float,
        *,
        exc_info: bool = False,
    ) -> None:
        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        payload = {
            "event": "http_request",
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status_code": status_code,
            "duration_ms": duration_ms,
            "client": request.client.host if request.client else "",
        }
        logger.info(json.dumps(payload, separators=(",", ":")), exc_info=exc_info)


def _clean_request_id(value: str | None) -> str:
    clean = str(value or "").strip()
    if not clean:
        return ""
    allowed = "".join(char for char in clean if char.isalnum() or char in {"-", "_", "."})
    return allowed[:128]
