import uuid
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from card_maven.catalog.models import CardVariant
from card_maven.collection.maintenance import sweep_abandoned_uploads
from card_maven.collection.models import CollectionItem, Image
from card_maven.identity.models import User
from card_maven.market.comps import Grade, _median, comps_for, current_asks, estimates_for
from card_maven.market.maintenance import purge_market_data
from card_maven.market.manual import ManualCompsService, ManualSale, ManualSales
from card_maven.market.models import Listing, MarketSyncJob, ProcessedEvent, Sale
from card_maven.shared.clock import utcnow
from card_maven.shared.errors import InvalidInputError, NotFoundError
from card_maven.shared.money import Money

pytestmark = pytest.mark.db

NOW = datetime(2026, 10, 27, 12, 0, tzinfo=UTC)


def add_sale(
    session: Session,
    variant: CardVariant | None,
    price: int,
    *,
    days: int = 1,
    grader: str | None = None,
    grade: str | None = None,
    source: str = "fixture",
    submitted_by: uuid.UUID | None = None,
    currency: str = "USD",
) -> Sale:
    sale = Sale(
        source_code=source,
        source_listing_id=f"t-{uuid.uuid4()}",
        title="t",
        variant_id=variant.id if variant else None,
        match_confidence=Decimal(1) if variant else None,
        match_method="test" if variant else None,
        price_minor=price,
        currency=currency,
        condition="graded" if grader else "raw",
        grader=grader,
        grade=Decimal(grade) if grade else None,
        sold_at=NOW - timedelta(days=days),
        submitted_by=submitted_by,
    )
    session.add(sale)
    session.flush()
    return sale


def add_listing(
    session: Session,
    variant: CardVariant,
    price: int,
    *,
    hours_old: float = 1,
    ends_in: timedelta | None = None,
    source: str = "ebay_browse",
) -> Listing:
    item = Listing(
        source_code=source,
        source_listing_id=f"l-{uuid.uuid4()}",
        title="t",
        variant_id=variant.id,
        match_confidence=Decimal(1),
        match_method="test",
        price_minor=price,
        currency="USD",
        condition="raw",
        buying_option="fixed_price",
        observed_at=NOW - timedelta(hours=hours_old),
        ends_at=NOW + ends_in if ends_in else None,
    )
    session.add(item)
    session.flush()
    return item


@pytest.fixture
def owner(make_user: Callable[[str], User]) -> User:
    return make_user("owner")


@pytest.fixture
def psa10(
    make_item: Callable[..., CollectionItem], owner: User, card_specs: dict[str, Any]
) -> CollectionItem:
    return make_item(
        owner, card_specs["wetherholt_gold"], condition="graded", grader="PSA", grade="10"
    )


class TestComps:
    def test_exact_grade_first_then_nearest_then_newest(
        self, seeded_session: Session, psa10: CollectionItem, owner: User
    ) -> None:
        variant = psa10.variant
        old_exact = add_sale(seeded_session, variant, 110000, days=20, grader="PSA", grade="10")
        new_exact = add_sale(seeded_session, variant, 115000, days=2, grader="PSA", grade="10")
        nine = add_sale(seeded_session, variant, 78000, days=1, grader="PSA", grade="9")
        nine_half = add_sale(seeded_session, variant, 90000, days=5, grader="BGS", grade="9.5")
        raw = add_sale(seeded_session, variant, 64000, days=1)
        add_sale(seeded_session, None, 1)  # unmatched: never a comp

        comps = comps_for(seeded_session, psa10, owner.id)
        assert [c.sale.id for c in comps] == [
            new_exact.id,
            old_exact.id,
            nine_half.id,
            nine.id,
            raw.id,
        ]
        assert [c.match for c in comps] == ["exact", "exact", "nearest", "nearest", "nearest"]
        assert len(comps_for(seeded_session, psa10, owner.id, limit=2)) == 2

    def test_raw_items_prefer_raw_sales(
        self,
        seeded_session: Session,
        make_item: Callable[..., CollectionItem],
        owner: User,
        card_specs: dict[str, Any],
    ) -> None:
        item = make_item(owner, card_specs["wetherholt_gold"])
        graded = add_sale(seeded_session, item.variant, 100000, days=1, grader="PSA", grade="10")
        raw = add_sale(seeded_session, item.variant, 60000, days=5)
        assert [(c.sale.id, c.match) for c in comps_for(seeded_session, item, owner.id)] == [
            (raw.id, "exact"),
            (graded.id, "nearest"),
        ]

    def test_license_gate_and_privacy(
        self,
        seeded_session: Session,
        psa10: CollectionItem,
        owner: User,
        make_user: Callable[[str], User],
    ) -> None:
        stranger = make_user("stranger")
        mine = add_sale(
            seeded_session,
            psa10.variant,
            1,
            source="manual",
            submitted_by=owner.id,
            grader="PSA",
            grade="10",
        )
        theirs = add_sale(
            seeded_session,
            psa10.variant,
            2,
            source="manual",
            submitted_by=stranger.id,
            grader="PSA",
            grade="10",
        )
        # Even if a display-only sale slipped into the table, comps exclude it.
        leaked = add_sale(
            seeded_session, psa10.variant, 3, source="ebay_browse", grader="PSA", grade="10"
        )
        ids = {c.sale.id for c in comps_for(seeded_session, psa10, owner.id)}
        assert mine.id in ids
        assert theirs.id not in ids
        assert leaked.id not in ids


