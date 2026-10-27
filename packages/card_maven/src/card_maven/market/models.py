from __future__ import annotations

from sqlalchemy import CheckConstraint, ForeignKey, SmallInteger, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from card_maven.shared.db import Base, TimestampMixin, UUIDPrimaryKeyMixin


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
