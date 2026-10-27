"""Typed application settings, loaded from ``CARD_MAVEN_*`` environment variables."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["local", "test", "dev", "prod"]
DEPLOYED_ENVIRONMENTS = frozenset({"dev", "prod"})
_LOCAL_DATABASE_URL = "postgresql+psycopg://card_maven:card_maven@localhost:5432/card_maven"


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

    tracked_sets_path: Path = Path("config/tracked_sets.yaml")
    reference_data_path: Path = Path("config/reference_data.yaml")

    outbox_batch_size: int = Field(default=100, ge=1, le=1000)
    outbox_poll_interval_seconds: float = Field(default=1.0, gt=0)

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
        return self

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
