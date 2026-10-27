"""Map domain objects to API response models."""

from __future__ import annotations

from card_maven.catalog.models import Parallel
from card_maven.collection.images import ImageService
from card_maven.collection.models import CollectionItem, Image
from card_maven.collection.service import live_images
from card_maven_api.schemas import (
    CardOut,
    ImageOut,
    ItemImagesOut,
    ItemOut,
    MoneyOut,
    ParallelOut,
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


def item_out(item: CollectionItem, images: ImageService) -> ItemOut:
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
        grade=None if item.grade is None else f"{item.grade:.1f}",
        cert_number=item.cert_number,
        serial_number=item.serial_number,
        purchase_price=MoneyOut.of(item.purchase_price),
        acquired_on=item.acquired_on,
        notes=item.notes,
        estimated_value=None,
        images=ItemImagesOut(
            front=image_out(live["front"], images) if "front" in live else None,
            back=image_out(live["back"], images) if "back" in live else None,
        ),
        created_at=item.created_at,
        updated_at=item.updated_at,
    )