class TestCurrentAsks:
    def test_fresh_unended_cheapest_first(self, seeded_session: Session, gold: CardVariant) -> None:
        cheap = add_listing(seeded_session, gold, 50000, hours_old=2)
        pricey = add_listing(seeded_session, gold, 90000, hours_old=5.9)
        add_listing(seeded_session, gold, 10000, hours_old=6.5)  # stale (> 6h): hidden
        add_listing(seeded_session, gold, 20000, ends_in=-timedelta(minutes=1))  # ended
        asks = current_asks(seeded_session, gold.id, now=NOW)
        assert [a.id for a in asks] == [cheap.id, pricey.id]

    def test_disabled_sources_hidden(self, seeded_session: Session, gold: CardVariant) -> None:
        from card_maven.market.models import MarketSource

        add_listing(seeded_session, gold, 50000)
        seeded_session.get(MarketSource, "ebay_browse").enabled = False
        assert current_asks(seeded_session, gold.id, now=NOW) == []


class TestEstimates:
    @pytest.mark.parametrize(
        ("prices", "median"),
        [([100], 100), ([100, 300], 200), ([1, 2, 9], 2), ([1, 2], 2), ([3, 4], 4)],
    )
    def test_median_rounds_half_even(self, prices: list[int], median: int) -> None:
        assert _median(prices) == median

    def test_median_of_recent_exact_grade_sales(
        self, seeded_session: Session, psa10: CollectionItem, owner: User
    ) -> None:
        for days, price in [
            (1, 100000),
            (3, 120000),
            (10, 110000),
            (200, 999999),
        ]:  # 200d: outside window
            add_sale(seeded_session, psa10.variant, price, days=days, grader="PSA", grade="10")
        add_sale(seeded_session, psa10.variant, 50000, grader="PSA", grade="9")  # other grade
        add_sale(
            seeded_session, psa10.variant, 1, grader="PSA", grade="10", currency="CAD"
        )  # other currency
        estimate = estimates_for(seeded_session, [psa10], owner.id, now=NOW)[psa10.id]
        assert estimate.value == Money(110000, "USD")
        assert (estimate.sample_size, estimate.window_days, estimate.grade.label()) == (
            3,
            180,
            "PSA 10",
        )
        assert estimate.latest_sale_at == NOW - timedelta(days=1)

    def test_uses_only_the_ten_most_recent(
        self, seeded_session: Session, psa10: CollectionItem, owner: User
    ) -> None:
        for day in range(1, 13):
            add_sale(
                seeded_session,
                psa10.variant,
                1000 if day <= 10 else 9_000_000,
                days=day,
                grader="PSA",
                grade="10",
            )
        estimate = estimates_for(seeded_session, [psa10], owner.id, now=NOW)[psa10.id]
        assert (estimate.sample_size, estimate.value) == (10, Money(1000, "USD"))

    def test_batch_matches_individual_and_skips_items_without_sales(
        self,
        seeded_session: Session,
        psa10: CollectionItem,
        owner: User,
        make_item: Callable[..., CollectionItem],
        card_specs: dict[str, Any],
    ) -> None:
        raw = make_item(owner, card_specs["wetherholt_gold"])
        empty = make_item(owner, card_specs["skenes_base"])
        add_sale(seeded_session, psa10.variant, 100000, grader="PSA", grade="10")
        add_sale(seeded_session, psa10.variant, 40000)
        batch = estimates_for(seeded_session, [psa10, raw, empty], owner.id, now=NOW)
        assert set(batch) == {psa10.id, raw.id}
        assert (
            batch[psa10.id] == estimates_for(seeded_session, [psa10], owner.id, now=NOW)[psa10.id]
        )
        assert batch[raw.id].grade.label() == "Raw"
        assert estimates_for(seeded_session, [], owner.id) == {}

    def test_private_and_display_only_sales(
        self,
        seeded_session: Session,
        psa10: CollectionItem,
        owner: User,
        make_user: Callable[[str], User],
    ) -> None:
        stranger = make_user("stranger")
        add_sale(
            seeded_session,
            psa10.variant,
            500,
            source="manual",
            submitted_by=stranger.id,
            grader="PSA",
            grade="10",
        )
        add_sale(seeded_session, psa10.variant, 700, source="ebay_browse", grader="PSA", grade="10")
        assert estimates_for(seeded_session, [psa10], owner.id, now=NOW) == {}
        add_sale(
            seeded_session,
            psa10.variant,
            900,
            source="manual",
            submitted_by=owner.id,
            grader="PSA",
            grade="10",
        )
        assert estimates_for(seeded_session, [psa10], owner.id, now=NOW)[psa10.id].value == Money(
            900, "USD"
        )

    def test_grade_labels(self) -> None:
        assert Grade("graded", "BGS", Decimal("9.5")).label() == "BGS 9.5"
        assert Grade("graded", "PSA", Decimal("10.0")).label() == "PSA 10"
        assert Grade("raw").label() == "Raw"


