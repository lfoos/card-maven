from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from typing import ParamSpec, TypeVar

from flask import current_app, g, request

from card_maven.shared.errors import AuthenticationError, PermissionDeniedError
from card_maven_api.auth.tokens import Principal, TokenVerifier
from card_maven_api.extensions import api_context

P = ParamSpec("P")
R = TypeVar("R")


def bearer_token() -> str:
    header = request.headers.get("Authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise AuthenticationError("a bearer token is required")
    return token.strip()


def current_principal() -> Principal:
    principal: Principal | None = g.get("principal")
    if principal is None:
        raise AuthenticationError()
    return principal


def require_auth(*, role: str | None = None) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Verify the bearer token and expose the caller as ``current_principal()``."""

    def decorator(view: Callable[P, R]) -> Callable[P, R]:
        @wraps(view)
        def wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
            verifier: TokenVerifier = api_context(current_app).token_verifier
            principal = verifier.verify(bearer_token())
            if role is not None and not principal.has_role(role):
                raise PermissionDeniedError(f"requires the '{role}' role")
            g.principal = principal
            return view(*args, **kwargs)

        return wrapped

    return decorator
