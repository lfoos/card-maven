"""Map domain objects to API response models."""

from __future__ import annotations

import uuid
from decimal import Decimal

from card_maven.catalog.models import Parallel
from card_maven.collection.images import ImageService
from card_maven.collection.models import CollectionItem, Image
from card_maven.collection.service import live_images
from card_maven.market.collector import ItemMarket
from card_maven.market.comps import Comp, Estimate
from card_maven.market.manual import MANUAL_SOURCE
from card_maven.market.models import Listing, MarketSyncJob
from card_maven.shared.money import Money
from card_maven_api.schemas import (
    AskOut,
    CardOut,
    CompOut,
    EstimateOut,
    ImageOut,
    ItemImagesOut,
    ItemMarketOut,
    ItemOut,
    MoneyOut,
    ParallelOut,
    SyncJobOut,
)


def parallel_out(parallel: Parallel) -> ParallelOut:
    return ParallelOut.model_validate(parallel)


def image_out(image: Image, images: ImageService) -> ImageOut:
    return ImageOut(
        id=image.id,
        kind=image.kind,
        url=images.download_url(image),
        content_type=image.content_type,
        byte_size=image.byte_size,
        uploaded_at=image.uploaded_at,
    )


def _money(money: Money) -> MoneyOut:
    out = MoneyOut.of(money)
    assert out is not None
    return out


def _grade(grade: Decimal | None) -> str | None:
    return None if grade is None else f"{grade:.1f}"


def _link(url: str | None) -> str | None:
    """Only web links reach the browser (no javascript:, data:, etc.)."""
    if url and url.lower().startswith(("https://", "http://")):
        return url
    return None


def estimate_out(estimate: Estimate | None) -> EstimateOut | None:
    if estimate is None:
        return None
    return EstimateOut(
        value=_money(estimate.value),
        sample_size=estimate.sample_size,
        grade=estimate.grade.label(),
        window_days=estimate.window_days,
        latest_sale_at=estimate.latest_sale_at,
    )


def comp_out(comp: Comp, viewer_id: uuid.UUID) -> CompOut:
    sale = comp.sale
    return CompOut(
        id=sale.id,
        sold_at=sale.sold_at,
        price=_money(sale.price),
        condition=sale.condition,
        grader=sale.grader,
        grade=_grade(sale.grade),
        title=sale.title,
        url=_link(sale.url),
        source=sale.source_code,
        sale_type=sale.sale_type,
        match=comp.match,
        mine=sale.source_code == MANUAL_SOURCE and sale.submitted_by == viewer_id,
    )


def ask_out(listing: Listing) -> AskOut:
    return AskOut(
        id=listing.id,
        title=listing.title,
        price=_money(listing.price),
        buying_option=listing.buying_option,
        bid_count=listing.bid_count,
        condition=listing.condition,
        grader=listing.grader,
        grade=_grade(listing.grade),
        url=_link(listing.url),
        image_url=_link(listing.image_url),
        source=listing.source_code,
        observed_at=listing.observed_at,
        ends_at=listing.ends_at,
    )


def sync_job_out(job: MarketSyncJob) -> SyncJobOut:
    return SyncJobOut.model_validate(job, from_attributes=True)


def item_market_out(market: ItemMarket, viewer_id: uuid.UUID) -> ItemMarketOut:
    return ItemMarketOut(
        item_id=market.item.id,
        grade=market.grade.label(),
        estimate=estimate_out(market.estimate),
        comps=[comp_out(c, viewer_id) for c in market.comps],
        asks=[ask_out(a) for a in market.asks],
        last_sync=sync_job_out(market.last_sync) if market.last_sync else None,
    )


def item_out(
    item: CollectionItem, images: ImageService, estimate: Estimate | None = None
) -> ItemOut:
    variant = item.variant
    card = variant.card
    card_set = card.card_set
    live = live_images(item)
    return ItemOut(
        id=item.id,
        card=CardOut(
            variant_id=variant.id,
            set_id=card_set.id,
            sport=card_set.sport_code,
            brand=card_set.brand_slug,
            year=card_set.year,
            set_name=card_set.name,
            card_number=card.card_number,
            name=card.name,
            subset=card.subset,
            team=card.team,
            players=[p.full_name for p in card.players],
            parallel=parallel_out(variant.parallel),
            is_rookie=card.is_rookie,
            is_autograph=card.is_autograph,
            is_memorabilia=card.is_memorabilia,
        ),
        condition=item.condition,
        grader=item.grader,
        grade=_grade(item.grade),
        cert_number=item.cert_number,
        serial_number=item.serial_number,
        purchase_price=MoneyOut.of(item.purchase_price),
        acquired_on=item.acquired_on,
        notes=item.notes,
        estimated_value=MoneyOut.of(estimate.value) if estimate else None,
        estimate=estimate_out(estimate),
        images=ItemImagesOut(
            front=image_out(live["front"], images) if "front" in live else None,
            back=image_out(live["back"], images) if "back" in live else None,
        ),
        created_at=item.created_at,
        updated_at=item.updated_at,
    )
