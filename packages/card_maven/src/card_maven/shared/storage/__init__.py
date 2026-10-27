"""Object storage port. Adapters: :mod:`.s3` (AWS S3, SeaweedFS) and :mod:`.memory` (tests)."""

from card_maven.shared.storage.port import ObjectInfo, ObjectStore, PresignedUpload

__all__ = ["ObjectInfo", "ObjectStore", "PresignedUpload"]
