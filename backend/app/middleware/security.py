"""
Security + request tracing middleware.

Adds stable headers (CSP, frame denial, MIME sniffing), request id for logs,
and lightweight request duration logging.
"""
from __future__ import annotations

import time
import uuid
from typing import Callable

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.config import get_settings
from app.core.metrics import incr as metrics_incr

log = structlog.get_logger(__name__)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Non-invasive API hardening (JSON API — minimal CSP)."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        settings = get_settings()
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"] = settings.CSP
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        # HSTS should be set at reverse proxy in production; optional here if HTTPS:
        if settings.COOKIE_SECURE:
            response.headers["Strict-Transport-Security"] = (
                "max-age=63072000; includeSubDomains; preload"
            )
        return response


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Request id + structlog context + basic metrics."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        rid = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=rid)
        metrics_incr("http_requests_total")
        t0 = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            metrics_incr("http_errors_total")
            raise
        response.headers["X-Request-ID"] = rid
        elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
        log.info(
            "http.request",
            method=request.method,
            path=request.url.path,
            status_code=getattr(response, "status_code", 0),
            elapsed_ms=elapsed_ms,
        )
        return response
