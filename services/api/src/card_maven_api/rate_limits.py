"""Rate limiting: per verified user when signed in, per client IP otherwise.

Each app gets its own ``Limiter`` (no module-level singleton), so settings and
counters never leak between app instances. Routes declare stricter limits with
``@rate_limited(...)``; the limiter applies them when the app is built.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, cast

from flask import Flask, current_app, g, request
from flask_limiter import Limiter

from card_maven.shared.config import Settings

UPLOAD_START_LIMIT = "30/minute"
WRITE_LIMIT = "60/minute"
EXEMPT_ENDPOINTS = ("health.liveness", "health.readiness", "openapi_spec")
_MARK = "_card_maven_rate_limit"
_EXTENSION = "card_maven_limiter"


def rate_limit_key() -> str:
    principal = g.get("principal")
    if principal is not None:
        return f"user:{principal.issuer}|{principal.subject}"
    return f"ip:{request.remote_addr or 'unknown'}"


def rate_limited[F: Callable[..., Any]](limit: str) -> Callable[[F], F]:
    """Declare a route's own limit (in addition to the default)."""

    def mark(view: F) -> F:
        setattr(view, _MARK, limit)
        return view

    return mark


def init_rate_limits(app: Flask, settings: Settings) -> Limiter:
    limiter = Limiter(
        key_func=rate_limit_key,
        app=app,
        default_limits=[settings.rate_limit_default],
        storage_uri=settings.rate_limit_storage_uri,
        headers_enabled=True,
        enabled=settings.rate_limits_enabled,
    )
    # Flask-Limiter holds only a weak reference; keep the limiter alive with the app.
    app.extensions[_EXTENSION] = limiter
    for endpoint, view in list(app.view_functions.items()):
        if endpoint in EXEMPT_ENDPOINTS:
            limiter.exempt(view)
        elif limit := getattr(view, _MARK, None):
            app.view_functions[endpoint] = cast(Any, limiter.limit(limit)(view))
    return limiter


def reset_rate_limits() -> None:
    """Clear all counters for the current app (tests and operations)."""
    limiter: Limiter = current_app.extensions[_EXTENSION]
    limiter.reset()
