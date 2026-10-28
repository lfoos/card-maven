from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from card_maven.catalog.models import CardVariant
from card_maven.market.ingestion import SALES_INGESTED, SYNC_REQUESTED, MarketSyncService
from card_maven.market.models import CatalogTerm, Listing, MarketSyncJob, Sale, TrackedSet
from card_maven.market.sources.fixture import FixtureSource
from card_maven.market.sources.port import MarketQuery, MarketRecord, MarketSourceError
from card_maven.shared.errors import DependencyUnavailableError, NotFoundError
from card_maven.shared.money import Money
from card_maven.shared.outbox import OutboxMessage

pytestmark = pytest.mark.db

REPO_ROOT = Path(__file__).resolve().parents[3]
NOW = datetime(2026, 10, 27, 12, 0, tzinfo=UTC)


class StubSource:
    def __init__(
        self, code: str, records: Sequence[MarketRecord] = (), error: Exception | None = None
    ) -> None:
        self.code = code
        self.records = list(records)
        self.error = error
        self.queries: list[MarketQuery] = []

    def fetch(self, query: MarketQuery, *, now: datetime) -> Sequence[MarketRecord]:
        self.queries.append(query)
        if self.error:
            raise self.error
        return self.records


def listing(id_: str, title: str, price: int = 50000, **extra: Any) -> MarketRecord:
    return MarketRecord(
        kind="listing",
        source_listing_id=id_,
        title=title,
        price=Money(price, "USD"),
        occurred_at=NOW,
        option="fixed_price",
        **extra,
    )


def sale(id_: str, title: str, price: int = 10000, days: int = 1) -> MarketRecord:
    return MarketRecord(
        kind="sale",
        source_listing_id=id_,
        title=title,
        price=Money(price, "USD"),
        occurred_at=NOW - timedelta(days=days),
        option="auction",
    )


def run(session: Session, job: MarketSyncJob, sources: dict[str, Any]) -> dict[str, Any]:
    service = MarketSyncService(session)
    plan = service.plan(job.id)
    fetched = service.fetch(plan, sources, now=NOW)
    return service.store(plan, fetched, now=NOW)


def count(session: Session, model: type, *where: Any) -> int:
    return session.scalar(select(func.count()).select_from(model).where(*where)) or 0


class TestRequesting:
    def test_variant_request_creates_job_and_event(
        self, seeded_session: Session, gold: CardVariant
    ) -> None:
        requested = MarketSyncService(seeded_session).request_variant_sync(
            gold.id, requested_by=None
        )
        assert requested.created
        assert requested.job.status == "queued"
        [message] = seeded_session.scalars(select(OutboxMessage)).all()
        assert message.event_type == SYNC_REQUESTED
        assert message.partition_key == f"variant:{gold.id}"
        assert message.payload["data"]["job_id"] == str(requested.job.id)

    def test_active_or_recent_jobs_are_reused(
        self, seeded_session: Session, gold: CardVariant
    ) -> None:
        service = MarketSyncService(seeded_session)
        first = service.request_variant_sync(gold.id, requested_by=None).job
        assert service.request_variant_sync(gold.id, requested_by=None).job.id == first.id  # queued
        first.status, first.finished_at = "succeeded", NOW
        again = service.request_variant_sync(
            gold.id, requested_by=None, now=NOW + timedelta(minutes=10)
        )
        assert (again.created, again.job.id) == (False, first.id)  # recent success
        later = service.request_variant_sync(
            gold.id, requested_by=None, now=NOW + timedelta(minutes=16)
        )
        assert later.created
        later.job.status = "failed"
        assert service.request_variant_sync(gold.id, requested_by=None).created  # failures retry

    def test_stuck_jobs_stop_blocking_after_ten_minutes(
        self, seeded_session: Session, gold: CardVariant
    ) -> None:
        service = MarketSyncService(seeded_session)
        stuck = service.request_variant_sync(gold.id, requested_by=None).job
        stuck.status = "running"
        soon = stuck.created_at + timedelta(minutes=9)
        assert service.request_variant_sync(gold.id, requested_by=None, now=soon).job.id == stuck.id
        later = stuck.created_at + timedelta(minutes=11)
        assert service.request_variant_sync(gold.id, requested_by=None, now=later).created

    def test_nightly_requests_one_job_per_active_tracked_set(self, seeded_session: Session) -> None:
        seeded_session.add_all(
            [
                TrackedSet(
                    sport_code="baseball", brand_slug="bowman", set_name="Bowman Chrome", year=2025
                ),
                TrackedSet(
                    sport_code="baseball",
                    brand_slug="topps",
                    set_name="Topps Chrome",
                    year=2024,
                    active=False,
                ),
            ]
        )
        seeded_session.flush()
        jobs = MarketSyncService(seeded_session).request_tracked_set_syncs()
        assert [j.target_type for j in jobs] == ["tracked_set"]
        assert count(seeded_session, OutboxMessage) == 1


