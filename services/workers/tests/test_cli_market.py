import threading
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from card_maven.collection.maintenance import SweepResult
from card_maven.market.models import CatalogTerm, MarketSyncJob, Sale
from card_maven.market.sources.port import MarketQuery, MarketRecord
from card_maven.shared.db import session_scope
from card_maven.shared.errors import DependencyUnavailableError
from card_maven.shared.events import InMemoryPublisher
from card_maven.shared.money import Money
from card_maven.shared.storage.memory import InMemoryObjectStore
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


def run(*args: str) -> Any:
    return CliRunner().invoke(cli, list(args))


def count(factory: sessionmaker[Session], model: type) -> int:
    with session_scope(factory) as session:
        return session.scalar(select(func.count()).select_from(model)) or 0


@pytest.mark.db
class TestScheduledCommands:
    def test_nightly_sync_queues_one_job_per_tracked_set(
        self, db_env: sessionmaker[Session]
    ) -> None:
        assert run("seed").exit_code == 0
        assert run("sync-tracked-sets").exit_code == 0
        result = run("request-market-sync")
        assert result.exit_code == 0, result.output
        assert "queued 39 tracked-set sync jobs" in result.output
        assert count(db_env, MarketSyncJob) == 39

    def test_run_now_ingests_without_kafka(self, db_env: sessionmaker[Session]) -> None:
        assert run("seed").exit_code == 0
        assert run("sync-tracked-sets").exit_code == 0
        result = run("request-market-sync", "--run-now")
        assert result.exit_code == 0, result.output
        assert "ran 39 jobs" in result.output
        with session_scope(db_env) as session:
            statuses = set(session.scalars(select(MarketSyncJob.status)))
            stored = session.scalar(select(func.count()).select_from(Sale)) or 0
        assert statuses == {"succeeded"}
        assert stored > 0  # sample sales from the fixture source

    def test_purge_on_an_empty_database(self, db_env: sessionmaker[Session]) -> None:
        result = run("purge-market-data")
        assert result.exit_code == 0, result.output
        assert "purged listings=0 jobs=0 processed_events=0" in result.output


class FlakyStore(InMemoryObjectStore):
    def delete(self, key: str) -> None:
        if key.endswith("bad"):
            raise DependencyUnavailableError("storage down")
        super().delete(key)


def test_sweep_deletes_objects_and_counts_orphans(
    env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = FlakyStore()
    store.put("users/u/items/i/good", b"x", "image/jpeg")
    monkeypatch.setattr(cli_module, "session_scope", _null_scope)
    monkeypatch.setattr(cli_module.Context, "session_factory", lambda self: None)
    monkeypatch.setattr(
        cli_module,
        "sweep_abandoned_uploads",
        lambda session: SweepResult(
            images=2, storage_keys=["users/u/items/i/good", "users/u/items/i/bad"]
        ),
    )
    monkeypatch.setattr(
        cli_module.S3ObjectStore, "from_settings", classmethod(lambda cls, s: store)
    )
    result = run("sweep-uploads")
    assert result.exit_code == 0, result.output
    assert "swept images=2 orphaned_objects=1" in result.output
    assert store.head("users/u/items/i/good") is None


class _null_scope:  # noqa: N801 - stands in for the session_scope function
    def __init__(self, factory: Any) -> None:
        pass

    def __enter__(self) -> None:
        return None

    def __exit__(self, *exc: object) -> None:
        return None


@pytest.mark.db
class TestEbayTaxonomy:
    def test_replaces_previous_terms(
        self, db_env: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        batches = iter(
            [
                [("Parallel/Variety", "Gold Refractor"), ("Grade", "10")],
                [("Parallel/Variety", "Gold Refractor")],
            ]
        )

        class FakeTaxonomy:
            def __init__(self, api: Any) -> None:
                pass

            def aspect_values(self) -> list[tuple[str, str]]:
                return next(batches)

        monkeypatch.setattr(cli_module, "EbayTaxonomyClient", FakeTaxonomy)
        monkeypatch.setattr(cli_module, "EbayApi", lambda config: None)
        monkeypatch.setattr(
            cli_module.EbayConfig, "from_settings", classmethod(lambda cls, s: None)
        )
        assert "loaded 2 eBay taxonomy terms" in run("sync-ebay-taxonomy").output
        assert "loaded 1 eBay taxonomy terms" in run("sync-ebay-taxonomy").output
        assert count(db_env, CatalogTerm) == 1

    def test_missing_keys_fail_cleanly(self, env: None, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("CARD_MAVEN_EBAY_CLIENT_ID", raising=False)
        result = run("sync-ebay-taxonomy")
        assert result.exit_code == 1
        assert "eBay" in result.output


class FakeSource:
    code = "ebay_browse"

    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.queries: list[MarketQuery] = []

    def fetch(self, query: MarketQuery, *, now: datetime) -> Sequence[MarketRecord]:
        self.queries.append(query)
        if self.error:
            raise self.error
        return [
            MarketRecord(
                kind="listing",
                source_listing_id="1",
                title="2024 Topps Chrome Paul Skenes #1 RC PSA 10",
                price=Money.from_decimal("99.00", "USD"),
                occurred_at=datetime(2026, 10, 27, tzinfo=UTC),
            )
        ]


class TestMarketSearch:
    def test_prints_records_with_parsed_grade(
        self, env: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        source = FakeSource()
        monkeypatch.setattr(cli_module, "build_sources", lambda settings: {"ebay_browse": source})
        result = run("market-search", "Topps", "Chrome", "--year", "2024")
        assert result.exit_code == 0, result.output
        assert "PSA 10" in result.output
        assert "1 records from ebay_browse" in result.output
        assert source.queries[0].set_name == "Topps Chrome"

    def test_unavailable_source(self, env: None, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(cli_module, "build_sources", lambda settings: {})
        result = run("market-search", "Topps", "--year", "2024")
        assert result.exit_code == 1
        assert "not available" in result.output

    def test_source_errors_are_reported(self, env: None, monkeypatch: pytest.MonkeyPatch) -> None:
        source = FakeSource(DependencyUnavailableError("eBay is rate limiting"))
        monkeypatch.setattr(cli_module, "build_sources", lambda settings: {"ebay_browse": source})
        result = run("market-search", "Topps", "--year", "2024")
        assert result.exit_code == 1
        assert "rate limiting" in result.output


class IdleConsumer:
    """Subscribes, finds nothing, and asks the loop to stop."""

    def __init__(self) -> None:
        self.stop = threading.Event()
        self.subscribed: list[str] = []
        self.closed = False

    def subscribe(self, topics: list[str]) -> None:
        self.subscribed = topics

    def poll(self, timeout: float) -> None:
        self.stop.set()

    def commit(self, message: Any, asynchronous: bool) -> None:
        raise AssertionError("nothing to commit")

    def close(self) -> None:
        self.closed = True


def test_market_worker_wires_consumer_and_exits(
    env: None, monkeypatch: pytest.MonkeyPatch, database_url: str
) -> None:
    monkeypatch.setenv("CARD_MAVEN_DATABASE_URL", database_url)
    consumer = IdleConsumer()
    monkeypatch.setattr(cli_module, "kafka_consumer", lambda *a, **k: consumer)
    monkeypatch.setattr(cli_module, "KafkaPublisher", lambda *a, **k: InMemoryPublisher())
    monkeypatch.setattr(cli_module, "_stop_on_signals", lambda: consumer.stop)
    result = run("market-worker")
    assert result.exit_code == 0, result.output
    assert "handled=0" in result.output
    assert consumer.subscribed == ["market.sync.requested"]
    assert consumer.closed
