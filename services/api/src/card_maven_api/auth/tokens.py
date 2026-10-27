"""Provider-agnostic verification of OIDC access tokens (JWTs).

Only standard claims are checked against the configured issuer, audience, and
JWKS, so Keycloak, Cognito, or any other compliant provider works unchanged.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any, Protocol

import jwt

from card_maven.shared.errors import AuthenticationError, DependencyUnavailableError

# Asymmetric algorithms only; "none" and HMAC are never accepted.
ALLOWED_ALGORITHMS = ("RS256", "ES256")
REQUIRED_CLAIMS = ("exp", "iat", "iss", "sub")


class SigningKeyProvider(Protocol):
    """Implemented by ``jwt.PyJWKClient`` (which caches keys and refetches on rotation)."""

    def get_signing_key_from_jwt(self, token: str) -> jwt.PyJWK: ...


@dataclass(frozen=True, slots=True)
class Principal:
    """The authenticated caller, as asserted by the identity provider."""

    issuer: str
    subject: str
    email: str | None = None
    name: str | None = None
    roles: frozenset[str] = field(default_factory=frozenset)

    def has_role(self, role: str) -> bool:
        return role in self.roles


def extract_roles(claims: dict[str, Any]) -> frozenset[str]:
    """Read roles from the claim shapes the supported providers use."""
    candidates: list[Any] = [
        claims.get("roles"),  # generic
        (claims.get("realm_access") or {}).get("roles"),  # Keycloak
        claims.get("cognito:groups"),  # Cognito
    ]
    roles: set[str] = set()
    for value in candidates:
        if isinstance(value, Iterable) and not isinstance(value, str | bytes | dict):
            roles.update(str(v) for v in value)
    return frozenset(roles)


class TokenVerifier:
    def __init__(
        self,
        *,
        issuer: str,
        audience: str,
        keys: SigningKeyProvider,
        leeway_seconds: int = 30,
    ) -> None:
        self._issuer = issuer
        self._audience = audience
        self._keys = keys
        self._leeway = leeway_seconds

    @classmethod
    def from_jwks_url(cls, *, issuer: str, audience: str, jwks_url: str) -> TokenVerifier:
        return cls(
            issuer=issuer,
            audience=audience,
            keys=jwt.PyJWKClient(jwks_url, cache_keys=True, lifespan=300, timeout=5),
        )

    def verify(self, token: str) -> Principal:
        try:
            signing_key = self._keys.get_signing_key_from_jwt(token)
        except jwt.PyJWKClientConnectionError as exc:
            raise DependencyUnavailableError("identity provider keys are unavailable") from exc
        except (jwt.PyJWKClientError, jwt.DecodeError) as exc:
            raise AuthenticationError("token signing key is not recognized") from exc

        try:
            claims: dict[str, Any] = jwt.decode(
                token,
                key=signing_key.key,
                algorithms=list(ALLOWED_ALGORITHMS),
                audience=self._audience,
                issuer=self._issuer,
                leeway=self._leeway,
                options={"require": list(REQUIRED_CLAIMS)},
            )
        except jwt.ExpiredSignatureError as exc:
            raise AuthenticationError("token has expired") from exc
        except jwt.InvalidTokenError as exc:
            # Covers bad signature, audience, issuer, algorithm, and missing claims.
            raise AuthenticationError("token is invalid") from exc

        return Principal(
            issuer=claims["iss"],
            subject=claims["sub"],
            email=claims.get("email"),
            name=claims.get("name") or claims.get("preferred_username"),
            roles=extract_roles(claims),
        )
