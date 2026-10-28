"""Application factory."""

from __future__ import annotations

from flask_openapi3.openapi import OpenAPI
from pydantic import ValidationError
from sqlalchemy.orm import Session, sessionmaker
from werkzeug.middleware.proxy_fix import ProxyFix

import card_maven.models  # noqa: F401  (registers every table, for cross-context foreign keys)
from card_maven.shared.config import Settings, get_settings
from card_maven.shared.db import make_engine, make_session_factory
from card_maven.shared.logging import configure_logging
from card_maven.shared.storage import ObjectStore
from card_maven.shared.storage.s3 import S3ObjectStore
from card_maven_api.auth.decorators import authenticate_request
from card_maven_api.auth.tokens import TokenVerifier
from card_maven_api.catalog.routes import bp as catalog_bp
from card_maven_api.collection.routes import bp as collection_bp
from card_maven_api.extensions import EXTENSION_KEY, ApiContext
from card_maven_api.health.routes import bp as health_bp
from card_maven_api.identity.routes import bp as identity_bp
from card_maven_api.market.routes import bp as market_bp
from card_maven_api.middleware import register_middleware
from card_maven_api.openapi import INFO, SECURITY_SCHEMES
from card_maven_api.problems import register_problem_handlers, validation_problem
from card_maven_api.rate_limits import init_rate_limits
from card_maven_api.schemas import ValidationProblemOut

MAX_REQUEST_BYTES = 1 * 1024 * 1024  # JSON only; images go straight to object storage


def create_app(
    settings: Settings | None = None,
    *,
    session_factory: sessionmaker[Session] | None = None,
    token_verifier: TokenVerifier | None = None,
    object_store: ObjectStore | None = None,
) -> OpenAPI:
    """Build the API. Dependencies can be injected for tests."""
    settings = settings or get_settings()
    configure_logging(settings.log_level, json=settings.log_json)

    app = OpenAPI(
        __name__,
        info=INFO,
        security_schemes=SECURITY_SCHEMES,
        validation_error_status=422,
        validation_error_callback=validation_problem,
        validation_error_model=ValidationProblemOut,
        doc_ui=False,  # the spec is served at /api/v1/openapi.json (below)
    )
    app.config.update(MAX_CONTENT_LENGTH=MAX_REQUEST_BYTES, JSON_SORT_KEYS=False)
    if settings.trusted_proxy_count:
        # Behind a load balancer: trust exactly that many X-Forwarded-* hops, so
        # client IPs (used for rate limiting) can't be spoofed.
        app.wsgi_app = ProxyFix(  # type: ignore[method-assign]
            app.wsgi_app,
            x_for=settings.trusted_proxy_count,
            x_proto=settings.trusted_proxy_count,
            x_host=settings.trusted_proxy_count,
        )

    app.extensions[EXTENSION_KEY] = ApiContext(
        settings=settings,
        session_factory=session_factory
        or make_session_factory(make_engine(settings.database_url.get_secret_value())),
        token_verifier=token_verifier
        or TokenVerifier.from_jwks_url(
            issuer=settings.oidc_issuer,
            audience=settings.oidc_audience,
            jwks_url=settings.oidc_jwks_url,
        ),
        object_store=object_store or S3ObjectStore.from_settings(settings),
    )

    register_middleware(app, cors_origins=settings.cors_origins, hsts=settings.is_production)
    app.before_request(authenticate_request)  # before the rate limiter: limits key on the user
    register_problem_handlers(app)
    app.register_error_handler(ValidationError, validation_problem)

    app.register_blueprint(health_bp)
    app.add_url_rule("/api/v1/openapi.json", "openapi_spec", lambda: app.api_doc)
    app.register_api(identity_bp)
    app.register_api(catalog_bp)
    app.register_api(collection_bp)
    app.register_api(market_bp)
    init_rate_limits(app, settings)
    return app
