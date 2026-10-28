"""Retention: delete display-only data once its license says it's stale."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import and_, delete, func, literal, or_, select
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from card_maven.market.models import (
    Listing,
    MarketSource,
    MarketSyncJob,
    ProcessedEvent,
    SyncStatus,
)
from card_maven.shared.clock import utcnow

JOB_RETENTION = timedelta(days=30)


@dataclass(frozen=True, slots=True)
class PurgeResult:
    listings: int
    jobs: int
    processed_events: int = 0


def purge_market_data(session: Session, *, now: datetime | None = None) -> PurgeResult:
    """Delete listings not re-observed within their source's ``max_age_hours``
    (or past their end date); sync jobs older than 30 days, including ones
    abandoned while queued or running; and idempotency markers older than
    that (Kafka retention is far shorter, so a redelivery can't be that old)."""
    now = now or utcnow()
    stale_sources = select(MarketSource.code).where(MarketSource.max_age_hours.is_not(None))
    max_age = (
        select(MarketSource.max_age_hours)
        .where(MarketSource.code == Listing.source_code)
        .scalar_subquery()
    )
    listings: CursorResult[Any] = session.execute(  # type: ignore[assignment]
        delete(Listing).where(
            Listing.source_code.in_(stale_sources.scalar_subquery()),
            or_(
                Listing.observed_at < literal(now) - func.make_interval(0, 0, 0, 0, max_age),
                Listing.ends_at <= now,
            ),
        )
    )
    jobs: CursorResult[Any] = session.execute(  # type: ignore[assignment]
        delete(MarketSyncJob).where(
            or_(
                and_(
                    MarketSyncJob.status.in_([SyncStatus.SUCCEEDED, SyncStatus.FAILED]),
                    MarketSyncJob.finished_at < now - JOB_RETENTION,
                ),
                MarketSyncJob.created_at < now - JOB_RETENTION,
            )
        )
    )
    events: CursorResult[Any] = session.execute(  # type: ignore[assignment]
        delete(ProcessedEvent).where(ProcessedEvent.processed_at < now - JOB_RETENTION)
    )
    return PurgeResult(
        listings=listings.rowcount or 0,
        jobs=jobs.rowcount or 0,
        processed_events=events.rowcount or 0,
    )
