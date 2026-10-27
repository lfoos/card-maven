"""Authentication happens once per request (``authenticate_request``) so rate
limiting can key on the caller; authorization happens per route (``require_user``)."""

from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from typing import Any

from flask import current_app, g, request

from card_maven.identity.models import User
from card_maven.identity.service import VerifiedIdentity, provision_user
from card_maven.shared.errors import AuthenticationError, CardMavenError, PermissionDeniedError
from card_maven_api.auth.tokens import Principal
from card_maven_api.db import transaction
from card_maven_api.extensions import api_context


def bearer_token() -> str | None:
    header = request.headers.get("Authorization", "")
    if not header:
        return None
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise AuthenticationError("a bearer token is required")
    return token.strip()


def authenticate_request() -> None:
    """``before_request`` hook: verify a bearer token if one was sent.

    Failures are remembered, not raised: public routes stay public, and
    ``require_user`` raises the stored error on protected ones.
    """
    g.principal = None
    g.auth_error = None
    try:
        token = bearer_token()
        if token is not None:
            g.principal = api_context(current_app).token_verifier.verify(token)
    except CardMavenError as error:
        g.auth_error = error


def current_principal() -> Principal:
    principal: Principal | None = g.get("principal")
    if principal is None:
        error: CardMavenError | None = g.get("auth_error")
        raise error or AuthenticationError("a bearer token is required")
    return principal


def current_user() -> User:
    user: User | None = g.get("user")
    if user is None:
        raise AuthenticationError()
    return user


def require_user[F: Callable[..., Any]](view: F | None = None, *, role: str | None = None) -> Any:
    """Require a verified caller, provision their user row, and expose it as
    ``current_user()``. Usable as ``@require_user`` or ``@require_user(role=...)``."""

    def decorator(func: F) -> F:
        @wraps(func)
        def wrapped(*args: Any, **kwargs: Any) -> Any:
            principal = current_principal()
            if role is not None and not principal.has_role(role):
                raise PermissionDeniedError(f"requires the '{role}' role")
            with transaction() as session:
                g.user = provision_user(
                    session,
                    VerifiedIdentity(
                        issuer=principal.issuer,
                        subject=principal.subject,
                        email=principal.email,
                        display_name=principal.name,
                    ),
                )
            return func(*args, **kwargs)

        return wrapped  # type: ignore[return-value]

    return decorator(view) if view is not None else decorator


def require_auth(*, role: str | None = None) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Require a verified caller without touching the database.

    For routes that only need the token's claims (e.g. operator endpoints);
    collector-facing routes use ``require_user``.
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        def wrapped(*args: Any, **kwargs: Any) -> Any:
            principal = current_principal()
            if role is not None and not principal.has_role(role):
                raise PermissionDeniedError(f"requires the '{role}' role")
            return func(*args, **kwargs)

        return wrapped

    return decorator
