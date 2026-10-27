from __future__ import annotations

import uuid
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    Column,
    ForeignKey,
    SmallInteger,
    String,
    Table,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from card_maven.shared.db import Base, TimestampMixin, UUIDPrimaryKeyMixin

BASE_PARALLEL_NAME = "Base"


class CatalogSource(StrEnum):
    """Where a catalog record came from. ``reference:<provider>`` values are added
    when a licensed checklist is plugged in; the column is a plain string so that
    needs no migration."""

    USER_CONFIRMED = "user_confirmed"
    SEED = "seed"


class Sport(Base):
    __tablename__ = "sport"

    code: Mapped[str] = mapped_column(String(32), primary_key=True)  # e.g. "baseball"
    name: Mapped[str] = mapped_column(String(64), unique=True)


class Brand(Base):
    __tablename__ = "brand"

    slug: Mapped[str] = mapped_column(String(64), primary_key=True)  # e.g. "upper-deck"
    name: Mapped[str] = mapped_column(String(128), unique=True)


class CardSet(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A product release, e.g. 2025 Bowman Chrome (baseball)."""

    __tablename__ = "card_set"

    sport_code: Mapped[str] = mapped_column(ForeignKey("sport.code"))
    brand_slug: Mapped[str] = mapped_column(ForeignKey("brand.slug"))
    year: Mapped[int] = mapped_column(SmallInteger)
    name: Mapped[str] = mapped_column(String(200))
    catalog_source: Mapped[str] = mapped_column(
        String(64),
        default=CatalogSource.USER_CONFIRMED,
        server_default=CatalogSource.USER_CONFIRMED.value,
    )

    cards: Mapped[list[Card]] = relationship(back_populates="card_set")
    parallels: Mapped[list[Parallel]] = relationship(back_populates="card_set")

    __table_args__ = (
        UniqueConstraint("sport_code", "brand_slug", "year", "name"),
        CheckConstraint("year BETWEEN 1860 AND 2100", name="year_range"),
    )


card_player = Table(
    "card_player",
    Base.metadata,
    Column("card_id", ForeignKey("card.id", ondelete="CASCADE"), primary_key=True),
    Column("player_id", ForeignKey("player.id", ondelete="RESTRICT"), primary_key=True, index=True),
    Column("position", SmallInteger, nullable=False, default=0, server_default=text("0")),
)


class Player(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "player"

    sport_code: Mapped[str] = mapped_column(ForeignKey("sport.code"))
    full_name: Mapped[str] = mapped_column(String(200), index=True)
    # Ids in external systems (league, data providers), keyed by provider.
    external_ids: Mapped[dict[str, Any]] = mapped_column(
        default=dict, server_default=text("'{}'::jsonb")
    )


class Card(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One checklist entry within a set, e.g. BCP-50 in 2025 Bowman Chrome."""

    __tablename__ = "card"

    set_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("card_set.id", ondelete="CASCADE"))
    card_number: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(200))
    # Subset within the product, e.g. "Prospects", "Chrome Prospect Autographs".
    subset: Mapped[str | None] = mapped_column(String(200))
    team: Mapped[str | None] = mapped_column(String(200))
    is_rookie: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    is_autograph: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    is_memorabilia: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    # Set-specific flags that don't merit a column, e.g. {"first_bowman": true}.
    attributes: Mapped[dict[str, Any]] = mapped_column(
        default=dict, server_default=text("'{}'::jsonb")
    )
    catalog_source: Mapped[str] = mapped_column(
        String(64),
        default=CatalogSource.USER_CONFIRMED,
        server_default=CatalogSource.USER_CONFIRMED.value,
    )

    card_set: Mapped[CardSet] = relationship(back_populates="cards")
    players: Mapped[list[Player]] = relationship(
        secondary=card_player, order_by=card_player.c.position
    )
    variants: Mapped[list[CardVariant]] = relationship(back_populates="card")

    __table_args__ = (UniqueConstraint("set_id", "card_number"),)


class Parallel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A finish or print variation, e.g. "Gold Refractor" /50.

    ``subset`` scopes a parallel to one subset; NULL means it applies to the whole
    set. Every set has a "Base" parallel, so every variant has a parallel and
    downstream code has no NULL special case.
    """

    __tablename__ = "parallel"

    set_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("card_set.id", ondelete="CASCADE"))
    subset: Mapped[str | None] = mapped_column(String(200))
    name: Mapped[str] = mapped_column(String(200))
    color: Mapped[str | None] = mapped_column(String(64))
    print_run: Mapped[int | None]
    catalog_source: Mapped[str] = mapped_column(
        String(64),
        default=CatalogSource.USER_CONFIRMED,
        server_default=CatalogSource.USER_CONFIRMED.value,
    )

    card_set: Mapped[CardSet] = relationship(back_populates="parallels")

    __table_args__ = (
        CheckConstraint("print_run IS NULL OR print_run > 0", name="print_run_positive"),
        # NULLS NOT DISTINCT (Postgres 15+): a set-wide "Refractor" can't be duplicated.
        UniqueConstraint("set_id", "subset", "name", postgresql_nulls_not_distinct=True),
    )

    @property
    def is_base(self) -> bool:
        return self.name == BASE_PARALLEL_NAME


class CardVariant(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A card in a specific parallel. Holdings and market data attach here."""

    __tablename__ = "card_variant"

    card_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("card.id", ondelete="CASCADE"))
    parallel_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("parallel.id", ondelete="RESTRICT"), index=True
    )

    card: Mapped[Card] = relationship(back_populates="variants")
    parallel: Mapped[Parallel] = relationship()

    __table_args__ = (UniqueConstraint("card_id", "parallel_id"),)
