"""In-memory object store for tests and offline development."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

from card_maven.shared.storage.port import ObjectInfo, PresignedUpload


@dataclass
class _Stored:
    data: bytes
    content_type: str | None


class InMemoryObjectStore:
    def __init__(self, base_url: str = "https://storage.test/bucket") -> None:
        self.base_url = base_url
        self.objects: dict[str, _Stored] = {}
        self.deleted: list[str] = []
        self.policies: dict[str, dict[str, object]] = {}

    def presign_upload(
        self, key: str, *, content_type: str, max_bytes: int, expires_in: int
    ) -> PresignedUpload:
        self.policies[key] = {
            "content_type": content_type,
            "max_bytes": max_bytes,
            "expires_in": expires_in,
        }
        return PresignedUpload(
            url=self.base_url, fields={"key": key, "Content-Type": content_type, "policy": "test"}
        )

    def put(self, key: str, data: bytes, content_type: str | None) -> None:
        """Test helper: simulate the browser's direct upload."""
        self.objects[key] = _Stored(data, content_type)

    def head(self, key: str) -> ObjectInfo | None:
        stored = self.objects.get(key)
        return None if stored is None else ObjectInfo(len(stored.data), stored.content_type)

    def iter_bytes(self, key: str, *, chunk_size: int = 1024 * 1024) -> Iterator[bytes]:
        data = self.objects[key].data
        for start in range(0, len(data), chunk_size):
            yield data[start : start + chunk_size]

    def presign_download(self, key: str, *, expires_in: int) -> str:
        return f"{self.base_url}/{key}?expires={expires_in}"

    def delete(self, key: str) -> None:
        self.objects.pop(key, None)
        self.deleted.append(key)
