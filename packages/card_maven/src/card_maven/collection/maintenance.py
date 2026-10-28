"""Clean up photo uploads that were started but never completed."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from card_maven.collection.models import Image, ImageStatus
from card_maven.shared.clock import utcnow

ABANDONED_AFTER = timedelta(hours=24)


@dataclass(frozen=True, slots=True)
class SweepResult:
    images: int
    storage_keys: list[str]


def sweep_abandoned_uploads(session: Session, *, now: datetime | None = None) -> SweepResult:
    """Delete pending image rows older than 24 hours. Returns their storage keys
    so the caller can delete any objects after the transaction commits."""
    cutoff = (now or utcnow()) - ABANDONED_AFTER
    stale = list(
        session.scalars(
            select(Image).where(Image.status == ImageStatus.PENDING, Image.created_at < cutoff)
        )
    )
    keys = [image.storage_key for image in stale]
    for image in stale:
        session.delete(image)
    session.flush()
    return SweepResult(images=len(stale), storage_keys=keys)
