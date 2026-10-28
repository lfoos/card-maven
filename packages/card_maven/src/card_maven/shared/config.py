"""Typed application settings, loaded from ``CARD_MAVEN_*`` environment variables."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["local", "test", "dev", "prod"]
DEPLOYED_ENVIRONMENTS = frozenset({"dev", "prod"})
_LOCAL_DATABASE_URL = "postgresql+psycopg://card_maven:card_maven@localhost:5432/card_maven"
_LOCAL_S3_ENDPOINT = "http://localhost:8333"
_LOCAL_S3_KEY_ID = "card-maven-local"


class Settings(BaseSettings):
    """All runtime configuration. Defaults target the local Docker Compose stack."""

    model_config = SettingsConfigDict(
        env_prefix="CARD_MAVEN_", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    environment: Environment = "local"
    log_level: str = "INFO"
    log_json: bool = True

    database_url: SecretStr = SecretStr(_LOCAL_DATABASE_URL)

    kafka_bootstrap_servers: str = "localhost:9092"

    oidc_issuer: str = "http://localhost:8080/realms/card-maven"
    oidc_audience: str = "card-maven-api"
    oidc_jwks_url: str = "http://localhost:8080/realms/card-maven/protocol/openid-connect/certs"

    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    # Object storage. Locally: SeaweedFS from the compose stack. On AWS: S3 with
    # IAM role credentials (leave the endpoint and keys unset).
    s3_bucket: str = "card-maven-media"
    s3_region: str = "us-east-1"
    s3_endpoint_url: str | None = _LOCAL_S3_ENDPOINT
    s3_public_endpoint_url: str | None = None
    s3_access_key_id: SecretStr | None = SecretStr(_LOCAL_S3_KEY_ID)
    s3_secret_access_key: SecretStr | None = SecretStr("card-maven-local-secret")

    # Rate limiting (Flask-Limiter storage). memory:// is per-process; use a
    # shared store (e.g. redis://) when running more than one API replica.
    rate_limit_storage_uri: str = "memory://"
    rate_limit_default: str = "300/minute"
    rate_limits_enabled: bool = True
    # X-Forwarded-* hops to trust (1 behind an ALB). 0 trusts none.
    trusted_proxy_count: int = Field(default=0, ge=0, le=5)

    # Market data. Sources are enabled here; their licenses live in reference data.
    market_sources: list[str] = Field(default_factory=lambda: ["fixture", "ebay_browse"])
    market_fixtures_path: Path = Path("config/market_fixtures.yaml")
    ebay_environment: Literal["sandbox", "production"] = "sandbox"
    ebay_client_id: SecretStr | None = None
    ebay_client_secret: SecretStr | None = None
    ebay_campaign_id: str | None = None  # eBay Partner Network, for affiliate links
    ebay_marketplace_id: str = "EBAY_US"
    ebay_category_id: str = "261328"  # Sports Trading Card Singles

    tracked_sets_path: Path = Path("config/tracked_sets.yaml")
    reference_data_path: Path = Path("config/reference_data.yaml")

    outbox_batch_size: int = Field(default=100, ge=1, le=1000)
    outbox_poll_interval_seconds: float = Field(default=1.0, gt=0)

    @field_validator(
        "s3_endpoint_url",
        "s3_public_endpoint_url",
        "s3_access_key_id",
        "s3_secret_access_key",
        "ebay_client_id",
        "ebay_client_secret",
        "ebay_campaign_id",
        mode="before",
    )
    @classmethod
    def _empty_means_unset(cls, value: object) -> object:
        # An empty env var (CARD_MAVEN_S3_ENDPOINT_URL=) means "use the AWS default".
        return None if value == "" else value

    @model_validator(mode="after")
    def _safe_for_deployment(self) -> Settings:
        """Fail at startup, not in production, on settings that are only safe locally."""
        if "*" in self.cors_origins:
            raise ValueError("cors_origins must list explicit origins, not '*'")
        if self.environment in DEPLOYED_ENVIRONMENTS:
            if self.database_url.get_secret_value() == _LOCAL_DATABASE_URL:
                raise ValueError("database_url must be set explicitly outside local/test")
            for name in ("oidc_issuer", "oidc_jwks_url"):
                if not getattr(self, name).startswith("https://"):
                    raise ValueError(f"{name} must use https outside local/test")
            if "fixture" in self.market_sources:
                raise ValueError(
                    "the fixture market source is sample data; disable it outside local/test"
                )
            key_id = self.s3_access_key_id
            if self.s3_endpoint_url == _LOCAL_S3_ENDPOINT or (
                key_id is not None and key_id.get_secret_value() == _LOCAL_S3_KEY_ID
            ):
                raise ValueError(
                    "s3 settings are the local defaults; on AWS leave the endpoint and keys "
                    "unset so the IAM role is used"
                )
        return self

    @property
    def ebay_configured(self) -> bool:
        return self.ebay_client_id is not None and self.ebay_client_secret is not None

    @property
    def is_deployed(self) -> bool:
        return self.environment in DEPLOYED_ENVIRONMENTS

    @property
    def is_production(self) -> bool:
        return self.environment == "prod"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Process-wide settings singleton. Tests construct ``Settings`` directly instead."""
    return Settings()
