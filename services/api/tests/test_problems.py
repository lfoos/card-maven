import pytest
from flask import Flask
from flask.testing import FlaskClient

from card_maven.shared.errors import (
    DependencyUnavailableError,
    InvalidInputError,
    NotFoundError,
)


@pytest.fixture
def failing_app(app: Flask) -> Flask:
    @app.get("/_test/invalid")
    def invalid() -> None:
        raise InvalidInputError("year must be between 1860 and 2100", field="year")

    @app.get("/_test/missing")
    def missing() -> None:
        raise NotFoundError("card not found")

    @app.get("/_test/dependency")
    def dependency() -> None:
        raise DependencyUnavailableError("kafka at 10.0.0.5:9092 refused the connection")

    @app.get("/_test/crash")
    def crash() -> None:
        raise RuntimeError("secret internal detail")

    return app


def get(app: Flask, path: str) -> tuple[int, dict[str, object], str]:
    response = app.test_client().get(path)
    assert response.content_type == "application/problem+json"
    assert response.json is not None
    return response.status_code, response.json, response.get_data(as_text=True)


def test_domain_error_includes_detail_and_extra(failing_app: Flask) -> None:
    status, body, _ = get(failing_app, "/_test/invalid")
    assert status == 422
    assert body["type"] == "https://cardmaven.app/problems/invalid_input"
    assert body["detail"] == "year must be between 1860 and 2100"
    assert body["field"] == "year"


def test_not_found_error(failing_app: Flask) -> None:
    status, body, _ = get(failing_app, "/_test/missing")
    assert (status, body["code"]) == (404, "not_found")


def test_server_side_errors_hide_detail(failing_app: Flask) -> None:
    status, body, raw = get(failing_app, "/_test/dependency")
    assert status == 503
    assert "10.0.0.5" not in raw
    assert body["title"] == "Dependency unavailable"


def test_unhandled_exception_is_generic_500(failing_app: Flask) -> None:
    status, body, raw = get(failing_app, "/_test/crash")
    assert (status, body["code"]) == (500, "internal_error")
    assert "secret internal detail" not in raw


def test_unknown_route_is_problem(client: FlaskClient) -> None:
    response = client.get("/does-not-exist")
    assert response.status_code == 404
    assert response.json is not None
    assert response.json["code"] == "not_found"


def test_wrong_method_lists_allowed(client: FlaskClient) -> None:
    response = client.delete("/healthz")
    assert response.status_code == 405
    assert "GET" in response.headers["Allow"]
