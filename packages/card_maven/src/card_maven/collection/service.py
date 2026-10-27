"""Collection use cases: add, edit, list, and remove a collector's items."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from sqlalchemy import ColumnElement, Select, exists, func, or_, select, tuple_
from sqlalchemy.orm import Session, contains_eager, selectinload

from card_maven.catalog.models import Card, CardSet, CardVariant, Parallel, Player, card_player
from card_maven.catalog.service import CatalogService
from card_maven.collection.models import CollectionItem, Condition, Image, ImageStatus
from card_maven.collection.schemas import Holding, ItemChanges, MoneyInput, NewItem
from card_maven.shared.errors import InvalidInputError
from card_maven.shared.pagination import CursorValue, decode_cursor, encode_cursor
from card_maven.shared.repository import OwnedRepository
from card_maven.shared.text import like_pattern, slugify

MAX_PAGE_SIZE = 100


class Sort(StrEnum):
    NEWEST = "newest"
    OLDEST = "oldest"
    YEAR_DESC = "year_desc"
    YEAR_ASC = "year_asc"
    NAME = "name"


@dataclass(frozen=True, slots=True)
class _SortSpec:
    columns: tuple[Any, ...]
    descending: bool


def _sort_spec(sort: Sort) -> _SortSpec:
    # Every sort ends with the primary key, so the order is total and keyset
    # pagination never skips or repeats rows that share the other key values.
    created, item_id = CollectionItem.created_at, CollectionItem.id
    specs = {
        Sort.NEWEST: _SortSpec((created, item_id), descending=True),
        Sort.OLDEST: _SortSpec((created, item_id), descending=False),
        Sort.YEAR_DESC: _SortSpec((CardSet.year, created, item_id), descending=True),
        Sort.YEAR_ASC: _SortSpec((CardSet.year, created, item_id), descending=False),
        Sort.NAME: _SortSpec((func.lower(Card.name), item_id), descending=False),
    }
    return specs[sort]


def _sort_values(item: CollectionItem, sort: Sort) -> tuple[CursorValue, ...]:
    card = item.variant.card
    values: dict[Sort, tuple[CursorValue, ...]] = {
        Sort.NEWEST: (item.created_at, item.id),
        Sort.OLDEST: (item.created_at, item.id),
        Sort.YEAR_DESC: (card.card_set.year, item.created_at, item.id),
        Sort.YEAR_ASC: (card.card_set.year, item.created_at, item.id),
        Sort.NAME: (card.name.lower(), item.id),
    }
    return values[sort]


@dataclass(frozen=True, slots=True)
class ItemFilters:
    sport: str | None = None
    year: int | None = None
    brand: str | None = None
    condition: Condition | None = None
    query: str | None = None


@dataclass(frozen=True, slots=True)
class Page:
    items: Sequence[CollectionItem]
    next_cursor: str | None


class CollectionRepository(OwnedRepository[CollectionItem]):
    model = CollectionItem
    not_found_message = "collection item not found"

    def _scoped(self) -> Select[CollectionItem]:
        # Join the catalog once and load it eagerly: every caller renders it.
        return (
            super()
            ._scoped()
            .join(CollectionItem.variant)
            .join(CardVariant.card)
            .join(Card.card_set)
            .join(CardVariant.parallel)
            .options(
                contains_eager(CollectionItem.variant)
                .contains_eager(CardVariant.card)
                .options(contains_eager(Card.card_set), selectinload(Card.players)),
                contains_eager(CollectionItem.variant).contains_eager(CardVariant.parallel),
                selectinload(CollectionItem.images),
            )
        )

    def page(self, filters: ItemFilters, *, sort: Sort, cursor: str | None, limit: int) -> Page:
        if not 1 <= limit <= MAX_PAGE_SIZE:
            raise InvalidInputError(f"limit must be between 1 and {MAX_PAGE_SIZE}", field="limit")
        spec = _sort_spec(sort)
        statement = self._filtered(filters)
        if cursor:
            values = decode_cursor(cursor, expected_sort=sort.value, size=len(spec.columns)).values
            row, after = tuple_(*spec.columns), tuple_(*values)
            statement = statement.where(row < after if spec.descending else row > after)
        order = [c.desc() if spec.descending else c.asc() for c in spec.columns]
        rows = list(self.session.scalars(statement.order_by(*order).limit(limit + 1)).unique())
        has_more = len(rows) > limit
        items = rows[:limit]
        next_cursor = (
            encode_cursor(sort.value, _sort_values(items[-1], sort)) if has_more and items else None
        )
        return Page(items=items, next_cursor=next_cursor)

    def _filtered(self, filters: ItemFilters) -> Select[CollectionItem]:
        statement = self._scoped()
        if filters.sport:
            statement = statement.where(CardSet.sport_code == filters.sport.lower())
        if filters.year:
            statement = statement.where(CardSet.year == filters.year)
        if filters.brand:
            statement = statement.where(CardSet.brand_slug == slugify(filters.brand))
        if filters.condition:
            statement = statement.where(CollectionItem.condition == filters.condition)
        if filters.query and filters.query.strip():
            statement = statement.where(_matches(filters.query))
        return statement


def _matches(query: str) -> ColumnElement[bool]:
    pattern = like_pattern(query)
    player_match = exists(
        select(card_player.c.card_id)
        .join(Player, Player.id == card_player.c.player_id)
        .where(card_player.c.card_id == Card.id, Player.full_name.ilike(pattern))
    )
    return or_(
        Card.name.ilike(pattern),
        Card.card_number.ilike(pattern),
        Card.team.ilike(pattern),
        CardSet.name.ilike(pattern),
        Parallel.name.ilike(pattern),
        player_match,
    )


def _apply_holding(item: CollectionItem, holding: Holding) -> None:
    item.condition = holding.condition
    item.grader = holding.grader
    item.grade = holding.grade
    item.cert_number = holding.cert_number
    item.serial_number = holding.serial_number
    item.purchase_price = holding.purchase_price.to_money() if holding.purchase_price else None
    item.acquired_on = holding.acquired_on
    item.notes = holding.notes


def _current_holding(item: CollectionItem) -> dict[str, Any]:
    price = item.purchase_price
    return {
        "condition": item.condition,
        "grader": item.grader,
        "grade": item.grade,
        "cert_number": item.cert_number,
        "serial_number": item.serial_number,
        "purchase_price": (
            MoneyInput(amount=price.to_decimal(), currency=price.currency) if price else None
        ),
        "acquired_on": item.acquired_on,
        "notes": item.notes,
    }


def _check_serial(item: CollectionItem) -> None:
    print_run = item.variant.parallel.print_run
    if item.serial_number is not None and print_run is not None and item.serial_number > print_run:
        raise InvalidInputError(
            f"serial number {item.serial_number} exceeds the print run of /{print_run}",
            field="serial_number",
        )


class CollectionService:
    def __init__(self, session: Session, owner_id: uuid.UUID) -> None:
        self.session = session
        self.items = CollectionRepository(session, owner_id)
        self.catalog = CatalogService(session)

    def create(self, command: NewItem) -> CollectionItem:
        item = CollectionItem(variant=self.catalog.resolve_variant(command.card))
        _apply_holding(item, command)
        _check_serial(item)
        self.items.add(item)
        return self.items.get(item.id)

    def get(self, item_id: uuid.UUID) -> CollectionItem:
        return self.items.get(item_id)

    def update(self, item_id: uuid.UUID, changes: ItemChanges) -> CollectionItem:
        item = self.items.get(item_id)
        provided = changes.model_dump(exclude_unset=True, exclude={"card"})
        if provided:
            merged = {**_current_holding(item), **provided}
            _apply_holding(item, Holding.model_validate(merged))
        if changes.card is not None:
            item.variant = self.catalog.resolve_variant(changes.card)
        _check_serial(item)
        self.session.flush()
        self.session.expire(item)
        return self.items.get(item_id)

    def delete(self, item_id: uuid.UUID) -> list[str]:
        """Delete an item. Returns storage keys to remove once the transaction commits."""
        item = self.items.get(item_id)
        keys = [image.storage_key for image in item.images]
        self.items.delete(item)
        return keys

    def page(
        self,
        filters: ItemFilters | None = None,
        *,
        sort: Sort = Sort.NEWEST,
        cursor: str | None = None,
        limit: int = 24,
    ) -> Page:
        return self.items.page(filters or ItemFilters(), sort=sort, cursor=cursor, limit=limit)


def live_images(item: CollectionItem) -> dict[str, Image]:
    """The item's current front/back photos, keyed by kind."""
    return {i.kind: i for i in item.images if i.status == ImageStatus.READY}
