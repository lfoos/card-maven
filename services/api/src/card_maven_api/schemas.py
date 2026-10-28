"""API response models (request models come from the domain package)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Literal

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


class EstimateOut(BaseModel):
    value: MoneyOut
    sample_size: int = Field(description="Sales in the median (at most 10)")
    grade: str = Field(description='The grade compared, e.g. "PSA 10" or "Raw"')
    window_days: int = Field(description="Only sales within this many days count")
    latest_sale_at: datetime


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
        description="Median of recent sales at this card's exact grade; null without any. "
        "Same as `estimate.value`."
    )
    estimate: EstimateOut | None = Field(description="The estimate and what it's based on")
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


class CompOut(BaseModel):
    """A completed sale of this card (analytics-licensed sources only)."""

    id: uuid.UUID
    sold_at: datetime
    price: MoneyOut
    condition: str
    grader: str | None
    grade: str | None
    title: str
    url: str | None = Field(description="Link to the sale, when the source has one (http/https)")
    source: str
    sale_type: str | None
    match: Literal["exact", "nearest"] = Field(
        description="`exact`: same grader and grade (or both raw). `nearest`: closest grade."
    )
    mine: bool = Field(description="A manual sale you entered (you can delete it)")


class AskOut(BaseModel):
    """A current listing: an asking price, not a sale. Never used for estimates."""

    id: uuid.UUID
    title: str
    price: MoneyOut
    buying_option: str
    bid_count: int | None
    condition: str
    grader: str | None
    grade: str | None
    url: str | None = Field(description="Listing link (an affiliate link when configured)")
    image_url: str | None
    source: str
    observed_at: datetime = Field(description="When this price was last seen")
    ends_at: datetime | None


class SyncJobOut(BaseModel):
    id: uuid.UUID
    status: Literal["queued", "running", "succeeded", "failed"]
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    error: str | None


class ItemMarketOut(BaseModel):
    item_id: uuid.UUID
    grade: str = Field(description='How the item is compared, e.g. "PSA 10" or "Raw"')
    estimate: EstimateOut | None
    comps: list[CompOut] = Field(description="Up to 5: exact grade first, then nearest, newest")
    asks: list[AskOut] = Field(description="Up to 5 current listings, cheapest first")
    last_sync: SyncJobOut | None


class SalesAddedOut(BaseModel):
    added: int
    market: ItemMarketOut
