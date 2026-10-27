import hashlib
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from card_maven.collection.images import (
    MAX_IMAGE_BYTES,
    SIGNATURES,
    ImageService,
    UploadableKind,
    storage_key,
)
from card_maven.collection.models import Image
from card_maven.collection.schemas import NewItem
from card_maven.collection.service import CollectionService, live_images
from card_maven.identity.models import User
from card_maven.shared.errors import ConflictError, InvalidInputError, NotFoundError
from card_maven.shared.storage.memory import InMemoryObjectStore

pytestmark = pytest.mark.db

JPEG = b"\xff\xd8\xff\xe0" + b"jpeg-body" * 50
PNG = b"\x89PNG\r\n\x1a\n" + b"png-body" * 50
WEBP = b"RIFF\x00\x00\x00\x00WEBPVP8 " + b"webp" * 20
HEIC = b"\x00\x00\x00\x18ftypheic" + b"heic" * 20


@pytest.fixture
def owner(seeded_session: Session) -> User:
    user = User(idp_issuer="https://idp.test", idp_subject="owner")
    seeded_session.add(user)
    seeded_session.flush()
    return user


@pytest.fixture
def store() -> InMemoryObjectStore:
    return InMemoryObjectStore()


@pytest.fixture
def item_id(seeded_session: Session, owner: User) -> uuid.UUID:
    item = CollectionService(seeded_session, owner.id).create(
        NewItem.model_validate(
            {
                "card": {
                    "sport": "baseball",
                    "brand": "Topps",
                    "year": 2025,
                    "set_name": "Topps Chrome",
                    "card_number": "1",
                    "name": "Paul Skenes",
                    "players": ["Paul Skenes"],
                }
            }
        )
    )
    return item.id


@pytest.fixture
def images(seeded_session: Session, owner: User, store: InMemoryObjectStore) -> ImageService:
    return ImageService(seeded_session, owner.id, store)


def start(
    images: ImageService,
    item_id: uuid.UUID,
    data: bytes = JPEG,
    *,
    kind: str = "front",
    content_type: str = "image/jpeg",
    size: int | None = None,
    sha: str | None = None,
):
    return images.start_upload(
        item_id,
        kind=UploadableKind(kind),
        content_type=content_type,
        byte_size=len(data) if size is None else size,
        sha256=sha or hashlib.sha256(data).hexdigest(),
    )


class TestStartUpload:
    def test_issues_policy_for_server_chosen_key(
        self, images: ImageService, item_id: uuid.UUID, owner: User, store: InMemoryObjectStore
    ) -> None:
        started = start(images, item_id)
        image = started.image
        assert image.status == "pending"
        assert image.storage_key == storage_key(owner.id, item_id, image.id)
        assert store.policies[image.storage_key] == {
            "content_type": "image/jpeg",
            "max_bytes": len(JPEG),
            "expires_in": 900,
        }
        assert started.upload.fields["key"] == image.storage_key

    @pytest.mark.parametrize(
        ("content_type", "size", "field"),
        [
            ("image/gif", 10, "content_type"),
            ("text/html", 10, "content_type"),
            ("image/jpeg", 0, "byte_size"),
            ("image/jpeg", MAX_IMAGE_BYTES + 1, "byte_size"),
        ],
    )
    def test_rejects_bad_declarations(
        self, images: ImageService, item_id: uuid.UUID, content_type: str, size: int, field: str
    ) -> None:
        with pytest.raises(InvalidInputError) as excinfo:
            start(images, item_id, content_type=content_type, size=size)
        assert excinfo.value.extra == {"field": field}

    def test_other_users_item(
        self, seeded_session: Session, item_id: uuid.UUID, store: InMemoryObjectStore
    ) -> None:
        stranger = User(idp_issuer="https://idp.test", idp_subject="stranger")
        seeded_session.add(stranger)
        seeded_session.flush()
        with pytest.raises(NotFoundError):
            start(ImageService(seeded_session, stranger.id, store), item_id)


