"""Request-scoped behavior applied to every response."""

from __future__ import annotations

import re
import uuid

import structlog
from flask import Flask, Response, g, request

REQUEST_ID_HEADER = "X-Request-ID"
_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    # The API serves JSON only, so it can forbid everything.
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
    "Cross-Origin-Resource-Policy": "same-site",
    "Cache-Control": "no-store",
}
HSTS = "max-age=63072000; includeSubDomains"

CORS_ALLOWED_HEADERS = "Authorization, Content-Type, X-Request-ID"
CORS_ALLOWED_METHODS = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
CORS_MAX_AGE = "600"


def register_middleware(app: Flask, *, cors_origins: list[str], hsts: bool) -> None:
    allowed_origins = frozenset(cors_origins)

    @app.before_request
    def _assign_request_id() -> Response | None:
        incoming = request.headers.get(REQUEST_ID_HEADER, "")
        # Accept a caller's id only if it is safe to log and echo back.
        g.request_id = incoming if _SAFE_REQUEST_ID.match(incoming) else uuid.uuid4().hex
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=g.request_id)

        if request.method == "OPTIONS" and "Access-Control-Request-Method" in request.headers:
            return Response(status=204)  # CORS headers are added below
        return None

    @app.after_request
    def _decorate(response: Response) -> Response:
        response.headers[REQUEST_ID_HEADER] = g.get("request_id", "")
        for name, value in SECURITY_HEADERS.items():
            response.headers.setdefault(name, value)
        if hsts:
            response.headers.setdefault("Strict-Transport-Security", HSTS)

        origin = request.headers.get("Origin")
        if origin and origin in allowed_origins:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Headers"] = CORS_ALLOWED_HEADERS
            response.headers["Access-Control-Allow-Methods"] = CORS_ALLOWED_METHODS
            response.headers["Access-Control-Expose-Headers"] = REQUEST_ID_HEADER
            response.headers["Access-Control-Max-Age"] = CORS_MAX_AGE
        response.headers.add("Vary", "Origin")
        return response

    @app.teardown_request
    def _clear_log_context(_error: BaseException | None) -> None:
        # Don't let this request's id leak into logs emitted later on this thread.
        structlog.contextvars.clear_contextvars()
