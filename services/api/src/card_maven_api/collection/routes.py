from __future__ import annotations

import uuid
from collections.abc import Iterable

from flask import current_app
from flask_openapi3.blueprint import APIBlueprint
from flask_openapi3.models.tag import Tag
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from card_maven.collection.images import UPLOAD_URL_TTL_SECONDS, ImageService, UploadableKind
from card_maven.collection.models import Condition
from card_maven.collection.schemas import ItemChanges, NewItem
from card_maven.collection.service import CollectionService, ItemFilters, Sort
from card_maven.shared.errors import DependencyUnavailableError
from card_maven.shared.logging import get_logger
from card_maven.shared.storage import ObjectStore
from card_maven_api.auth.decorators import current_user, require_user
from card_maven_api.db import transaction
from card_maven_api.extensions import api_context
from card_maven_api.openapi import BEARER, NOT_FOUND, PROTECTED_RESPONSES
from card_maven_api.presenters import image_out, item_out
from card_maven_api.rate_limits import UPLOAD_START_LIMIT, WRITE_LIMIT, rate_limited
from card_maven_api.schemas import (
    ImageOut,
    ItemOut,
    ItemPageOut,
    PresignedPostOut,
    UploadStartedOut,
)

log = get_logger(__name__)

TAG = Tag(name="collection", description="A collector's cards and their photos")
bp = APIBlueprint(
    "collection",
    __name__,
    url_prefix="/api/v1/collection",
    abp_tags=[TAG],
    abp_security=BEARER,
    abp_responses=PROTECTED_RESPONSES,
)


class ItemPath(BaseModel):
    item_id: uuid.UUID


class ImagePath(BaseModel):
    item_id: uuid.UUID
    image_id: uuid.UUID


class ListQuery(BaseModel):
    sport: str | None = Field(default=None, max_length=32)
    year: int | None = Field(default=None, ge=1860, le=2100)
    brand: str | None = Field(default=None, max_length=128)
    condition: Condition | None = None
    q: str | None = Field(default=None, max_length=100, description="Free-text search")
    sort: Sort = Sort.NEWEST
    cursor: str | None = Field(default=None, max_length=500)
    limit: int = Field(default=24, ge=1, le=100)


class StartUpload(BaseModel):
    kind: UploadableKind
    content_type: str = Field(examples=["image/jpeg"], max_length=100)
    byte_size: int = Field(ge=1)
    sha256: str = Field(pattern=r"^[0-9a-fA-F]{64}$", description="Hex SHA-256 of the file")


def _store() -> ObjectStore:
    return api_context(current_app).object_store


def _services(session: Session) -> tuple[CollectionService, ImageService]:
    owner = current_user().id
    return CollectionService(session, owner), ImageService(session, owner, _store())


def _delete_objects(keys: Iterable[str]) -> None:
    """Best-effort cleanup after the database commit. A failure leaves an orphan
    (logged with its key) rather than failing a request that already succeeded."""
    store = _store()
    for key in keys:
        try:
            store.delete(key)
        except DependencyUnavailableError:
            log.warning("orphaned_object", storage_key=key)


@bp.get("/items", summary="List my collection", responses={200: ItemPageOut})
@require_user
def list_items(query: ListQuery) -> dict[str, object]:
    with transaction() as session:
        items, images = _services(session)
        page = items.page(
            ItemFilters(
                sport=query.sport,
                year=query.year,
                brand=query.brand,
                condition=query.condition,
                query=query.q,
            ),
            sort=query.sort,
            cursor=query.cursor,
            limit=query.limit,
        )
        out = ItemPageOut(
            items=[item_out(i, images) for i in page.items], next_cursor=page.next_cursor
        )
    return out.model_dump(mode="json")


@bp.post("/items", summary="Add a card", responses={201: ItemOut})
@rate_limited(WRITE_LIMIT)
@require_user
def create_item(body: NewItem) -> tuple[dict[str, object], int]:
    with transaction() as session:
        items, images = _services(session)
        out = item_out(items.create(body), images)
    return out.model_dump(mode="json"), 201


@bp.get("/items/<uuid:item_id>", summary="Get a card", responses={200: ItemOut, **NOT_FOUND})
@require_user
def get_item(path: ItemPath) -> dict[str, object]:
    with transaction() as session:
        items, images = _services(session)
        out = item_out(items.get(path.item_id), images)
    return out.model_dump(mode="json")


@bp.patch(
    "/items/<uuid:item_id>",
    summary="Edit a card",
    description="Only fields present in the body change. Send `null` to clear a field.",
    responses={200: ItemOut, **NOT_FOUND},
)
@rate_limited(WRITE_LIMIT)
@require_user
def update_item(path: ItemPath, body: ItemChanges) -> dict[str, object]:
    with transaction() as session:
        items, images = _services(session)
        out = item_out(items.update(path.item_id, body), images)
    return out.model_dump(mode="json")


@bp.delete(
    "/items/<uuid:item_id>",
    summary="Delete a card and its photos",
    responses={204: None, **NOT_FOUND},
)
@rate_limited(WRITE_LIMIT)
@require_user
def delete_item(path: ItemPath) -> tuple[str, int]:
    with transaction() as session:
        items, _ = _services(session)
        keys = items.delete(path.item_id)
    _delete_objects(keys)
    return "", 204


@bp.post(
    "/items/<uuid:item_id>/images",
    summary="Start a photo upload",
    description="Returns a presigned POST. Upload the file directly to storage, then call "
    "`.../images/{image_id}/complete`. The policy pins the key, content type, and size.",
    responses={201: UploadStartedOut, **NOT_FOUND},
)
@rate_limited(UPLOAD_START_LIMIT)
@require_user
def start_upload(path: ItemPath, body: StartUpload) -> tuple[dict[str, object], int]:
    with transaction() as session:
        _, images = _services(session)
        started = images.start_upload(
            path.item_id,
            kind=body.kind,
            content_type=body.content_type,
            byte_size=body.byte_size,
            sha256=body.sha256,
        )
        out = UploadStartedOut(
            image_id=started.image.id,
            upload=PresignedPostOut(url=started.upload.url, fields=started.upload.fields),
            expires_in=UPLOAD_URL_TTL_SECONDS,
        )
    return out.model_dump(mode="json"), 201


@bp.post(
    "/items/<uuid:item_id>/images/<uuid:image_id>/complete",
    summary="Finish a photo upload",
    description="Verifies the stored file (size, type, signature, SHA-256) and makes it the "
    "card's front or back photo, replacing the previous one.",
    responses={200: ImageOut, 409: None, **NOT_FOUND},
)
@rate_limited(WRITE_LIMIT)
@require_user
def complete_upload(path: ImagePath) -> dict[str, object]:
    with transaction() as session:
        _, images = _services(session)
        done = images.complete_upload(path.item_id, path.image_id)
        out = image_out(done.image, images)
    _delete_objects(done.replaced_keys)
    return out.model_dump(mode="json")


@bp.delete(
    "/items/<uuid:item_id>/images/<uuid:image_id>",
    summary="Remove a photo",
    responses={204: None, **NOT_FOUND},
)
@rate_limited(WRITE_LIMIT)
@require_user
def delete_image(path: ImagePath) -> tuple[str, int]:
    with transaction() as session:
        _, images = _services(session)
        key = images.delete(path.item_id, path.image_id)
    _delete_objects([key])
    return "", 204