class TestCompleteUpload:
    @pytest.mark.parametrize(
        ("data", "content_type"),
        [(JPEG, "image/jpeg"), (PNG, "image/png"), (WEBP, "image/webp"), (HEIC, "image/heic")],
    )
    def test_verified_upload_goes_live(
        self,
        seeded_session: Session,
        images: ImageService,
        item_id: uuid.UUID,
        store: InMemoryObjectStore,
        data: bytes,
        content_type: str,
    ) -> None:
        started = start(images, item_id, data, content_type=content_type)
        store.put(started.image.storage_key, data, content_type)
        done = images.complete_upload(item_id, started.image.id)
        assert done.image.status == "ready"
        assert done.image.uploaded_at is not None
        assert done.replaced_keys == []

    def test_replaces_previous_photo_of_same_side(
        self,
        seeded_session: Session,
        images: ImageService,
        item_id: uuid.UUID,
        store: InMemoryObjectStore,
    ) -> None:
        keys = []
        for _ in range(2):
            started = start(images, item_id)
            store.put(started.image.storage_key, JPEG, "image/jpeg")
            done = images.complete_upload(item_id, started.image.id)
            keys.append((started.image.storage_key, done.replaced_keys))
        assert keys[1][1] == [keys[0][0]]
        back = start(images, item_id, kind="back")
        store.put(back.image.storage_key, JPEG, "image/jpeg")
        assert images.complete_upload(item_id, back.image.id).replaced_keys == []  # front untouched
        item = CollectionService(seeded_session, images.owner_id).get(item_id)
        assert set(live_images(item)) == {"front", "back"}

    def test_completion_is_idempotent(
        self, images: ImageService, item_id: uuid.UUID, store: InMemoryObjectStore
    ) -> None:
        started = start(images, item_id)
        store.put(started.image.storage_key, JPEG, "image/jpeg")
        images.complete_upload(item_id, started.image.id)
        assert images.complete_upload(item_id, started.image.id).replaced_keys == []

    def test_not_uploaded_yet(self, images: ImageService, item_id: uuid.UUID) -> None:
        started = start(images, item_id)
        with pytest.raises(ConflictError, match="hasn't been uploaded"):
            images.complete_upload(item_id, started.image.id)

    @pytest.mark.parametrize(
        ("stored", "stored_type", "declared_sha", "message"),
        [
            (JPEG[:-1], "image/jpeg", None, "expected"),
            (JPEG, "image/png", None, "wrong content type"),
            (b"<html>" + JPEG[6:], "image/jpeg", None, "not a valid image/jpeg"),
            (JPEG, "image/jpeg", "0" * 64, "checksum"),
        ],
    )
    def test_rejects_and_cleans_up_bad_uploads(
        self,
        seeded_session: Session,
        images: ImageService,
        item_id: uuid.UUID,
        store: InMemoryObjectStore,
        stored: bytes,
        stored_type: str,
        declared_sha: str | None,
        message: str,
    ) -> None:
        started = start(images, item_id, sha=declared_sha)
        key = started.image.storage_key
        store.put(key, stored, stored_type)
        with pytest.raises(InvalidInputError, match=message):
            images.complete_upload(item_id, started.image.id)
        assert key in store.deleted
        assert seeded_session.scalars(select(Image).where(Image.storage_key == key)).all() == []

    def test_image_must_belong_to_the_item(
        self, seeded_session: Session, images: ImageService, item_id: uuid.UUID
    ) -> None:
        started = start(images, item_id)
        with pytest.raises(NotFoundError, match="image not found"):
            images.complete_upload(uuid.uuid4(), started.image.id)

    def test_large_files_are_hashed_in_chunks(
        self, images: ImageService, item_id: uuid.UUID, store: InMemoryObjectStore
    ) -> None:
        data = b"\xff\xd8\xff" + bytes(3 * 1024 * 1024)
        started = start(images, item_id, data)
        store.put(started.image.storage_key, data, "image/jpeg")
        assert images.complete_upload(item_id, started.image.id).image.status == "ready"


def test_delete_and_download(
    images: ImageService, item_id: uuid.UUID, store: InMemoryObjectStore
) -> None:
    started = start(images, item_id)
    assert images.download_url(started.image).endswith("expires=600")
    assert images.delete(item_id, started.image.id) == started.image.storage_key
    with pytest.raises(NotFoundError):
        images.delete(item_id, started.image.id)


@pytest.mark.parametrize(
    ("content_type", "good", "bad"),
    [
        ("image/jpeg", JPEG, PNG),
        ("image/png", PNG, JPEG),
        ("image/webp", WEBP, b"RIFF\x00\x00\x00\x00WAVE"),
        ("image/heic", HEIC, b"\x00\x00\x00\x18ftypmp42"),
    ],
)
def test_signatures(content_type: str, good: bytes, bad: bytes) -> None:
    assert SIGNATURES[content_type](good[:16])
    assert not SIGNATURES[content_type](bad[:16])


def test_concurrent_completions_for_the_same_side_conflict_cleanly(
    seeded_session: Session,
    images: ImageService,
    item_id: uuid.UUID,
    store: InMemoryObjectStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """QA: two uploads of the same side finishing at once. The loser must get a
    409 (retryable), not a 500 from the unique index."""
    first = start(images, item_id)
    second = start(images, item_id)
    for s in (first, second):
        store.put(s.image.storage_key, JPEG, "image/jpeg")
    images.complete_upload(item_id, first.image.id)

    # Simulate the race: the second request didn't see the first's live photo.
    real_scalars = seeded_session.scalars
    calls = {"n": 0}

    def stale(statement, *args, **kwargs):  # type: ignore[no-untyped-def]
        calls["n"] += 1
        result = real_scalars(statement, *args, **kwargs)
        return [] if "image.status" in str(statement) and calls["n"] > 1 else result

    monkeypatch.setattr(seeded_session, "scalars", stale)
    with pytest.raises(ConflictError, match="another upload"):
        images.complete_upload(item_id, second.image.id)
