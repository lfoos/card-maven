from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from flask import Flask
from flask.testing import FlaskClient
from sqlalchemy import Engine
from sqlalchemy.orm import sessionmaker

from card_maven.shared.config import Settings
from card_maven.shared.db import make_engine, make_session_factory
from card_maven_api.app import create_app
from card_maven_api.auth.tokens import TokenVerifier

ISSUER = "https://idp.test/realms/card-maven"
AUDIENCE = "card-maven-api"
KID = "test-key"


class StaticKeys:
    """Stands in for PyJWKClient: serves one known key, rejects unknown kids."""

    def __init__(self, public_key: Any, kid: str = KID) -> None:
        self._key = jwt.PyJWK.from_dict(
            {
                **jwt.algorithms.RSAAlgorithm.to_jwk(public_key, as_dict=True),
                "kid": kid,
                "alg": "RS256",
            }
        )
        self._kid = kid

    def get_signing_key_from_jwt(self, token: str) -> jwt.PyJWK:
        kid = jwt.get_unverified_header(token).get("kid")
        if kid != self._kid:
            raise jwt.PyJWKClientError(f"Unable to find a signing key that matches: {kid}")
        return self._key


@pytest.fixture(scope="session")
def private_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture(scope="session")
def other_private_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def verifier(private_key: rsa.RSAPrivateKey) -> TokenVerifier:
    return TokenVerifier(
        issuer=ISSUER, audience=AUDIENCE, keys=StaticKeys(private_key.public_key())
    )


TokenFactory = Callable[..., str]


@pytest.fixture
def make_token(private_key: rsa.RSAPrivateKey) -> TokenFactory:
    def factory(*, key: Any = None, kid: str = KID, algorithm: str = "RS256", **claims: Any) -> str:
        now = int(time.time())
        payload: dict[str, Any] = {
            "iss": ISSUER,
            "aud": AUDIENCE,
            "sub": "user-123",
            "iat": now,
            "exp": now + 300,
            "email": "collector@example.com",
        }
        payload.update(claims)
        payload = {k: v for k, v in payload.items() if v is not None}
        return jwt.encode(payload, key or private_key, algorithm=algorithm, headers={"kid": kid})

    return factory


@pytest.fixture
def settings() -> Settings:
    return Settings(  # type: ignore[call-arg]
        _env_file=None,
        environment="test",
        log_json=True,
        cors_origins=["http://localhost:5173"],
        oidc_issuer=ISSUER,
        oidc_audience=AUDIENCE,
    )


@pytest.fixture
def unreachable_session_factory() -> sessionmaker:  # type: ignore[type-arg]
    # Port 1 refuses connections immediately, simulating a database outage.
    engine = make_engine(
        "postgresql+psycopg://nobody:nothing@127.0.0.1:1/none", connect_args={"connect_timeout": 1}
    )
    return make_session_factory(engine)


@pytest.fixture
def app(
    settings: Settings,
    verifier: TokenVerifier,
    unreachable_session_factory: sessionmaker,  # type: ignore[type-arg]
) -> Flask:
    """An app with no working database; tests that need one use ``db_app``."""
    return create_app(
        settings, session_factory=unreachable_session_factory, token_verifier=verifier
    )


@pytest.fixture
def client(app: Flask) -> FlaskClient:
    return app.test_client()


@pytest.fixture
def db_app(settings: Settings, verifier: TokenVerifier, engine: Engine) -> Flask:
    return create_app(
        settings, session_factory=make_session_factory(engine), token_verifier=verifier
    )
