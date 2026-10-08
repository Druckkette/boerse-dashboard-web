"""Second gate for the restricted frontend credential, with shared read cache."""
import json
import secrets

from fastapi import HTTPException
from starlette.concurrency import run_in_threadpool
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

from app.beta_policy import beta_api_allowed, public_projection
from app.core_config import get_settings
from app.services import beta


class BetaAccessMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        credential = request.headers.get("x-beta-proxy-key")
        path = request.url.path
        if credential is None and not path.startswith("/api/v1/beta/"):
            return await call_next(request)
        settings = get_settings()
        expected = settings.beta_proxy_secret
        if len(expected) < 32 or not credential or not secrets.compare_digest(credential.encode(), expected.encode()):
            return JSONResponse({"detail": "Beta-Zugang nicht verfügbar."}, status_code=403)
        if not path.startswith("/api/v1/") or not beta_api_allowed(
            request.method, path.removeprefix("/api/v1/"), request.url.query
        ):
            return JSONResponse({"detail": "In der Beta nicht verfügbar."}, status_code=403)
        if request.method == "POST":
            # Also enforce bounded requests at the internal boundary.
            body = bytearray()
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body) > 4096:
                    return JSONResponse({"detail": "Anfrage zu groß."}, status_code=413)
            request._body = bytes(body)
        cacheable = request.method == "GET" and not path.startswith("/api/v1/beta/stock-refresh/")
        compute_lease = None
        try:
            def admission():
                with beta.protection() as client:
                    beta.rate_limit(client, "read", settings.beta_read_requests_per_minute)
                    key = beta.cache_key(client, path, request.url.query) if cacheable else None
                    cached = client.get(key) if key else None
                    lease = beta.acquire_compute_slot(client, "read", settings.beta_read_max_active) if cacheable and not cached else None
                    return key, cached, lease
            key, cached, compute_lease = await run_in_threadpool(admission)
            if cached:
                return Response(cached, media_type="application/json", headers={"Cache-Control": "no-store"})
            response = await call_next(request)
            # Beta APIs are JSON-only. Do not pass backend errors, tracebacks or headers.
            body = b"".join([part async for part in response.body_iterator])
            if response.status_code >= 400:
                detail = "Daten derzeit nicht verfügbar. Bitte später erneut versuchen."
                if response.status_code in {404, 409, 429, 503}:
                    try:
                        message = json.loads(body).get("detail", "")
                        # Only our authored operational messages may cross the boundary.
                        if path.startswith("/api/v1/beta/") and isinstance(message, str):
                            detail = message
                    except (ValueError, AttributeError):
                        pass
                elif response.status_code == 422:
                    detail = "Ungültige Eingaben. Bitte Ticker, Preis, Datum und Währung prüfen."
                headers = {"Cache-Control": "no-store"}
                if "retry-after" in response.headers:
                    headers["Retry-After"] = response.headers["retry-after"]
                return JSONResponse({"detail": detail}, status_code=response.status_code, headers=headers)
            data = json.loads(body)
            if path.startswith("/api/v1/beta/stock-refresh/") or path.endswith("/refresh"):
                safe = data  # Already an explicit projection, with public beta handle only.
            else:
                safe = public_projection(data)
            encoded = json.dumps(safe, ensure_ascii=False, allow_nan=False)
            if key:
                def cache():
                    with beta.protection() as client:
                        client.set(key, encoded, ex=30)
                await run_in_threadpool(cache)
            return Response(encoded, media_type="application/json", headers={"Cache-Control": "no-store"})
        except HTTPException as exc:
            return JSONResponse({"detail": exc.detail}, status_code=exc.status_code, headers=exc.headers)
        except Exception:
            # Keep operational/private details out of beta error bodies and logs.
            return JSONResponse({"detail": "Beta-Daten derzeit nicht verfügbar."}, status_code=503)

        finally:
            if compute_lease:
                def release():
                    try:
                        beta.redis_client().zrem("beta:read-active", compute_lease)
                    except Exception:
                        pass  # Lease expires even when Redis is temporarily unavailable.
                await run_in_threadpool(release)
