"""Collector-entered sales ("manual comps"): private to the collector who adds them."""

from __future__ import annotations

import uuid
from datetime import date, datetime, time
from decimal import Decimal
from typing import Annotated, Self

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    field_validator,
    model_validator,
)
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from card_maven.collection.models import Condition, Grader
from card_maven.collection.schemas import MoneyInput
from card_maven.collection.service import CollectionRepository
from card_maven.market.models import Sale, SaleType
from card_maven.shared.clock import utcnow
from card_maven.shared.errors import InvalidInputError, NotFoundError
from card_maven.shared.text import clean

MANUAL_SOURCE = "manual"
# Bounds storage per collector; far more than comps or estimates ever use.
MAX_SALES_PER_CARD = 1000
MAX_SALES_PER_REQUEST = 200
OLDEST_SALE_YEARS = 15

Text = Annotated[str, AfterValidator(clean)]


class ManualSale(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sold_on: date
    price: MoneyInput
    condition: Condition = Condition.RAW
    grader: Grader | None = None
    grade: Decimal | None = Field(default=None, ge=1, le=10, decimal_places=1)
    sale_type: SaleType = SaleType.OTHER
    title: Annotated[Text, Field(max_length=500)] | None = None
    # Only http(s) links are kept, so a comp can't carry a javascript: URL.
    url: HttpUrl | None = None

    @field_validator("sold_on")
    @classmethod
    def _plausible_date(cls, value: date) -> date:
        today = utcnow().date()
        if value > today:
            raise ValueError("sold_on can't be in the future")
        if value.year < today.year - OLDEST_SALE_YEARS:
            raise ValueError(f"sold_on must be within the last {OLDEST_SALE_YEARS} years")
        return value

    @field_validator("grade")
    @classmethod
    def _half_steps(cls, value: Decimal | None) -> Decimal | None:
        if value is not None and (value * 2) % 1 != 0:
            raise ValueError("grades come in steps of 0.5")
        return value

    @field_validator("url")
    @classmethod
    def _http_only(cls, value: HttpUrl | None) -> HttpUrl | None:
        if value is not None and value.scheme not in ("http", "https"):
            raise ValueError("url must be http(s)")
        return value

    @model_validator(mode="after")
    def _grade_matches_condition(self) -> Self:
        if self.condition == Condition.GRADED and (self.grader is None or self.grade is None):
            raise ValueError("graded sales need a grader and a grade")
        if self.condition == Condition.RAW and (self.grader is not None or self.grade is not None):
            raise ValueError("raw sales can't have a grader or grade")
        return self


class ManualSales(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sales: list[ManualSale] = Field(min_length=1, max_length=MAX_SALES_PER_REQUEST)


def _sold_at(sold_on: date) -> datetime:
    """Midday UTC on the sale date (dates carry no time), but never in the
    future: a sale entered this morning must count right away."""
    now = utcnow()
    return min(datetime.combine(sold_on, time(12), tzinfo=now.tzinfo), now)


class ManualCompsService:
    def __init__(self, session: Session, owner_id: uuid.UUID) -> None:
        self.session = session
        self.owner_id = owner_id
        self.items = CollectionRepository(session, owner_id)

    def add(self, item_id: uuid.UUID, command: ManualSales) -> list[Sale]:
        item = self.items.get(item_id)
        existing = self.session.scalar(
            select(func.count()).where(
                Sale.submitted_by == self.owner_id,
                Sale.variant_id == item.variant_id,
                Sale.source_code == MANUAL_SOURCE,
            )
        )
        if (existing or 0) + len(command.sales) > MAX_SALES_PER_CARD:
            raise InvalidInputError(
                f"at most {MAX_SALES_PER_CARD} of your own sales per card; "
                f"this card has {existing}. Delete some first."
            )
        sales = []
        for entry in command.sales:
            money = entry.price.to_money()
            graded = entry.condition == Condition.GRADED
            sale = Sale(
                source_code=MANUAL_SOURCE,
                source_listing_id=f"manual:{uuid.uuid4()}",
                variant_id=item.variant_id,
                match_confidence=Decimal(1),
                match_method=MANUAL_SOURCE,
                title=entry.title or "Manual entry",
                price_minor=money.amount_minor,
                currency=money.currency,
                condition=entry.condition,
                grader=entry.grader if graded else None,
                grade=entry.grade if graded else None,
                url=str(entry.url) if entry.url else None,
                sold_at=_sold_at(entry.sold_on),
                sale_type=entry.sale_type,
                submitted_by=self.owner_id,
            )
            self.session.add(sale)
            sales.append(sale)
        self.session.flush()
        return sales

    def delete(self, sale_id: uuid.UUID) -> None:
        sale = self.session.scalars(
            select(Sale).where(
                Sale.id == sale_id,
                Sale.submitted_by == self.owner_id,
                Sale.source_code == MANUAL_SOURCE,
            )
        ).one_or_none()
        if sale is None:
            raise NotFoundError("sale not found")
        self.session.delete(sale)
        self.session.flush()
