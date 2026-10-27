import pytest
from flask import Flask
from flask.testing import FlaskClient


def test_liveness_never_touches_dependencies(client: FlaskClient) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json == {"status": "ok"}


def test_readiness_reports_database_outage(client: FlaskClient) -> None:
    response = client.get("/readyz")
    assert response.status_code == 503
    assert response.content_type == "application/problem+json"
    assert response.json is not None
    assert response.json["code"] == "not_ready"
    # No connection string or driver error leaks to the client.
    assert "postgresql" not in response.get_data(as_text=True)


@pytest.mark.db
def test_readiness_ok_with_database(db_app: Flask) -> None:
    response = db_app.test_client().get("/readyz")
    assert response.status_code == 200
    assert response.json == {"status": "ready", "checks": {"database": "ok"}}
