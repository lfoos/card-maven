"""Photo uploads for collection items.

Flow: ``start_upload`` issues a presigned POST and records a *pending* image;
the browser uploads straight to object storage; ``complete_upload`` verifies
the stored object (size, type, file signature, SHA-256) before the image goes
*ready* and replaces the item's previous front or back photo.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from card_maven.collection.models import CollectionItem, Image, ImageKind, ImageStatus
from card_maven.collection.service import CollectionRepository
from card_maven.shared.clock import utcnow
from card_maven.shared.errors import ConflictError, InvalidInputError, NotFoundError
from card_maven.shared.repository import OwnedRepository
from card_maven.shared.storage import ObjectStore, PresignedUpload

MAX_IMAGE_BYTES = 15 * 1024 * 1024
UPLOAD_URL_TTL_SECONDS = 15 * 60
DOWNLOAD_URL_TTL_SECONDS = 10 * 60


class UploadableKind(StrEnum):
    FRONT = ImageKind.FRONT.value
    BACK = ImageKind.BACK.value


def _is_heic(head: bytes) -> bool:
    return head[4:8] == b"ftyp" and head[8:12] in {b"heic", b"heix", b"mif1", b"msf1", b"heim"}


# Accepted types and how to recognize each from its first bytes, so a file
# renamed to .jpg (or an HTML page posing as an image) is rejected.
SIGNATURES = {
    "image/jpeg": lambda head: head.startswith(b"\xff\xd8\xff"),
    "image/png": lambda head: head.startswith(b"\x89PNG\r\n\x1a\n"),
    "image/webp": lambda head: head[:4] == b"RIFF" and head[8:12] == b"WEBP",
    "image/heic": _is_heic,
}


@dataclass(frozen=True, slots=True)
class StartedUpload:
    image: Image
    upload: PresignedUpload


@dataclass(frozen=True, slots=True)
class CompletedUpload:
    image: Image
    replaced_keys: list[str]


class ImageRepository(OwnedRepository[Image]):
    model = Image
    not_found_message = "image not found"

    def for_item(self, item_id: uuid.UUID, image_id: uuid.UUID) -> Image:
        image = self.session.scalars(
            self._scoped().where(Image.id == image_id, Image.collection_item_id == item_id)
        ).one_or_none()
        if image is None:
            raise NotFoundError(self.not_found_message)
        return image


def storage_key(owner_id: uuid.UUID, item_id: uuid.UUID, image_id: uuid.UUID) -> str:
    """Server-chosen keys: clients can never pick or traverse paths."""
    return f"users/{owner_id}/items/{item_id}/{image_id}"


class ImageService:
    def __init__(self, session: Session, owner_id: uuid.UUID, store: ObjectStore) -> None:
        self.session = session
        self.owner_id = owner_id
        self.store = store
        self.items = CollectionRepository(session, owner_id)
        self.images = ImageRepository(session, owner_id)

    def start_upload(
        self,
        item_id: uuid.UUID,
        *,
        kind: UploadableKind,
        content_type: str,
        byte_size: int,
        sha256: str,
    ) -> StartedUpload:
        item: CollectionItem = self.items.get(item_id)
        if content_type not in SIGNATURES:
            raise InvalidInputError(
                f"unsupported image type; use one of {sorted(SIGNATURES)}", field="content_type"
            )
        if not 1 <= byte_size <= MAX_IMAGE_BYTES:
            raise InvalidInputError(
                f"images must be between 1 byte and {MAX_IMAGE_BYTES // (1024 * 1024)} MB",
                field="byte_size",
            )
        image_id = uuid.uuid4()
        image = Image(
            id=image_id,
            collection_item_id=item.id,
            kind=kind.value,
            storage_key=storage_key(self.owner_id, item.id, image_id),
            content_type=content_type,
            byte_size=byte_size,
            sha256=sha256.lower(),
            status=ImageStatus.PENDING,
        )
        self.images.add(image)
        upload = self.store.presign_upload(
            image.storage_key,
            content_type=content_type,
            max_bytes=byte_size,  # exactly the declared size at most
            expires_in=UPLOAD_URL_TTL_SECONDS,
        )
        return StartedUpload(image=image, upload=upload)

    def complete_upload(self, item_id: uuid.UUID, image_id: uuid.UUID) -> CompletedUpload:
        image = self.images.for_item(item_id, image_id)
        if image.status == ImageStatus.READY:
            return CompletedUpload(image=image, replaced_keys=[])  # idempotent retry

        info = self.store.head(image.storage_key)
        if info is None:
            raise ConflictError("the file hasn't been uploaded yet")
        try:
            self._verify(image, declared_type=info.content_type, actual_size=info.size)
        except InvalidInputError:
            # Reject and clean up: the upload slot is spent, the client starts over.
            self.store.delete(image.storage_key)
            self.images.delete(image)
            raise

        replaced = list(
            self.session.scalars(
                select(Image).where(
                    Image.collection_item_id == image.collection_item_id,
                    Image.kind == image.kind,
                    Image.status == ImageStatus.READY,
                    Image.id != image.id,
                )
            )
        )
        try:
            with self.session.begin_nested():
                for old in replaced:
                    self.session.delete(old)
                self.session.flush()  # free the "one live front/back" slot first
                image.status = ImageStatus.READY
                image.uploaded_at = utcnow()
        except IntegrityError as exc:
            # A concurrent upload of the same side went live first. The client
            # can retry; this pending image (and its object) stay valid.
            raise ConflictError("another upload of this photo finished first; try again") from exc
        return CompletedUpload(image=image, replaced_keys=[old.storage_key for old in replaced])

    def _verify(self, image: Image, *, declared_type: str | None, actual_size: int) -> None:
        if actual_size != image.byte_size:
            raise InvalidInputError(
                f"uploaded file is {actual_size} bytes, expected {image.byte_size}", field="file"
            )
        if declared_type != image.content_type:
            raise InvalidInputError("uploaded file has the wrong content type", field="file")
        digest = hashlib.sha256()
        head = b""
        for chunk in self.store.iter_bytes(image.storage_key):
            if len(head) < 16:
                head += chunk[: 16 - len(head)]
            digest.update(chunk)
        if not SIGNATURES[image.content_type](head):
            raise InvalidInputError(f"file is not a valid {image.content_type}", field="file")
        if digest.hexdigest() != image.sha256:
            raise InvalidInputError("file checksum doesn't match", field="file")

    def delete(self, item_id: uuid.UUID, image_id: uuid.UUID) -> str:
        """Delete an image. Returns its storage key to remove after commit."""
        image = self.images.for_item(item_id, image_id)
        key = image.storage_key
        self.images.delete(image)
        return key

    def download_url(self, image: Image) -> str:
        return self.store.presign_download(image.storage_key, expires_in=DOWNLOAD_URL_TTL_SECONDS)
