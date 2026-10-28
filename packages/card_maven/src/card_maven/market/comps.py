"""Comparable sales, current asks, and estimated values for a collector's cards.

Every query here applies the license gate (ADR-0009): only ``analytics`` sources
feed comps and estimates, and a collector sees shared sales plus their own
private manual comps. Display-only data appears only as current asks, and only
while fresh.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import ROUND_HALF_EVEN, Decimal
from typing import Literal

from sqlalchemy import ColumnElement, and_, case, func, literal, or_, select, text
from sqlalchemy.orm import Session

from card_maven.collection.models import CollectionItem
from card_maven.market.models import License, Listing, MarketSource, Sale
from card_maven.shared.clock import utcnow
from card_maven.shared.money import Money

COMPS_LIMIT = 5
ASKS_LIMIT = 5
ESTIMATE_SAMPLE = 10  # most recent exact-grade sales used for the median
ESTIMATE_WINDOW = timedelta(days=180)
ESTIMATE_CURRENCY = "USD"  # v1: estimates are in USD; other currencies are ignored


@dataclass(frozen=True, slots=True)
class Grade:
    """A condition bucket: raw, or (grader, grade)."""

    condition: str
    grader: str | None = None
    grade: Decimal | None = None

    @classmethod
    def of(cls, item: CollectionItem) -> Grade:
        if item.condition == "graded" and item.grader and item.grade is not None:
            return cls("graded", item.grader, Decimal(item.grade))
        return cls("raw")

    def label(self) -> str:
        if self.condition != "graded" or self.grade is None:
            return "Raw"
        grade = f"{self.grade.normalize():f}"
        return f"{self.grader} {grade}"


@dataclass(frozen=True, slots=True)
class Comp:
    sale: Sale
    match: Literal["exact", "nearest"]


@dataclass(frozen=True, slots=True)
class Estimate:
    value: Money
    sample_size: int
    grade: Grade
    window_days: int
    latest_sale_at: datetime


def eligible_sales(viewer_id: uuid.UUID) -> ColumnElement[bool]:
    """Sales this viewer may see as comps: analytics-licensed, matched, and
    either shared or their own private manual comps."""
    analytics = select(MarketSource.code).where(MarketSource.license == License.ANALYTICS)
    return and_(
        Sale.variant_id.is_not(None),
        Sale.source_code.in_(analytics.scalar_subquery()),
        or_(Sale.submitted_by.is_(None), Sale.submitted_by == viewer_id),
    )


def _exact(grade: Grade) -> ColumnElement[bool]:
    if grade.condition == "raw":
        return Sale.condition == "raw"
    return and_(Sale.condition == "graded", Sale.grader == grade.grader, Sale.grade == grade.grade)


def comps_for(
    session: Session, item: CollectionItem, viewer_id: uuid.UUID, limit: int = COMPS_LIMIT
) -> list[Comp]:
    """Most relevant sales: exact grade first, then nearest grade, newest first."""
    grade = Grade.of(item)
    exact = _exact(grade)
    if grade.condition == "raw":
        distance: ColumnElement[Decimal] = case((Sale.condition == "raw", 0), else_=1)
    else:
        distance = case(
            (Sale.condition == "graded", func.abs(Sale.grade - literal(grade.grade))), else_=99
        )
    rows = session.execute(
        select(Sale, exact.label("is_exact"))
        .where(Sale.variant_id == item.variant_id, eligible_sales(viewer_id))
        .order_by(case((exact, 0), else_=1), distance, Sale.sold_at.desc(), Sale.id)
        .limit(limit)
    ).all()
    return [Comp(sale, "exact" if is_exact else "nearest") for sale, is_exact in rows]


def current_asks(
    session: Session, variant_id: uuid.UUID, *, now: datetime | None = None, limit: int = ASKS_LIMIT
) -> list[Listing]:
    """Fresh listings for a variant, cheapest first. Stale rows are never shown,
    even before the purge job deletes them."""
    now = now or utcnow()
    fresh = Listing.observed_at >= literal(now) - func.make_interval(
        0, 0, 0, 0, MarketSource.max_age_hours
    )
    return list(
        session.scalars(
            select(Listing)
            .join(MarketSource, MarketSource.code == Listing.source_code)
            .where(
                Listing.variant_id == variant_id,
                MarketSource.enabled,
                or_(MarketSource.max_age_hours.is_(None), fresh),
                or_(Listing.ends_at.is_(None), Listing.ends_at > now),
            )
            .order_by(Listing.price_minor, Listing.observed_at.desc())
            .limit(limit)
        )
    )


def _median(values: Sequence[int]) -> int:
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    pair = Decimal(ordered[middle - 1] + ordered[middle]) / 2
    return int(pair.quantize(Decimal(1), rounding=ROUND_HALF_EVEN))


def estimates_for(
    session: Session,
    items: Iterable[CollectionItem],
    viewer_id: uuid.UUID,
    *,
    now: datetime | None = None,
) -> dict[uuid.UUID, Estimate]:
    """Estimated value per item: the median of up to the 10 most recent
    exact-grade eligible sales in the last 180 days. Items without such sales
    are absent from the result. One query for any number of items."""
    now = now or utcnow()
    items = list(items)
    if not items:
        return {}
    wanted = {(item.variant_id, Grade.of(item)) for item in items}
    variant_ids = {variant_id for variant_id, _ in wanted}
    ranked = (
        select(
            Sale.variant_id,
            Sale.condition,
            Sale.grader,
            Sale.grade,
            Sale.price_minor,
            Sale.sold_at,
            func.row_number()
            .over(
                partition_by=(Sale.variant_id, Sale.condition, Sale.grader, Sale.grade),
                order_by=(Sale.sold_at.desc(), Sale.id),
            )
            .label("recency"),
        )
        .where(
            Sale.variant_id.in_(variant_ids),
            eligible_sales(viewer_id),
            Sale.currency == ESTIMATE_CURRENCY,
            Sale.sold_at >= now - ESTIMATE_WINDOW,
            Sale.sold_at <= now,
        )
        .subquery()
    )
    rows = session.execute(
        select(ranked).where(ranked.c.recency <= ESTIMATE_SAMPLE).order_by(text("recency"))
    ).all()

    samples: dict[tuple[uuid.UUID, Grade], list[tuple[int, datetime]]] = {}
    for row in rows:
        grade = (
            Grade("graded", row.grader, Decimal(row.grade))
            if row.condition == "graded"
            else Grade("raw")
        )
        key = (row.variant_id, grade)
        if key in wanted:
            samples.setdefault(key, []).append((row.price_minor, row.sold_at))

    result: dict[uuid.UUID, Estimate] = {}
    for item in items:
        sample = samples.get((item.variant_id, Grade.of(item)))
        if not sample:
            continue
        result[item.id] = Estimate(
            value=Money(_median([price for price, _ in sample]), ESTIMATE_CURRENCY),
            sample_size=len(sample),
            grade=Grade.of(item),
            window_days=ESTIMATE_WINDOW.days,
            latest_sale_at=max(at for _, at in sample),
        )
    return result
