from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Index,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, declared_attr, mapped_column

from card_maven.shared.clock import utcnow
from card_maven.shared.db import Base, TimestampMixin, UUIDPrimaryKeyMixin
from card_maven.shared.money import Money


class TrackedSet(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One (set, year) the nightly job syncs market data for.

    Keyed by natural name rather than a ``card_set`` FK: the nightly job is what
    discovers a set's cards, so the catalog row may not exist yet. Rows are
    managed by :func:`card_maven.market.tracked_sets.sync_tracked_sets` from
    ``config/tracked_sets.yaml``. Removed entries are deactivated, never deleted,
    so their history stays attributable.
    """

    __tablename__ = "tracked_set"

    sport_code: Mapped[str] = mapped_column(ForeignKey("sport.code"))
    brand_slug: Mapped[str] = mapped_column(ForeignKey("brand.slug"))
    set_name: Mapped[str] = mapped_column(String(200))
    year: Mapped[int] = mapped_column(SmallInteger)
    focus: Mapped[str | None] = mapped_column(String(200))
    active: Mapped[bool] = mapped_column(default=True, server_default=text("true"))

    __table_args__ = (
        UniqueConstraint("sport_code", "brand_slug", "set_name", "year"),
        CheckConstraint("year BETWEEN 1860 AND 2100", name="year_range"),
    )


# ---- Market data (Phase 2) ---------------------------------------------------


class License(StrEnum):
    """What a source's terms allow us to do with its data (ADR-0009)."""

    ANALYTICS = "analytics"  # comps, estimates, marts, trends
    DISPLAY_ONLY = "display_only"  # show as current asks only; purge when stale


class RecordKind(StrEnum):
    SALE = "sale"
    LISTING = "listing"


class SaleType(StrEnum):
    AUCTION = "auction"
    FIXED_PRICE = "fixed_price"
    BEST_OFFER = "best_offer"
    OTHER = "other"


class MarketSource(Base):
    __tablename__ = "market_source"

    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    license: Mapped[str] = mapped_column(String(16))
    # Display-only data older than this (since last seen) must be deleted.
    max_age_hours: Mapped[int | None]
    enabled: Mapped[bool] = mapped_column(default=True, server_default=text("true"))

    __table_args__ = (
        CheckConstraint("license IN ('analytics', 'display_only')", name="license_valid"),
        CheckConstraint(
            "license = 'analytics' OR max_age_hours IS NOT NULL", name="display_only_has_max_age"
        ),
        CheckConstraint("max_age_hours IS NULL OR max_age_hours > 0", name="max_age_positive"),
    )


class _MarketRecord:
    """Columns shared by sales and listings: identity, match, price, grade."""

    source_listing_id: Mapped[str] = mapped_column(String(128))
    match_confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    match_method: Mapped[str | None] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(500))
    price_minor: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3))
    condition: Mapped[str] = mapped_column(String(16))
    grader: Mapped[str | None] = mapped_column(String(16))
    grade: Mapped[Decimal | None] = mapped_column(Numeric(3, 1))
    url: Mapped[str | None] = mapped_column(String(2000))
    payload: Mapped[dict[str, Any]] = mapped_column(
        default=dict, server_default=text("'{}'::jsonb")
    )

    @declared_attr
    def source_code(cls) -> Mapped[str]:  # noqa: N805
        return mapped_column(ForeignKey("market_source.code"))

    @declared_attr
    def variant_id(cls) -> Mapped[uuid.UUID | None]:  # noqa: N805
        return mapped_column(ForeignKey("card_variant.id", ondelete="SET NULL"))

    @property
    def price(self) -> Money:
        return Money(self.price_minor, self.currency)


def _record_checks() -> tuple[Any, ...]:
    return (
        UniqueConstraint("source_code", "source_listing_id"),
        CheckConstraint("price_minor >= 0", name="price_non_negative"),
        CheckConstraint("condition IN ('raw', 'graded')", name="condition_valid"),
        CheckConstraint(
            "(condition = 'graded' AND grader IS NOT NULL AND grade IS NOT NULL)"
            " OR (condition = 'raw' AND grader IS NULL AND grade IS NULL)",
            name="grade_matches_condition",
        ),
        CheckConstraint(
            "match_confidence IS NULL OR (match_confidence >= 0 AND match_confidence <= 1)",
            name="confidence_range",
        ),
        CheckConstraint(
            "(variant_id IS NULL) = (match_confidence IS NULL)", name="match_has_confidence"
        ),
    )


class Sale(UUIDPrimaryKeyMixin, TimestampMixin, _MarketRecord, Base):
    """A completed sale. Shared unless ``submitted_by`` is set (a private manual comp)."""

    __tablename__ = "sale"

    sold_at: Mapped[datetime]
    sale_type: Mapped[str] = mapped_column(String(16), default=SaleType.OTHER)
    submitted_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("app_user.id", ondelete="CASCADE"), index=True
    )

    __table_args__ = (
        *_record_checks(),
        CheckConstraint(
            "sale_type IN ('auction', 'fixed_price', 'best_offer', 'other')",
            name="sale_type_valid",
        ),
        Index("ix_sale_variant_recent", "variant_id", text("sold_at DESC")),
    )


class Listing(UUIDPrimaryKeyMixin, TimestampMixin, _MarketRecord, Base):
    """A current asking price. Only matched listings are stored."""

    __tablename__ = "listing"

    buying_option: Mapped[str] = mapped_column(String(16))
    bid_count: Mapped[int | None]
    image_url: Mapped[str | None] = mapped_column(String(2000))
    observed_at: Mapped[datetime]
    ends_at: Mapped[datetime | None]

    __table_args__ = (
        *_record_checks(),
        CheckConstraint(
            "buying_option IN ('auction', 'fixed_price', 'best_offer', 'other')",
            name="buying_option_valid",
        ),
        CheckConstraint("variant_id IS NOT NULL", name="listing_is_matched"),
        Index("ix_listing_variant_recent", "variant_id", text("observed_at DESC")),
        Index("ix_listing_observed_at", "observed_at"),
    )


class SyncTargetType(StrEnum):
    VARIANT = "variant"
    TRACKED_SET = "tracked_set"


class SyncStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class MarketSyncJob(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One request to pull market data for a card variant or a tracked set."""

    __tablename__ = "market_sync_job"

    target_type: Mapped[str] = mapped_column(String(16))
    target_id: Mapped[uuid.UUID]
    status: Mapped[str] = mapped_column(String(16), default=SyncStatus.QUEUED)
    requested_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL")
    )
    attempts: Mapped[int] = mapped_column(default=0, server_default=text("0"))
    stats: Mapped[dict[str, Any]] = mapped_column(default=dict, server_default=text("'{}'::jsonb"))
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None]
    finished_at: Mapped[datetime | None]

    __table_args__ = (
        CheckConstraint("target_type IN ('variant', 'tracked_set')", name="target_type_valid"),
        CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed')", name="status_valid"
        ),
        Index("ix_market_sync_job_target", "target_type", "target_id", text("created_at DESC")),
    )


class ProcessedEvent(Base):
    """Idempotency record: a consumer has fully handled an event."""

    __tablename__ = "processed_event"

    consumer: Mapped[str] = mapped_column(String(64), primary_key=True)
    event_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    processed_at: Mapped[datetime] = mapped_column(default=utcnow, server_default=func.now())


class CatalogTerm(Base):
    """Vocabulary from a taxonomy (e.g. eBay item specifics) used by title parsing."""

    __tablename__ = "catalog_term"

    source: Mapped[str] = mapped_column(String(32), primary_key=True)
    aspect: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(String(200), primary_key=True)
