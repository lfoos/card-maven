from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from card_maven.catalog.models import CardVariant
from card_maven.shared.db import Base, OwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin
from card_maven.shared.money import Money


class Condition(StrEnum):
    RAW = "raw"
    GRADED = "graded"


class Grader(StrEnum):
    """Known grading companies. Stored as a string so adding one needs no migration."""

    PSA = "PSA"
    BGS = "BGS"
    SGC = "SGC"
    CGC = "CGC"
    TAG = "TAG"


class ImageKind(StrEnum):
    FRONT = "front"
    BACK = "back"
    SCAN_SOURCE = "scan_source"
    CROP = "crop"


class CollectionItem(UUIDPrimaryKeyMixin, TimestampMixin, OwnedMixin, Base):
    """One physical card a collector owns."""

    __tablename__ = "collection_item"

    variant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("card_variant.id", ondelete="RESTRICT"), index=True
    )
    serial_number: Mapped[int | None] = mapped_column(Integer)  # e.g. 123 of /499
    condition: Mapped[str] = mapped_column(
        String(16), default=Condition.RAW, server_default=Condition.RAW.value
    )
    grader: Mapped[str | None] = mapped_column(String(16))
    grade: Mapped[Decimal | None] = mapped_column(Numeric(3, 1))
    cert_number: Mapped[str | None] = mapped_column(String(64))
    purchase_price_minor: Mapped[int | None] = mapped_column(BigInteger)
    purchase_currency: Mapped[str | None] = mapped_column(String(3))
    acquired_on: Mapped[date | None]
    notes: Mapped[str | None] = mapped_column(Text)

    variant: Mapped[CardVariant] = relationship()
    images: Mapped[list[Image]] = relationship(
        back_populates="collection_item", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint("condition IN ('raw', 'graded')", name="condition_valid"),
        CheckConstraint(
            "(condition = 'graded' AND grader IS NOT NULL AND grade IS NOT NULL)"
            " OR (condition = 'raw' AND grader IS NULL AND grade IS NULL AND cert_number IS NULL)",
            name="grade_matches_condition",
        ),
        CheckConstraint("grade IS NULL OR (grade >= 1 AND grade <= 10)", name="grade_range"),
        CheckConstraint("serial_number IS NULL OR serial_number > 0", name="serial_positive"),
        CheckConstraint(
            "(purchase_price_minor IS NULL) = (purchase_currency IS NULL)",
            name="purchase_price_has_currency",
        ),
        CheckConstraint(
            "purchase_price_minor IS NULL OR purchase_price_minor >= 0",
            name="purchase_price_non_negative",
        ),
    )

    @property
    def purchase_price(self) -> Money | None:
        if self.purchase_price_minor is None or self.purchase_currency is None:
            return None
        return Money(self.purchase_price_minor, self.purchase_currency)

    @purchase_price.setter
    def purchase_price(self, value: Money | None) -> None:
        self.purchase_price_minor = None if value is None else value.amount_minor
        self.purchase_currency = None if value is None else value.currency


class Image(UUIDPrimaryKeyMixin, TimestampMixin, OwnedMixin, Base):
    """Metadata for an image in object storage. The bytes never touch the database."""

    __tablename__ = "image"

    collection_item_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("collection_item.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(16))
    storage_key: Mapped[str] = mapped_column(String(500), unique=True)
    content_type: Mapped[str] = mapped_column(String(100))
    byte_size: Mapped[int] = mapped_column(BigInteger)
    width: Mapped[int | None]
    height: Mapped[int | None]
    sha256: Mapped[str] = mapped_column(String(64), index=True)

    collection_item: Mapped[CollectionItem | None] = relationship(back_populates="images")

    __table_args__ = (
        CheckConstraint("kind IN ('front', 'back', 'scan_source', 'crop')", name="kind_valid"),
        CheckConstraint("byte_size > 0", name="byte_size_positive"),
    )
