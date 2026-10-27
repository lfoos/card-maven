import time
from collections.abc import Callable
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from flask import Flask, Response, jsonify
from flask.testing import FlaskClient

from card_maven.shared.errors import AuthenticationError, DependencyUnavailableError
from card_maven_api.auth.decorators import current_principal, require_auth
from card_maven_api.auth.tokens import Principal, TokenVerifier, extract_roles

TokenFactory = Callable[..., str]


class TestTokenVerifier:
    def test_valid_token(self, verifier: TokenVerifier, make_token: TokenFactory) -> None:
        principal = verifier.verify(make_token(name="Logan", realm_access={"roles": ["collector"]}))
        assert principal == Principal(
            issuer="https://idp.test/realms/card-maven",
            subject="user-123",
            email="collector@example.com",
            name="Logan",
            roles=frozenset({"collector"}),
        )

    def test_name_falls_back_to_preferred_username(
        self, verifier: TokenVerifier, make_token: TokenFactory
    ) -> None:
        assert verifier.verify(make_token(preferred_username="lfoos")).name == "lfoos"

    def test_clock_skew_within_leeway_is_tolerated(
        self, verifier: TokenVerifier, make_token: TokenFactory
    ) -> None:
        verifier.verify(make_token(exp=int(time.time()) - 10))

    @pytest.mark.parametrize(
        ("claims", "message"),
        [
            ({"exp": int(time.time()) - 120}, "expired"),
            ({"aud": "some-other-api"}, "invalid"),
            ({"iss": "https://evil.example"}, "invalid"),
            ({"sub": None}, "invalid"),
            ({"iat": None}, "invalid"),
            ({"nbf": int(time.time()) + 600}, "invalid"),
        ],
    )
    def test_rejects_bad_claims(
        self,
        verifier: TokenVerifier,
        make_token: TokenFactory,
        claims: dict[str, Any],
        message: str,
    ) -> None:
        with pytest.raises(AuthenticationError, match=message):
            verifier.verify(make_token(**claims))

    def test_rejects_token_signed_by_another_key(
        self,
        verifier: TokenVerifier,
        make_token: TokenFactory,
        other_private_key: rsa.RSAPrivateKey,
    ) -> None:
        with pytest.raises(AuthenticationError, match="invalid"):
            verifier.verify(make_token(key=other_private_key))

    def test_rejects_unknown_key_id(
        self, verifier: TokenVerifier, make_token: TokenFactory
    ) -> None:
        with pytest.raises(AuthenticationError, match="not recognized"):
            verifier.verify(make_token(kid="rotated-away"))

    def test_rejects_hmac_algorithm_confusion(self, verifier: TokenVerifier) -> None:
        forged = jwt.encode(
            {"iss": "x", "sub": "y"},
            "a-shared-secret-that-is-long-enough-for-hs256",
            algorithm="HS256",
            headers={"kid": "test-key"},
        )
        with pytest.raises(AuthenticationError):
            verifier.verify(forged)

    def test_rejects_unsigned_token(self, verifier: TokenVerifier) -> None:
        unsigned = jwt.encode({"sub": "y"}, None, algorithm="none", headers={"kid": "test-key"})
        with pytest.raises(AuthenticationError):
            verifier.verify(unsigned)

    @pytest.mark.parametrize("garbage", ["", "not-a-jwt", "a.b.c"])
    def test_rejects_malformed(self, verifier: TokenVerifier, garbage: str) -> None:
        with pytest.raises(AuthenticationError):
            verifier.verify(garbage)

    def test_key_endpoint_outage_is_a_dependency_error(self, make_token: TokenFactory) -> None:
        class Down:
            def get_signing_key_from_jwt(self, token: str) -> jwt.PyJWK:
                raise jwt.PyJWKClientConnectionError("connection refused")

        verifier = TokenVerifier(issuer="i", audience="a", keys=Down())
        with pytest.raises(DependencyUnavailableError):
            verifier.verify(make_token())

    def test_from_jwks_url_builds_caching_client(self) -> None:
        verifier = TokenVerifier.from_jwks_url(
            issuer="i", audience="a", jwks_url="https://idp.test/certs"
        )
        assert isinstance(verifier._keys, jwt.PyJWKClient)

    def test_es256_supported(self, make_token: TokenFactory) -> None:
        key = ec.generate_private_key(ec.SECP256R1())

        class EcKeys:
            def get_signing_key_from_jwt(self, token: str) -> jwt.PyJWK:
                jwk = jwt.algorithms.ECAlgorithm.to_jwk(key.public_key(), as_dict=True)
                return jwt.PyJWK.from_dict({**jwk, "alg": "ES256"})

        verifier = TokenVerifier(
            issuer="https://idp.test/realms/card-maven", audience="card-maven-api", keys=EcKeys()
        )
        assert verifier.verify(make_token(key=key, algorithm="ES256")).subject == "user-123"


@pytest.mark.parametrize(
    ("claims", "roles"),
    [
        ({"roles": ["admin"]}, {"admin"}),
        ({"realm_access": {"roles": ["collector", "admin"]}}, {"collector", "admin"}),
        ({"cognito:groups": ["collector"]}, {"collector"}),
        ({"roles": "admin"}, set()),  # a bare string is not a role list
        ({"realm_access": None}, set()),
        ({}, set()),
    ],
)
def test_extract_roles(claims: dict[str, Any], roles: set[str]) -> None:
    assert extract_roles(claims) == roles


class TestRequireAuth:
    @pytest.fixture
    def protected(self, app: Flask) -> FlaskClient:
        @app.get("/_test/me")
        @require_auth()
        def me() -> Response:
            return jsonify(subject=current_principal().subject)

        @app.get("/_test/admin")
        @require_auth(role="admin")
        def admin() -> Response:
            return jsonify(ok=True)

        return app.test_client()

    def test_valid_bearer(self, protected: FlaskClient, make_token: TokenFactory) -> None:
        response = protected.get("/_test/me", headers={"Authorization": f"Bearer {make_token()}"})
        assert response.status_code == 200
        assert response.json == {"subject": "user-123"}

    @pytest.mark.parametrize(
        "header", [None, "", "Bearer", "Bearer   ", "Basic dXNlcjpwYXNz", "Token abc"]
    )
    def test_missing_or_wrong_scheme(self, protected: FlaskClient, header: str | None) -> None:
        headers = {} if header is None else {"Authorization": header}
        response = protected.get("/_test/me", headers=headers)
        assert response.status_code == 401
        assert response.json is not None
        assert response.json["code"] == "unauthenticated"

    def test_invalid_token(self, protected: FlaskClient) -> None:
        response = protected.get("/_test/me", headers={"Authorization": "Bearer nope"})
        assert response.status_code == 401

    def test_role_required(self, protected: FlaskClient, make_token: TokenFactory) -> None:
        collector = make_token(realm_access={"roles": ["collector"]})
        admin = make_token(realm_access={"roles": ["admin"]})
        assert (
            protected.get(
                "/_test/admin", headers={"Authorization": f"Bearer {collector}"}
            ).status_code
            == 403
        )
        assert (
            protected.get("/_test/admin", headers={"Authorization": f"Bearer {admin}"}).status_code
            == 200
        )

    def test_current_principal_outside_auth(self, app: Flask) -> None:
        with app.test_request_context(), pytest.raises(AuthenticationError):
            current_principal()
