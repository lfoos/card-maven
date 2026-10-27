from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True, slots=True)
class PresignedUpload:
    """A browser-usable upload: POST multipart ``fields`` plus the file to ``url``.

    The signed policy pins the key, content type, and size range, so the
    client can upload exactly one file of the declared shape and nothing else.
    """

    url: str
    fields: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ObjectInfo:
    size: int
    content_type: str | None


class ObjectStore(Protocol):
    def presign_upload(
        self, key: str, *, content_type: str, max_bytes: int, expires_in: int
    ) -> PresignedUpload: ...

    def head(self, key: str) -> ObjectInfo | None:
        """Metadata for ``key``, or ``None`` if it doesn't exist."""

    def iter_bytes(self, key: str, *, chunk_size: int = 1024 * 1024) -> Iterator[bytes]: ...

    def presign_download(self, key: str, *, expires_in: int) -> str: ...

    def delete(self, key: str) -> None:
        """Delete ``key``. Deleting a missing key is not an error."""
