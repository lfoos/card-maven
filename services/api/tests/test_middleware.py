import re

import pytest
from flask import Flask, Response, jsonify, request
from flask.testing import FlaskClient

from card_maven.shared.config import Settings
from card_maven_api.app import create_app
from card_maven_api.auth.tokens import TokenVerifier


class TestRequestId:
    def test_generated_when_absent(self, client: FlaskClient) -> None:
        request_id = client.get("/healthz").headers["X-Request-ID"]
        assert re.fullmatch(r"[0-9a-f]{32}", request_id)

    def test_echoes_safe_caller_id(self, client: FlaskClient) -> None:
        response = client.get("/healthz", headers={"X-Request-ID": "web-abc.123:x"})
        assert response.headers["X-Request-ID"] == "web-abc.123:x"

    @pytest.mark.parametrize("bad", ["has space", "x" * 129, "<script>", "semi;colon"])
    def test_replaces_unsafe_caller_id(self, client: FlaskClient, bad: str) -> None:
        response = client.get("/healthz", headers={"X-Request-ID": bad})
        assert response.headers["X-Request-ID"] != bad
        assert re.fullmatch(r"[0-9a-f]{32}", response.headers["X-Request-ID"])

    def test_included_in_problem_body(self, client: FlaskClient) -> None:
        response = client.get("/nope", headers={"X-Request-ID": "trace-1"})
        assert response.json is not None
        assert response.json["request_id"] == "trace-1"


class TestSecurityHeaders:
    def test_present_on_success_and_error(self, client: FlaskClient) -> None:
        for path in ("/healthz", "/missing"):
            headers = client.get(path).headers
            assert headers["X-Content-Type-Options"] == "nosniff"
            assert headers["X-Frame-Options"] == "DENY"
            assert headers["Cache-Control"] == "no-store"
            assert "default-src 'none'" in headers["Content-Security-Policy"]

    def test_hsts_only_in_production(
        self, client: FlaskClient, settings: Settings, verifier: TokenVerifier
    ) -> None:
        assert "Strict-Transport-Security" not in client.get("/healthz").headers
        prod = settings.model_copy(update={"environment": "prod"})  # skips deploy validators
        prod_client = create_app(prod, token_verifier=verifier).test_client()
        assert "max-age=" in prod_client.get("/healthz").headers["Strict-Transport-Security"]


class TestCors:
    def test_allowed_origin(self, client: FlaskClient) -> None:
        response = client.get("/healthz", headers={"Origin": "http://localhost:5173"})
        assert response.headers["Access-Control-Allow-Origin"] == "http://localhost:5173"
        assert "Origin" in response.headers["Vary"]

    def test_disallowed_origin_gets_no_cors_headers(self, client: FlaskClient) -> None:
        response = client.get("/healthz", headers={"Origin": "https://evil.example"})
        assert "Access-Control-Allow-Origin" not in response.headers

    def test_preflight(self, client: FlaskClient) -> None:
        response = client.options(
            "/healthz",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "Authorization",
            },
        )
        assert response.status_code == 204
        assert "Authorization" in response.headers["Access-Control-Allow-Headers"]
        assert response.headers["Access-Control-Expose-Headers"] == "X-Request-ID"


def test_oversized_body_rejected(app: Flask) -> None:
    @app.post("/_test/echo")
    def echo() -> Response:
        return jsonify(size=len(request.get_data()))

    response = app.test_client().post("/_test/echo", data=b"x" * (1024 * 1024 + 1))
    assert response.status_code == 413
    assert response.content_type == "application/problem+json"
