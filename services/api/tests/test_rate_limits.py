from collections.abc import Callable

import pytest
from flask import Flask

from card_maven.shared.config import Settings
from card_maven.shared.storage.memory import InMemoryObjectStore
from card_maven_api.app import create_app
from card_maven_api.auth.tokens import TokenVerifier

Auth = Callable[..., dict[str, str]]
SETS = "/api/v1/catalog/sets?q=chrome"


@pytest.fixture
def limited_app(
    settings: Settings, verifier: TokenVerifier, unreachable_session_factory: object
) -> Flask:
    app = create_app(
        settings.model_copy(update={"rate_limits_enabled": True, "rate_limit_default": "3/minute"}),
        session_factory=unreachable_session_factory,  # type: ignore[arg-type]
        token_verifier=verifier,
        object_store=InMemoryObjectStore(),
    )
    return app


def test_limit_exceeded_is_429_problem_with_retry_after(limited_app: Flask) -> None:
    client = limited_app.test_client()
    statuses = [client.get(SETS).status_code for _ in range(4)]
    assert statuses == [401, 401, 401, 429]
    response = client.get(SETS)
    assert response.content_type == "application/problem+json"
    assert response.json is not None
    assert response.json["code"] == "too_many_requests"
    assert int(response.headers["Retry-After"]) > 0
    assert response.headers["X-RateLimit-Limit"] == "3"


def test_users_are_limited_separately_from_each_other_and_from_ip(
    limited_app: Flask, auth: Auth
) -> None:
    client = limited_app.test_client()
    # No `q`, so these fail validation (422) before touching the database.
    for _ in range(3):
        client.get("/api/v1/catalog/sets", headers=auth("alice"))
    assert client.get("/api/v1/catalog/sets", headers=auth("alice")).status_code == 429
    assert client.get("/api/v1/catalog/sets", headers=auth("bob")).status_code == 422
    assert client.get(SETS).status_code == 401  # anonymous, keyed by IP


def test_health_probes_are_never_limited(limited_app: Flask) -> None:
    client = limited_app.test_client()
    assert all(client.get("/healthz").status_code == 200 for _ in range(10))


def test_forwarded_for_trusted_only_when_configured(
    settings: Settings, verifier: TokenVerifier, unreachable_session_factory: object
) -> None:
    def make(proxies: int) -> Flask:
        return create_app(
            settings.model_copy(
                update={
                    "rate_limits_enabled": True,
                    "rate_limit_default": "1/minute",
                    "trusted_proxy_count": proxies,
                }
            ),
            session_factory=unreachable_session_factory,  # type: ignore[arg-type]
            token_verifier=verifier,
            object_store=InMemoryObjectStore(),
        )

    behind_alb = make(1)
    client = behind_alb.test_client()
    assert client.get(SETS, headers={"X-Forwarded-For": "1.1.1.1"}).status_code == 401
    assert (
        client.get(SETS, headers={"X-Forwarded-For": "2.2.2.2"}).status_code == 401
    )  # distinct client
    assert client.get(SETS, headers={"X-Forwarded-For": "1.1.1.1"}).status_code == 429

    direct = make(0)
    client = direct.test_client()
    client.get(SETS, headers={"X-Forwarded-For": "3.3.3.3"})
    # Spoofed header is ignored: same socket address, so the same bucket.
    assert client.get(SETS, headers={"X-Forwarded-For": "4.4.4.4"}).status_code == 429


def test_route_specific_limit_and_reset(limited_app: Flask) -> None:
    from card_maven_api.rate_limits import reset_rate_limits

    client = limited_app.test_client()
    for _ in range(3):
        client.get(SETS)
    assert client.get(SETS).status_code == 429
    with limited_app.app_context():
        reset_rate_limits()
    assert client.get(SETS).status_code == 401


def test_write_routes_carry_their_own_limit(limited_app: Flask) -> None:
    view = limited_app.view_functions["collection.create_item"]
    assert view.__wrapped__ is not None  # wrapped by the limiter


def test_comps_refresh_has_its_own_tighter_limit(
    settings: Settings, verifier: TokenVerifier, unreachable_session_factory: object
) -> None:
    app = create_app(
        settings.model_copy(
            update={"rate_limits_enabled": True, "rate_limit_default": "100/minute"}
        ),
        session_factory=unreachable_session_factory,  # type: ignore[arg-type]
        token_verifier=verifier,
        object_store=InMemoryObjectStore(),
    )
    client = app.test_client()
    url = "/api/v1/collection/items/00000000-0000-0000-0000-000000000001/comps/refresh"
    statuses = [client.post(url).status_code for _ in range(11)]
    assert statuses == [401] * 10 + [429]