class TestManualComps:
    def sale(self, **overrides: Any) -> dict[str, Any]:
        return {"sold_on": "2026-10-01", "price": {"amount": "125.00"}, **overrides}

    def test_caps_each_collectors_sales_per_card(
        self,
        seeded_session: Session,
        psa10: CollectionItem,
        owner: User,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr("card_maven.market.manual.MAX_SALES_PER_CARD", 3)
        service = ManualCompsService(seeded_session, owner.id)
        two = ManualSales.model_validate({"sales": [self.sale(), self.sale()]})
        service.add(psa10.id, two)
        with pytest.raises(InvalidInputError, match="at most 3 of your own sales per card"):
            service.add(psa10.id, two)
        service.add(psa10.id, ManualSales.model_validate({"sales": [self.sale()]}))  # exactly 3

    def test_add_and_delete(
        self,
        seeded_session: Session,
        psa10: CollectionItem,
        owner: User,
        make_user: Callable[[str], User],
    ) -> None:
        service = ManualCompsService(seeded_session, owner.id)
        [added] = service.add(
            psa10.id,
            ManualSales(
                sales=[
                    ManualSale.model_validate(
                        self.sale(
                            condition="graded",
                            grader="PSA",
                            grade="10",
                            title="  From Terapeak  ",
                            url="https://www.ebay.com/itm/1",
                            sale_type="auction",
                        )
                    )
                ]
            ),
        )
        assert (added.source_code, added.submitted_by, added.variant_id) == (
            "manual",
            owner.id,
            psa10.variant_id,
        )
        assert (added.title, added.price_minor, added.sale_type, added.grade) == (
            "From Terapeak",
            12500,
            "auction",
            Decimal(10),
        )
        assert added.sold_at.date() == date(2026, 10, 1)

        stranger = ManualCompsService(seeded_session, make_user("stranger").id)
        with pytest.raises(NotFoundError):
            stranger.delete(added.id)
        with pytest.raises(NotFoundError):
            stranger.add(psa10.id, ManualSales(sales=[ManualSale.model_validate(self.sale())]))
        service.delete(added.id)
        assert seeded_session.scalars(select(Sale)).all() == []

    def test_cannot_delete_shared_sales(
        self, seeded_session: Session, gold: CardVariant, owner: User
    ) -> None:
        shared = add_sale(seeded_session, gold, 100)
        with pytest.raises(NotFoundError):
            ManualCompsService(seeded_session, owner.id).delete(shared.id)

    @pytest.mark.parametrize(
        ("overrides", "message"),
        [
            ({"sold_on": (utcnow() + timedelta(days=2)).date().isoformat()}, "future"),
            ({"sold_on": "2001-01-01"}, "last 15 years"),
            ({"condition": "graded"}, "grader and a grade"),
            ({"grader": "PSA", "grade": "10"}, "raw sales"),
            ({"condition": "graded", "grader": "PSA", "grade": "9.2"}, "0.5"),
            ({"price": {"amount": 12.5}}, "as a string"),
            ({"url": "javascript:alert(1)"}, "URL"),
            ({"url": "ftp://x.test/a"}, "URL scheme"),
            ({"extra": 1}, "Extra inputs"),
        ],
    )
    def test_validation(self, overrides: dict[str, Any], message: str) -> None:
        with pytest.raises(ValidationError, match=message):
            ManualSale.model_validate(self.sale(**overrides))

    def test_batch_limits(self) -> None:
        with pytest.raises(ValidationError):
            ManualSales(sales=[])
        with pytest.raises(ValidationError):
            ManualSales.model_validate({"sales": [self.sale()] * 201})


class TestMaintenance:
    def test_purges_stale_and_ended_display_only_listings(
        self, seeded_session: Session, gold: CardVariant
    ) -> None:
        fresh = add_listing(seeded_session, gold, 1, hours_old=1)
        add_listing(seeded_session, gold, 2, hours_old=7)
        add_listing(seeded_session, gold, 3, ends_in=-timedelta(seconds=1))
        old_job = MarketSyncJob(
            target_type="variant",
            target_id=gold.id,
            status="succeeded",
            finished_at=NOW - timedelta(days=31),
        )
        new_job = MarketSyncJob(
            target_type="variant", target_id=gold.id, status="succeeded", finished_at=NOW
        )
        running = MarketSyncJob(target_type="variant", target_id=gold.id, status="running")
        abandoned = MarketSyncJob(
            target_type="variant",
            target_id=gold.id,
            status="running",
            created_at=NOW - timedelta(days=31),
        )
        seeded_session.add_all([old_job, new_job, running, abandoned])
        seeded_session.add_all(
            [
                ProcessedEvent(
                    consumer="market-worker",
                    event_id=uuid.uuid4(),
                    processed_at=NOW - timedelta(days=31),
                ),
                ProcessedEvent(consumer="market-worker", event_id=uuid.uuid4(), processed_at=NOW),
            ]
        )
        seeded_session.flush()

        result = purge_market_data(seeded_session, now=NOW)
        assert (result.listings, result.jobs, result.processed_events) == (2, 2, 1)
        assert [listing.id for listing in seeded_session.scalars(select(Listing))] == [fresh.id]
        remaining = {job.id for job in seeded_session.scalars(select(MarketSyncJob))}
        assert remaining == {new_job.id, running.id}
        assert purge_market_data(seeded_session, now=NOW) == type(result)(0, 0, 0)

    def test_sweeps_abandoned_uploads(
        self, seeded_session: Session, psa10: CollectionItem, owner: User
    ) -> None:
        def image(key: str, status: str, age: timedelta) -> Image:
            return Image(
                owner_id=owner.id,
                collection_item_id=psa10.id,
                kind="front",
                storage_key=key,
                content_type="image/jpeg",
                byte_size=1,
                sha256="a" * 64,
                status=status,
                created_at=NOW - age,
            )

        seeded_session.add_all(
            [
                image("old-pending", "pending", timedelta(hours=25)),
                image("new-pending", "pending", timedelta(hours=1)),
                image("old-ready", "ready", timedelta(days=9)),
            ]
        )
        seeded_session.flush()
        result = sweep_abandoned_uploads(seeded_session, now=NOW)
        assert (result.images, result.storage_keys) == (1, ["old-pending"])
        assert {i.storage_key for i in seeded_session.scalars(select(Image))} == {
            "new-pending",
            "old-ready",
        }
