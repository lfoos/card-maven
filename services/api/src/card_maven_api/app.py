"""Application factory."""

from __future__ import annotations

from flask import Flask
from sqlalchemy.orm import Session, sessionmaker

from card_maven.shared.config import Settings, get_settings
from card_maven.shared.db import make_engine, make_session_factory
from card_maven.shared.logging import configure_logging
from card_maven_api.auth.tokens import TokenVerifier
from card_maven_api.extensions import EXTENSION_KEY, ApiContext
from card_maven_api.health.routes import bp as health_bp
from card_maven_api.middleware import register_middleware
from card_maven_api.problems import register_problem_handlers

MAX_REQUEST_BYTES = 1 * 1024 * 1024  # JSON only; images go straight to object storage


def create_app(
    settings: Settings | None = None,
    *,
    session_factory: sessionmaker[Session] | None = None,
    token_verifier: TokenVerifier | None = None,
) -> Flask:
    """Build the API. Dependencies can be injected for tests."""
    settings = settings or get_settings()
    configure_logging(settings.log_level, json=settings.log_json)

    app = Flask(__name__)
    app.config.update(MAX_CONTENT_LENGTH=MAX_REQUEST_BYTES, JSON_SORT_KEYS=False)

    if session_factory is None:
        session_factory = make_session_factory(
            make_engine(settings.database_url.get_secret_value())
        )
    if token_verifier is None:
        token_verifier = TokenVerifier.from_jwks_url(
            issuer=settings.oidc_issuer,
            audience=settings.oidc_audience,
            jwks_url=settings.oidc_jwks_url,
        )
    app.extensions[EXTENSION_KEY] = ApiContext(
        settings=settings, session_factory=session_factory, token_verifier=token_verifier
    )

    register_middleware(app, cors_origins=settings.cors_origins, hsts=settings.is_production)
    register_problem_handlers(app)
    app.register_blueprint(health_bp)
    # Feature blueprints mount under /api/v1 from Phase 1 onwards.
    return app
