"""API response models (request models come from the domain package)."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from card_maven.shared.money import Money


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class MoneyOut(ApiModel):
    amount: str = Field(description='Decimal string, e.g. "49.99"', examples=["49.99"])
    currency: str = Field(examples=["USD"])

    @classmethod
    def of(cls, money: Money | None) -> MoneyOut | None:
        if money is None:
            return None
        return cls(amount=f"{money.to_decimal():f}", currency=money.currency)


class ProblemOut(BaseModel):
    """RFC 9457 problem details."""

    type: str
    title: str
    status: int
    code: str
    detail: str | None = None
    request_id: str | None = None


class FieldError(BaseModel):
    loc: str = Field(description="Dotted path to the offending field, e.g. card.year")
    message: str


class ValidationProblemOut(ProblemOut):
    errors: list[FieldError] = []


class MeOut(ApiModel):
    id: uuid.UUID
    email: str | None
    display_name: str | None
    roles: list[str]


class ParallelOut(ApiModel):
    id: uuid.UUID
    name: str
    subset: str | None
    print_run: int | None
    color: str | None


class CardOut(ApiModel):
    variant_id: uuid.UUID
    set_id: uuid.UUID
    sport: str
    brand: str
    year: int
    set_name: str
    card_number: str
    name: str
    subset: str | None
    team: str | None
    players: list[str]
    parallel: ParallelOut
    is_rookie: bool
    is_autograph: bool
    is_memorabilia: bool


class ImageOut(ApiModel):
    id: uuid.UUID
    kind: str
    url: str = Field(description="Short-lived download URL (10 minutes)")
    content_type: str
    byte_size: int
    uploaded_at: datetime | None


class ItemImagesOut(BaseModel):
    front: ImageOut | None = None
    back: ImageOut | None = None


class ItemOut(ApiModel):
    id: uuid.UUID
    card: CardOut
    condition: str
    grader: str | None
    grade: str | None = Field(description='Decimal string, e.g. "9.5"')
    cert_number: str | None
    serial_number: int | None
    purchase_price: MoneyOut | None
    acquired_on: date | None
    notes: str | None
    estimated_value: MoneyOut | None = Field(
        description="Market-based estimate. Null until market data is available (Phase 2)."
    )
    images: ItemImagesOut
    created_at: datetime
    updated_at: datetime


class ItemPageOut(BaseModel):
    items: list[ItemOut]
    next_cursor: str | None = Field(
        description="Pass as `cursor` for the next page; null at the end"
    )


class SetSuggestionOut(ApiModel):
    id: uuid.UUID
    sport: str
    brand: str
    year: int
    name: str


class PlayerSuggestionOut(ApiModel):
    id: uuid.UUID
    sport: str
    full_name: str


class PresignedPostOut(BaseModel):
    url: str
    fields: dict[str, str] = Field(description="Send these as multipart form fields, then the file")


class UploadStartedOut(BaseModel):
    image_id: uuid.UUID
    upload: PresignedPostOut
    expires_in: int = Field(description="Seconds the upload is valid")
