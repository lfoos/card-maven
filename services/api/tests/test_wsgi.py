import importlib

import pytest


def test_wsgi_module_builds_app_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    from card_maven.shared.config import get_settings

    monkeypatch.setenv("CARD_MAVEN_ENVIRONMENT", "test")
    get_settings.cache_clear()
    try:
        module = importlib.import_module("card_maven_api.wsgi")
        response = module.app.test_client().get("/healthz")
        assert response.status_code == 200
    finally:
        get_settings.cache_clear()


def test_request_id_does_not_leak_into_later_logs() -> None:
    import structlog

    from card_maven.shared.config import Settings
    from card_maven_api.app import create_app

    app = create_app(Settings(_env_file=None, environment="test"))  # type: ignore[call-arg]
    app.test_client().get("/healthz", headers={"X-Request-ID": "req-leak-check"})
    assert "request_id" not in structlog.contextvars.get_contextvars()