class TestVariantSync:
    def test_stores_matched_listings_and_sales_with_grades(
        self, seeded_session: Session, gold: CardVariant
    ) -> None:
        job = MarketSyncService(seeded_session).request_variant_sync(gold.id, requested_by=None).job
        ebay = StubSource(
            "ebay_browse",
            [
                listing(
                    "e1",
                    "2025 Bowman Chrome JJ Wetherholt CPA-JW Gold Refractor Auto /50 PSA 10",
                    url="https://ebay/1?campid=1",
                    image_url="https://img/1",
                    bid_count=None,
                    ends_at=NOW + timedelta(days=3),
                ),
                listing(
                    "e2", "2025 Bowman Chrome JJ Wetherholt Orange Refractor Auto /25"
                ),  # other parallel
                listing("e3", "2025 Bowman Chrome lot of 4 autos Wetherholt"),
            ],
        )
        fixture = StubSource(
            "fixture",
            [
                sale(
                    "f1", "2025 Bowman Chrome JJ Wetherholt CPA-JW Gold Refractor Auto 12/50", 64000
                ),
                sale(
                    "f2", "2025 Bowman Chrome Roman Anthony BCP-50"
                ),  # unrelated card: kept unmatched
            ],
        )
        stats = run(seeded_session, job, {"ebay_browse": ebay, "fixture": fixture})

        assert stats["ebay_browse"] == {
            "fetched": 3,
            "stored": 1,
            "unmatched": 1,
            "disqualified": 1,
        }
        assert stats["fixture"] == {"fetched": 2, "stored": 1, "stored_unmatched": 1}
        assert ebay.queries[0].card_number == "CPA-JW"
        stored = seeded_session.scalars(select(Listing)).one()
        assert (stored.variant_id, stored.condition, stored.grader, str(stored.grade)) == (
            gold.id,
            "graded",
            "PSA",
            "10.0",
        )
        assert stored.url == "https://ebay/1?campid=1"
        assert stored.match_confidence == 1
        sales = {s.source_listing_id: s for s in seeded_session.scalars(select(Sale))}
        assert sales["f1"].variant_id == gold.id
        assert sales["f2"].variant_id is None
        assert sales["f2"].match_confidence is None
        seeded_session.refresh(job)
        assert (job.status, job.attempts, job.error) == ("succeeded", 1, None)
        assert job.finished_at == NOW
        events = [
            m.event_type
            for m in seeded_session.scalars(select(OutboxMessage).order_by(OutboxMessage.id))
        ]
        assert events == [SYNC_REQUESTED, SALES_INGESTED]

    def test_display_only_sources_can_never_create_sales(
        self, seeded_session: Session, gold: CardVariant
    ) -> None:
        job = MarketSyncService(seeded_session).request_variant_sync(gold.id, requested_by=None).job
        rogue = StubSource(
            "ebay_browse",
            [sale("x1", "2025 Bowman Chrome Wetherholt CPA-JW Gold Refractor Auto /50")],
        )
        assert (
            run(seeded_session, job, {"ebay_browse": rogue})["ebay_browse"]["rejected_license"] == 1
        )
        assert count(seeded_session, Sale) == 0

    def test_reingesting_is_idempotent_and_refreshes(
        self, seeded_session: Session, gold: CardVariant
    ) -> None:
        service = MarketSyncService(seeded_session)
        title = "2025 Bowman Chrome JJ Wetherholt CPA-JW Gold Refractor Auto /50"
        first = service.request_variant_sync(gold.id, requested_by=None).job
        run(
            seeded_session,
            first,
            {
                "ebay_browse": StubSource("ebay_browse", [listing("e1", title, 50000)]),
                "fixture": StubSource("fixture", [sale("f1", title, 60000)]),
            },
        )
        first.finished_at = NOW - timedelta(hours=1)
        second = service.request_variant_sync(gold.id, requested_by=None, now=NOW).job
        later = NOW + timedelta(hours=2)
        service.plan(second.id)
        moved = MarketRecord(
            kind="listing",
            source_listing_id="e1",
            title=title,
            price=Money(45000, "USD"),
            occurred_at=later,
            option="fixed_price",
        )
        plan = service.plan(second.id)
        fetched = service.fetch(
            plan,
            {
                "ebay_browse": StubSource("ebay_browse", [moved]),
                "fixture": StubSource("fixture", [sale("f1", "garbled title no year")]),
            },
            now=later,
        )
        service.store(plan, fetched, now=later)
        seeded_session.expire_all()
        refreshed = seeded_session.scalars(select(Listing)).one()
        assert (refreshed.price_minor, refreshed.observed_at) == (45000, later)
        kept = seeded_session.scalars(select(Sale)).one()
        assert kept.variant_id == gold.id  # a worse re-ingest never un-matches a sale

    def test_one_failing_source_does_not_fail_the_job(
        self, seeded_session: Session, gold: CardVariant
    ) -> None:
        job = MarketSyncService(seeded_session).request_variant_sync(gold.id, requested_by=None).job
        stats = run(
            seeded_session,
            job,
            {
                "ebay_browse": StubSource(
                    "ebay_browse", error=DependencyUnavailableError("eBay down")
                ),
                "fixture": StubSource("fixture"),
            },
        )
        assert stats["ebay_browse"] == {"error": "eBay down", "transient": True}
        assert stats["fixture"] == {"fetched": 0}
        assert job.status == "succeeded"

    def test_a_crashing_adapter_is_contained(
        self, seeded_session: Session, gold: CardVariant
    ) -> None:
        job = MarketSyncService(seeded_session).request_variant_sync(gold.id, requested_by=None).job
        stats = run(
            seeded_session,
            job,
            {
                "ebay_browse": StubSource("ebay_browse", error=KeyError("itemSummaries")),
                "fixture": StubSource("fixture"),
            },
        )
        # Collectors see the job: no internals in the message.
        assert stats["ebay_browse"] == {
            "error": "unexpected error (see worker logs)",
            "transient": False,
        }
        assert stats["fixture"] == {"fetched": 0}
        assert job.status == "succeeded"

    def test_job_fails_when_every_source_fails(
        self, seeded_session: Session, gold: CardVariant
    ) -> None:
        job = MarketSyncService(seeded_session).request_variant_sync(gold.id, requested_by=None).job
        run(
            seeded_session,
            job,
            {"ebay_browse": StubSource("ebay_browse", error=MarketSourceError("bad key"))},
        )
        assert job.status == "failed"
        assert job.error == "ebay_browse: bad key"

    def test_unregistered_or_disabled_sources_are_ignored(
        self, seeded_session: Session, gold: CardVariant
    ) -> None:
        from card_maven.market.models import MarketSource

        seeded_session.get(MarketSource, "ebay_browse").enabled = False
        job = MarketSyncService(seeded_session).request_variant_sync(gold.id, requested_by=None).job
        stray = StubSource("mystery")
        disabled = StubSource("ebay_browse")
        assert run(seeded_session, job, {"mystery": stray, "ebay_browse": disabled}) == {}
        assert stray.queries == disabled.queries == []

    def test_taxonomy_vocabulary_extends_conflicts(
        self,
        seeded_session: Session,
        make_variant: Callable[..., CardVariant],
        card_specs: dict[str, Any],
    ) -> None:
        base = make_variant(**card_specs["skenes_base"])
        seeded_session.add(CatalogTerm(source="ebay", aspect="Parallel/Variety", value="Sepia"))
        job = MarketSyncService(seeded_session).request_variant_sync(base.id, requested_by=None).job
        source = StubSource(
            "fixture",
            [
                sale("s1", "2024 Topps Chrome Paul Skenes #1 Sepia RC"),
                sale("s2", "2024 Topps Chrome Paul Skenes #1 RC"),
            ],
        )
        run(seeded_session, job, {"fixture": source})
        matched = {s.source_listing_id: s.variant_id for s in seeded_session.scalars(select(Sale))}
        assert matched == {"s1": None, "s2": base.id}

    def test_missing_job_or_variant(self, seeded_session: Session) -> None:
        import uuid

        service = MarketSyncService(seeded_session)
        with pytest.raises(NotFoundError):
            service.plan(uuid.uuid4())
        job = MarketSyncJob(target_type="variant", target_id=uuid.uuid4())
        seeded_session.add(job)
        seeded_session.flush()
        with pytest.raises(NotFoundError, match="variant"):
            service.plan(job.id)
        service.fail(job.id, "boom")
        assert job.status == "failed"
        service.fail(uuid.uuid4(), "ignored")  # unknown job: no error


