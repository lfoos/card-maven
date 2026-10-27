from pathlib import Path

import pytest
from click.testing import CliRunner
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from card_maven.catalog.models import Brand, Sport
from card_maven.market.models import TrackedSet
from card_maven.shared.db import session_scope
from card_maven.shared.events import Event
from card_maven.shared.outbox import enqueue
from card_maven_workers import cli as cli_module
from card_maven_workers.cli import cli

REPO_ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CARD_MAVEN_LOG_JSON", "false")
    monkeypatch.setenv("CARD_MAVEN_TRACKED_SETS_PATH", str(REPO_ROOT / "config/tracked_sets.yaml"))
    monkeypatch.setenv(
        "CARD_MAVEN_REFERENCE_DATA_PATH", str(REPO_ROOT / "config/reference_data.yaml")
    )


@pytest.fixture
def db_env(
    env: None,
    database_url: str,
    monkeypatch: pytest.MonkeyPatch,
    committing_session_factory: sessionmaker[Session],
) -> sessionmaker[Session]:
    monkeypatch.setenv("CARD_MAVEN_DATABASE_URL", database_url)
    return committing_session_factory


def count(factory: sessionmaker[Session], model: type) -> int:
    with session_scope(factory) as session:
        return session.scalar(select(func.count()).select_from(model)) or 0


class TestCheckConfig:
    def test_repository_config_passes(self, env: None) -> None:
        result = CliRunner().invoke(cli, ["check-config"])
        assert result.exit_code == 0, result.output
        assert "config ok: 39 tracked set-years across 4 sports" in result.output

    def test_unknown_brand_fails(
        self, env: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        config = tmp_path / "sets.yaml"
        config.write_text(
            "defaults:\n  years: {from: 2025, to: 2025}\nsets:\n"
            "  - {sport: baseball, brand: Leaf, name: Metal}\n"
        )
        monkeypatch.setenv("CARD_MAVEN_TRACKED_SETS_PATH", str(config))
        result = CliRunner().invoke(cli, ["check-config"])
        assert result.exit_code == 1
        assert "brand:leaf" in result.output

    def test_invalid_file_fails(
        self, env: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        config = tmp_path / "sets.yaml"
        config.write_text("defaults: [")
        monkeypatch.setenv("CARD_MAVEN_TRACKED_SETS_PATH", str(config))
        result = CliRunner().invoke(cli, ["check-config"])
        assert result.exit_code == 1
        assert "not valid YAML" in result.output


@pytest.mark.db
class TestDatabaseCommands:
    def test_seed_is_idempotent(self, db_env: sessionmaker[Session]) -> None:
        for _ in range(2):
            result = CliRunner().invoke(cli, ["seed"])
            assert result.exit_code == 0, result.output
        assert count(db_env, Sport) == 4
        assert count(db_env, Brand) == 4

    def test_sync_requires_seed(self, db_env: sessionmaker[Session]) -> None:
        result = CliRunner().invoke(cli, ["sync-tracked-sets"])
        assert result.exit_code == 1
        assert "unknown catalog entries" in result.output

    def test_dry_run_then_sync(self, db_env: sessionmaker[Session]) -> None:
        CliRunner().invoke(cli, ["seed"])
        dry = CliRunner().invoke(cli, ["sync-tracked-sets", "--dry-run"])
        assert dry.exit_code == 0, dry.output
        assert "dry run" in dry.output
        assert "created=39" in dry.output
        assert count(db_env, TrackedSet) == 0

        real = CliRunner().invoke(cli, ["sync-tracked-sets"])
        assert "created=39" in real.output
        assert count(db_env, TrackedSet) == 39
        again = CliRunner().invoke(cli, ["sync-tracked-sets"])
        assert "unchanged=39" in again.output

    def test_sync_with_override_file(self, db_env: sessionmaker[Session], tmp_path: Path) -> None:
        CliRunner().invoke(cli, ["seed"])
        config = tmp_path / "sets.yaml"
        config.write_text(
            "defaults:\n  years: {from: 2020, to: 2021}\nsets:\n"
            "  - {sport: hockey, brand: Upper Deck, name: Series 1}\n"
        )
        result = CliRunner().invoke(cli, ["sync-tracked-sets", "--config", str(config)])
        assert "created=2" in result.output

    def test_outbox_relay_once(
        self, db_env: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from card_maven.shared.events import InMemoryPublisher

        publisher = InMemoryPublisher()
        monkeypatch.setattr(cli_module, "KafkaPublisher", lambda *_a, **_k: publisher)
        with session_scope(db_env) as session:
            enqueue(session, Event(type="market.sync.requested.v1", source="test"))
        result = CliRunner().invoke(cli, ["outbox-relay", "--once"])
        assert result.exit_code == 0, result.output
        assert "published=1 failed=0" in result.output
        assert len(publisher.sent) == 1

    def test_outbox_relay_loop_stops_on_signal(
        self, db_env: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from card_maven.shared.events import InMemoryPublisher

        monkeypatch.setattr(cli_module, "KafkaPublisher", lambda *_a, **_k: InMemoryPublisher())
        calls: list[dict[str, object]] = []

        def fake_run_relay(relay: object, **kwargs: object) -> int:
            calls.append(kwargs)
            return 0

        monkeypatch.setattr(cli_module, "run_relay", fake_run_relay)
        result = CliRunner().invoke(cli, ["outbox-relay"])
        assert result.exit_code == 0, result.output
        assert calls[0]["poll_interval_seconds"] == 1.0
