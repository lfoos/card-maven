"""Validated commands for creating and editing collection items."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated, Self

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator, model_validator

from card_maven.catalog.schemas import CardIdentity
from card_maven.collection.models import Condition, Grader
from card_maven.shared.clock import utcnow
from card_maven.shared.money import Money
from card_maven.shared.text import clean

Text = Annotated[str, AfterValidator(clean)]

MAX_PRICE = Decimal("10000000")  # $10M covers any card ever sold


class MoneyInput(BaseModel):
    """Money in JSON: a decimal *string* plus currency, so clients never send floats."""

    model_config = ConfigDict(extra="forbid")

    amount: Decimal = Field(ge=0, le=MAX_PRICE, max_digits=12, decimal_places=2)
    currency: str = Field(default="USD", pattern=r"^[A-Z]{3}$")

    @field_validator("amount", mode="before")
    @classmethod
    def _no_floats(cls, value: object) -> object:
        if isinstance(value, float):
            raise ValueError('send amounts as a string, e.g. "49.99"')
        return value

    def to_money(self) -> Money:
        return Money.from_decimal(self.amount, self.currency)


class Holding(BaseModel):
    """Facts about one physical copy: condition, grade, serial, purchase."""

    model_config = ConfigDict(extra="forbid")

    condition: Condition = Condition.RAW
    grader: Grader | None = None
    grade: Decimal | None = Field(default=None, ge=1, le=10, decimal_places=1)
    cert_number: Annotated[Text, Field(min_length=1, max_length=64)] | None = None
    serial_number: int | None = Field(default=None, ge=1, le=100_000)
    purchase_price: MoneyInput | None = None
    acquired_on: date | None = None
    notes: Annotated[Text, Field(max_length=2000)] | None = None

    @field_validator("grade")
    @classmethod
    def _half_steps(cls, value: Decimal | None) -> Decimal | None:
        if value is not None and (value * 2) % 1 != 0:
            raise ValueError("grades come in steps of 0.5")
        return value

    @field_validator("acquired_on")
    @classmethod
    def _not_future(cls, value: date | None) -> date | None:
        if value is not None and value > utcnow().date():
            raise ValueError("acquired_on can't be in the future")
        return value

    @field_validator("notes")
    @classmethod
    def _blank_notes(cls, value: str | None) -> str | None:
        return value or None

    @model_validator(mode="after")
    def _grade_matches_condition(self) -> Self:
        if self.condition == Condition.GRADED:
            if self.grader is None or self.grade is None:
                raise ValueError("graded cards need a grader and a grade")
        elif self.grader is not None or self.grade is not None or self.cert_number is not None:
            raise ValueError("raw cards can't have a grader, grade, or cert number")
        return self


class NewItem(Holding):
    card: CardIdentity


class ItemChanges(BaseModel):
    """A partial update. Only fields present in the request are changed.

    Holding fields are re-validated as a whole after merging, so a PATCH can't
    produce an invalid combination (e.g. switching to raw but keeping a grade).
    """

    model_config = ConfigDict(extra="forbid")

    card: CardIdentity | None = None
    condition: Condition | None = None
    grader: Grader | None = None
    grade: Decimal | None = None
    cert_number: str | None = None
    serial_number: int | None = None
    purchase_price: MoneyInput | None = None
    acquired_on: date | None = None
    notes: str | None = None