class TestTrackedSetSync:
    def test_matches_against_every_known_card_in_the_set(
        self, seeded_session: Session, make_variant: Callable[..., CardVariant], gold: CardVariant
    ) -> None:
        anthony = make_variant(
            sport="baseball",
            brand="Bowman",
            year=2025,
            set_name="Bowman Chrome",
            card_number="BCP-50",
            name="Roman Anthony",
            players=["Roman Anthony"],
            subset="Prospects",
        )
        tracked = TrackedSet(
            sport_code="baseball", brand_slug="bowman", set_name="bowman chrome", year=2025
        )
        seeded_session.add(tracked)
        seeded_session.flush()
        [job] = MarketSyncService(seeded_session).request_tracked_set_syncs()
        ebay = StubSource("ebay_browse", [listing("e1", "2025 Bowman Chrome Roman Anthony BCP-50")])
        fixture = FixtureSource.from_file(REPO_ROOT / "config/market_fixtures.yaml")
        stats = run(seeded_session, job, {"fixture": fixture, "ebay_browse": ebay})

        assert ebay.queries == []  # display-only sources skip nightly set-wide syncs
        assert "ebay_browse" not in stats or stats["ebay_browse"] == {"fetched": 0}
        assert stats["fixture"]["disqualified"] >= 2  # the lot and the break
        by_variant = dict(
            seeded_session.execute(
                select(Sale.variant_id, func.count()).group_by(Sale.variant_id)
            ).all()
        )
        assert by_variant[gold.id] == 3  # fx-007 (12/50), fx-008 (PSA 10), fx-009 (PSA 9)
        assert by_variant[anthony.id] == 2  # base and PSA 10; not the /499 refractor
        assert by_variant[None] > 0

    def test_unknown_tracked_set(self, seeded_session: Session) -> None:
        import uuid

        job = MarketSyncJob(target_type="tracked_set", target_id=uuid.uuid4())
        seeded_session.add(job)
        seeded_session.flush()
        with pytest.raises(NotFoundError, match="tracked set"):
            MarketSyncService(seeded_session).plan(job.id)
