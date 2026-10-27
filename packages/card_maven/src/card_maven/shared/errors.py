"""Error taxonomy shared by every context.

Domain and service code raise these. The API maps them to RFC 9457
``application/problem+json`` responses, and workers map them to retry or
dead-letter decisions. Each error carries a stable machine-readable ``code``.
"""

from __future__ import annotations

from typing import Any, ClassVar


class CardMavenError(Exception):
    """Base class. Unexpected failures surface as ``internal_error`` (HTTP 500)."""

    code: ClassVar[str] = "internal_error"
    status: ClassVar[int] = 500
    title: ClassVar[str] = "Internal server error"
    retryable: ClassVar[bool] = False

    def __init__(self, detail: str | None = None, **extra: Any) -> None:
        super().__init__(detail or self.title)
        self.detail = detail or self.title
        self.extra = extra


class InvalidInputError(CardMavenError):
    code = "invalid_input"
    status = 422
    title = "Invalid input"


class NotFoundError(CardMavenError):
    code = "not_found"
    status = 404
    title = "Resource not found"


class ConflictError(CardMavenError):
    code = "conflict"
    status = 409
    title = "Conflict"


class AuthenticationError(CardMavenError):
    code = "unauthenticated"
    status = 401
    title = "Authentication required"


class PermissionDeniedError(CardMavenError):
    code = "permission_denied"
    status = 403
    title = "Permission denied"


class DependencyUnavailableError(CardMavenError):
    """An external dependency (database, Kafka, IdP, model provider) is unavailable."""

    code = "dependency_unavailable"
    status = 503
    title = "Dependency unavailable"
    retryable = True
