import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from card_maven.catalog.schemas import CardIdentity
from card_maven.catalog.service import CatalogService
from card_maven.market.ingestion import MarketSyncService, sync_event
from card_maven.market.models import MarketSyncJob, ProcessedEvent, Sale
from card_maven.market.sources.fixture import FixtureSource
from card_maven.market.sources.port import MarketQuery, MarketRecord
from card_maven.reference_data import load_reference_data, seed_reference_data
from card_maven.shared.db import session_scope
from card_maven.shared.errors import DependencyUnavailableError, InvalidInputError, NotFoundError
from card_maven.shared.events import Event
from card_maven_workers.market_worker import MarketSyncHandler

pytestmark = pytest.mark.db

REPO_ROOT = Path(__file__).resolve().parents[3]
NOW = datetime(2026, 10, 27, 12, tzinfo=UTC)


class Down:
    code = "fixture"

    def __init__(self) -> None:
        self.calls = 0

    def fetch(self, query: MarketQuery, *, now: datetime) -> Sequence[MarketRecord]:
        self.calls += 1
        raise DependencyUnavailableError("down")


@pytest.fixture
def job(committing_session_factory: sessionmaker[Session]) -> tuple[MarketSyncJob, Event]:
    with session_scope(committing_session_factory) as session:
        seed_reference_data(session, load_reference_data(REPO_ROOT / "config/reference_data.yaml"))
        variant = CatalogService(session).resolve_variant(
            CardIdentity.model_validate(
                {
                    "sport": "baseball",
                    "brand": "Topps",
                    "year": 2024,
                    "set_name": "Topps Chrome",
                    "card_number": "1",
                    "name": "Paul Skenes",
                    "players": ["Paul Skenes"],
                }
            )
        )
        job = MarketSyncService(session).request_variant_sync(variant.id, requested_by=None).job
        return job, sync_event(job)


def fixtures() -> dict[str, FixtureSource]:
    return {"fixture": FixtureSource.from_file(REPO_ROOT / "config/market_fixtures.yaml")}


def test_runs_job_once_even_if_delivered_twice(
    committing_session_factory: sessionmaker[Session], job: tuple[MarketSyncJob, Event]
) -> None:
    record, event = job
    handler = MarketSyncHandler(committing_session_factory, fixtures(), clock=lambda: NOW)
    handler(event)
    handler(event)  # redelivery
    with session_scope(committing_session_factory) as session:
        stored = session.get(MarketSyncJob, record.id)
        assert stored is not None
        assert (stored.status, stored.attempts) == ("succeeded", 1)
        # Base Skenes #1: one raw, two PSA 10, one PSA 9. Refractor + Gold kept unmatched.
        assert stored.stats["fixture"] == {
            "fetched": 9,
            "stored": 4,
            "stored_unmatched": 2,
            "disqualified": 3,
        }
        assert session.scalar(select(func.count()).select_from(ProcessedEvent)) == 1
        matched = select(func.count()).select_from(Sale).where(Sale.variant_id.is_not(None))
        assert session.scalar(matched) == 4


def test_transient_failure_retries_then_records_failure(
    committing_session_factory: sessionmaker[Session], job: tuple[MarketSyncJob, Event]
) -> None:
    record, event = job
    down = Down()
    handler = MarketSyncHandler(
        committing_session_factory, {"fixture": down}, clock=lambda: NOW, max_attempts=2
    )
    with pytest.raises(DependencyUnavailableError):
        handler(event)  # attempt 1: the consumer loop will retry
    handler(event)  # attempt 2 (last): give up gracefully and mark the job failed
    with session_scope(committing_session_factory) as session:
        stored = session.get(MarketSyncJob, record.id)
        assert stored is not None
        assert (stored.status, stored.attempts) == ("failed", 2)
        assert stored.error == "fixture: down"
    assert down.calls == 2


@pytest.mark.parametrize("data", [{}, {"job_id": "nope"}])
def test_rejects_bad_payloads(
    committing_session_factory: sessionmaker[Session], data: dict[str, str]
) -> None:
    handler = MarketSyncHandler(committing_session_factory, {})
    with pytest.raises(InvalidInputError, match="job_id"):
        handler(Event(type="market.sync.requested.v1", source="t", data=data))


def test_rejects_other_event_types(committing_session_factory: sessionmaker[Session]) -> None:
    with pytest.raises(InvalidInputError, match="unexpected event type"):
        MarketSyncHandler(committing_session_factory, {})(
            Event(type="scan.requested.v1", source="t")
        )


def test_unknown_job_is_permanent(committing_session_factory: sessionmaker[Session]) -> None:
    with pytest.raises(NotFoundError):
        MarketSyncHandler(committing_session_factory, {})(
            Event(type="market.sync.requested.v1", source="t", data={"job_id": str(uuid.uuid4())})
        )
