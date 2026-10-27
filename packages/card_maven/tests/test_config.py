import pytest

from card_maven.shared.config import Settings, get_settings


def test_defaults_target_local_stack() -> None:
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.environment == "local"
    assert "localhost:5432" in settings.database_url.get_secret_value()
    assert not settings.is_production


DEPLOYED = {
    "CARD_MAVEN_DATABASE_URL": "postgresql+psycopg://app:s3cret@db.internal:5432/card_maven",
    "CARD_MAVEN_S3_ENDPOINT_URL": "",
    "CARD_MAVEN_S3_ACCESS_KEY_ID": "",
    "CARD_MAVEN_S3_SECRET_ACCESS_KEY": "",
    "CARD_MAVEN_OIDC_ISSUER": "https://auth.cardmaven.app",
    "CARD_MAVEN_OIDC_JWKS_URL": "https://auth.cardmaven.app/.well-known/jwks.json",
}


def test_reads_prefixed_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in DEPLOYED.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("CARD_MAVEN_ENVIRONMENT", "prod")
    monkeypatch.setenv("CARD_MAVEN_CORS_ORIGINS", '["https://cardmaven.app"]')
    monkeypatch.setenv("CARD_MAVEN_OUTBOX_BATCH_SIZE", "25")
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.is_production
    assert settings.cors_origins == ["https://cardmaven.app"]
    assert settings.outbox_batch_size == 25


def test_database_url_is_not_leaked_in_repr() -> None:
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert "card_maven:card_maven" not in repr(settings)


def test_rejects_invalid_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CARD_MAVEN_ENVIRONMENT", "staging")
    with pytest.raises(ValueError, match="environment"):
        Settings(_env_file=None)  # type: ignore[call-arg]


def test_get_settings_is_cached() -> None:
    get_settings.cache_clear()
    assert get_settings() is get_settings()
    get_settings.cache_clear()


class TestDeploymentGuards:
    """Security: settings that are only safe locally are rejected when deployed."""

    @pytest.fixture(autouse=True)
    def deployed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for name, value in DEPLOYED.items():
            monkeypatch.setenv(name, value)
        monkeypatch.setenv("CARD_MAVEN_ENVIRONMENT", "dev")

    def test_valid_deployed_settings(self) -> None:
        assert Settings(_env_file=None).is_deployed  # type: ignore[call-arg]

    def test_rejects_local_database_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("CARD_MAVEN_DATABASE_URL")
        with pytest.raises(ValueError, match="database_url"):
            Settings(_env_file=None)  # type: ignore[call-arg]

    @pytest.mark.parametrize("name", ["CARD_MAVEN_OIDC_ISSUER", "CARD_MAVEN_OIDC_JWKS_URL"])
    def test_rejects_plain_http_identity_provider(
        self, monkeypatch: pytest.MonkeyPatch, name: str
    ) -> None:
        monkeypatch.setenv(name, "http://auth.cardmaven.app/x")
        with pytest.raises(ValueError, match="https"):
            Settings(_env_file=None)  # type: ignore[call-arg]

    def test_rejects_wildcard_cors_everywhere(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CARD_MAVEN_ENVIRONMENT", "local")
        monkeypatch.setenv("CARD_MAVEN_CORS_ORIGINS", '["*"]')
        with pytest.raises(ValueError, match="explicit origins"):
            Settings(_env_file=None)  # type: ignore[call-arg]


class TestStorageDeploymentGuards:
    @pytest.fixture(autouse=True)
    def deployed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for name, value in DEPLOYED.items():
            monkeypatch.setenv(name, value)
        monkeypatch.setenv("CARD_MAVEN_ENVIRONMENT", "prod")

    def test_iam_role_settings_accepted(self) -> None:
        settings = Settings(_env_file=None)  # type: ignore[call-arg]
        assert settings.s3_endpoint_url is None
        assert settings.s3_access_key_id is None

    @pytest.mark.parametrize(
        ("name", "value"),
        [
            ("CARD_MAVEN_S3_ENDPOINT_URL", "http://localhost:8333"),
            ("CARD_MAVEN_S3_ACCESS_KEY_ID", "card-maven-local"),
        ],
    )
    def test_local_storage_defaults_rejected(
        self, monkeypatch: pytest.MonkeyPatch, name: str, value: str
    ) -> None:
        monkeypatch.setenv(name, value)
        with pytest.raises(ValueError, match="IAM role"):
            Settings(_env_file=None)  # type: ignore[call-arg]
