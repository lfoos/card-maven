import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy.orm import Session

from card_maven.collection.models import CollectionItem
from card_maven.identity.models import User
from card_maven.market.collector import CollectorMarket
from card_maven.market.manual import ManualSales
from card_maven.market.models import Listing, MarketSyncJob, Sale
from card_maven.shared.errors import NotFoundError

pytestmark = pytest.mark.db

NOW = datetime.now(UTC)
TODAY = NOW.date().isoformat()


@pytest.fixture
def owner(make_user: Callable[[str], User]) -> User:
    return make_user("owner")


@pytest.fixture
def item(
    owner: User, make_item: Callable[..., CollectionItem], card_specs: dict[str, dict[str, Any]]
) -> CollectionItem:
    return make_item(owner, card_specs["skenes_base"])


def sale(session: Session, item: CollectionItem, price: int, days: int, **extra: Any) -> Sale:
    row = Sale(
        source_code="fixture",
        source_listing_id=f"t-{uuid.uuid4()}",
        title="t",
        variant_id=item.variant_id,
        match_confidence=Decimal(1),
        match_method="test",
        price_minor=price,
        currency="USD",
        condition="raw",
        sold_at=NOW - timedelta(days=days),
        **extra,
    )
    session.add(row)
    session.flush()
    return row


def test_overview_combines_estimate_comps_asks_and_last_job(
    seeded_session: Session, owner: User, item: CollectionItem
) -> None:
    for price, days in [(1000, 1), (1400, 2), (1200, 3)]:
        sale(seeded_session, item, price, days)
    seeded_session.add(
        Listing(
            source_code="ebay_browse",
            source_listing_id="v1|1|0",
            title="ask",
            variant_id=item.variant_id,
            match_confidence=Decimal("0.9"),
            match_method="rules_v1",
            buying_option="fixed_price",
            price_minor=1500,
            currency="USD",
            condition="raw",
            observed_at=NOW,
        )
    )
    market = CollectorMarket(seeded_session, owner.id)
    job = market.refresh(item.id).job

    view = market.overview(item.id)
    assert view.grade.label() == "Raw"
    assert view.estimate is not None
    assert view.estimate.value.amount_minor == 1200
    assert [c.sale.price_minor for c in view.comps] == [1000, 1400, 1200]
    assert [a.price_minor for a in view.asks] == [1500]
    assert view.last_sync is not None
    assert view.last_sync.id == job.id


def test_overview_without_market_data(
    seeded_session: Session, owner: User, item: CollectionItem
) -> None:
    view = CollectorMarket(seeded_session, owner.id).overview(item.id)
    assert (view.estimate, view.comps, view.asks, view.last_sync) == (None, [], [], None)


def test_other_collectors_items_are_not_found(
    seeded_session: Session, item: CollectionItem, make_user: Callable[[str], User]
) -> None:
    stranger = CollectorMarket(seeded_session, make_user("stranger").id)
    with pytest.raises(NotFoundError):
        stranger.overview(item.id)
    with pytest.raises(NotFoundError):
        stranger.refresh(item.id)
    with pytest.raises(NotFoundError):
        stranger.add_sales(
            item.id,
            ManualSales.model_validate(
                {
                    "sales": [
                        {
                            "sold_on": TODAY,
                            "price": {"amount": "5", "currency": "USD"},
                            "condition": "raw",
                        }
                    ]
                }
            ),
        )


def test_refresh_is_shared_and_jobs_are_visible_to_holders_only(
    seeded_session: Session,
    owner: User,
    item: CollectionItem,
    make_user: Callable[[str], User],
    make_item: Callable[..., CollectionItem],
    card_specs: dict[str, dict[str, Any]],
) -> None:
    other = make_user("other")
    other_item = make_item(other, card_specs["skenes_base"])
    first = CollectorMarket(seeded_session, owner.id).refresh(item.id)
    second = CollectorMarket(seeded_session, other.id).refresh(other_item.id)
    assert first.created
    assert not second.created
    assert second.job.id == first.job.id
    # Both holders may poll it; a collector without the card may not.
    assert CollectorMarket(seeded_session, other.id).job(first.job.id).id == first.job.id
    with pytest.raises(NotFoundError):
        CollectorMarket(seeded_session, make_user("nobody").id).job(first.job.id)


def test_tracked_set_and_unknown_jobs_are_hidden(seeded_session: Session, owner: User) -> None:
    tracked = MarketSyncJob(id=uuid.uuid4(), target_type="tracked_set", target_id=uuid.uuid4())
    seeded_session.add(tracked)
    seeded_session.flush()
    market = CollectorMarket(seeded_session, owner.id)
    for job_id in (tracked.id, uuid.uuid4()):
        with pytest.raises(NotFoundError):
            market.job(job_id)


def test_manual_sales_round_trip(
    seeded_session: Session, owner: User, item: CollectionItem
) -> None:
    market = CollectorMarket(seeded_session, owner.id)
    [added] = market.add_sales(
        item.id,
        ManualSales.model_validate(
            {
                "sales": [
                    {
                        "sold_on": TODAY,
                        "price": {"amount": "12.34", "currency": "USD"},
                        "condition": "raw",
                    }
                ]
            }
        ),
    )
    assert [c.sale.id for c in market.overview(item.id).comps] == [added.id]
    assert market.estimates([item])[item.id].value.amount_minor == 1234
    market.delete_sale(added.id)
    assert market.overview(item.id).comps == []


def test_sale_entered_before_noon_utc_counts_immediately(
    seeded_session: Session, owner: User, item: CollectionItem, monkeypatch: pytest.MonkeyPatch
) -> None:
    morning = datetime(2026, 10, 27, 8, 30, tzinfo=UTC)
    monkeypatch.setattr("card_maven.market.manual.utcnow", lambda: morning)
    [added] = CollectorMarket(seeded_session, owner.id).add_sales(
        item.id,
        ManualSales.model_validate(
            {
                "sales": [
                    {
                        "sold_on": "2026-10-27",
                        "price": {"amount": "9", "currency": "USD"},
                        "condition": "raw",
                    }
                ]
            }
        ),
    )
    assert added.sold_at == morning
    yesterday = CollectorMarket(seeded_session, owner.id).add_sales(
        item.id,
        ManualSales.model_validate(
            {
                "sales": [
                    {
                        "sold_on": "2026-10-26",
                        "price": {"amount": "9", "currency": "USD"},
                        "condition": "raw",
                    }
                ]
            }
        ),
    )
    assert yesterday[0].sold_at == datetime(2026, 10, 26, 12, tzinfo=UTC)
