"""Catalog lookups and find-or-create resolution of a card variant."""

from __future__ import annotations

import uuid
from collections.abc import Callable

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from card_maven.catalog.models import (
    BASE_PARALLEL_NAME,
    Brand,
    Card,
    CardSet,
    CardVariant,
    CatalogSource,
    Parallel,
    Player,
    Sport,
)
from card_maven.catalog.schemas import CardIdentity
from card_maven.shared.errors import InvalidInputError
from card_maven.shared.text import like_pattern, slugify

MAX_SUGGESTIONS = 20


def get_or_create[T](session: Session, find: Callable[[], T | None], make: Callable[[], T]) -> T:
    """Find a row by its natural key, or insert it.

    The insert runs in a savepoint. If a concurrent transaction inserted the
    same natural key first, the unique index rejects ours, the savepoint rolls
    back, and we return the winner's row. Callers never see the race.
    """
    existing = find()
    if existing is not None:
        return existing
    try:
        with session.begin_nested():
            created = make()
            session.add(created)
        return created
    except IntegrityError:
        winner = find()
        if winner is None:
            raise
        return winner


class CatalogService:
    def __init__(self, session: Session) -> None:
        self.session = session

    # ---- Resolution -------------------------------------------------------

    def resolve_variant(self, spec: CardIdentity) -> CardVariant:
        """Return the variant ``spec`` describes, creating catalog rows as needed.

        Existing catalog rows win: if the card is already known, its stored
        name, team, and flags are kept (the shared catalog is the source of
        truth; corrections arrive with a reference catalog).
        """
        if self.session.get(Sport, spec.sport) is None:
            raise InvalidInputError(f"unknown sport '{spec.sport}'", field="card.sport")
        brand = self._brand(spec.brand)
        card_set = self._set(spec, brand)
        card = self._card(spec, card_set)
        parallel = self._parallel(spec, card_set)
        return get_or_create(
            self.session,
            lambda: self.session.scalars(
                select(CardVariant).where(
                    CardVariant.card_id == card.id, CardVariant.parallel_id == parallel.id
                )
            ).one_or_none(),
            lambda: CardVariant(card=card, parallel=parallel),
        )

    def _brand(self, name: str) -> Brand:
        slug = slugify(name)
        return get_or_create(
            self.session, lambda: self.session.get(Brand, slug), lambda: Brand(slug=slug, name=name)
        )

    def _set(self, spec: CardIdentity, brand: Brand) -> CardSet:
        return get_or_create(
            self.session,
            lambda: self.session.scalars(
                select(CardSet).where(
                    CardSet.sport_code == spec.sport,
                    CardSet.brand_slug == brand.slug,
                    CardSet.year == spec.year,
                    func.lower(CardSet.name) == spec.set_name.lower(),
                )
            ).one_or_none(),
            lambda: CardSet(
                sport_code=spec.sport,
                brand_slug=brand.slug,
                year=spec.year,
                name=spec.set_name,
                catalog_source=CatalogSource.USER_CONFIRMED,
            ),
        )

    def _card(self, spec: CardIdentity, card_set: CardSet) -> Card:
        def make() -> Card:
            # Resolve players first: their lookups may autoflush, which must not
            # happen while a half-built Card is attached to the set.
            players = [self._player(name, spec.sport) for name in spec.players]
            card = Card(
                card_set=card_set,
                card_number=spec.card_number,
                name=spec.name,
                subset=spec.subset,
                team=spec.team,
                is_rookie=spec.is_rookie,
                is_autograph=spec.is_autograph,
                is_memorabilia=spec.is_memorabilia,
                catalog_source=CatalogSource.USER_CONFIRMED,
            )
            card.players = players
            return card

        return get_or_create(
            self.session,
            lambda: self.session.scalars(
                select(Card).where(
                    Card.set_id == card_set.id,
                    func.upper(Card.card_number) == spec.card_number.upper(),
                )
            ).one_or_none(),
            make,
        )

    def _player(self, full_name: str, sport: str) -> Player:
        # Players aren't unique by name (two MLB "Will Smith"s), so this picks the
        # earliest match. A reference catalog with league ids will disambiguate.
        existing = self.session.scalars(
            select(Player)
            .where(Player.sport_code == sport, func.lower(Player.full_name) == full_name.lower())
            .order_by(Player.created_at, Player.id)
            .limit(1)
        ).one_or_none()
        if existing is not None:
            return existing
        player = Player(sport_code=sport, full_name=full_name)
        self.session.add(player)
        return player

    def _parallel(self, spec: CardIdentity, card_set: CardSet) -> Parallel:
        name = spec.parallel.name if spec.parallel else BASE_PARALLEL_NAME
        # Base is set-wide; other parallels are scoped to the card's subset,
        # since print runs differ between, e.g., Prospects and Prospect Autos.
        subset = None if name.lower() == BASE_PARALLEL_NAME.lower() else spec.subset
        return get_or_create(
            self.session,
            lambda: self.session.scalars(
                select(Parallel).where(
                    Parallel.set_id == card_set.id,
                    func.coalesce(Parallel.subset, "") == (subset or ""),
                    func.lower(Parallel.name) == name.lower(),
                )
            ).one_or_none(),
            lambda: Parallel(
                card_set=card_set,
                subset=subset,
                name=name,
                print_run=spec.parallel.print_run if spec.parallel else None,
                color=spec.parallel.color if spec.parallel else None,
                catalog_source=CatalogSource.USER_CONFIRMED,
            ),
        )

    # ---- Suggestions ------------------------------------------------------

    def search_sets(
        self, query: str, *, sport: str | None = None, year: int | None = None, limit: int = 10
    ) -> list[CardSet]:
        statement = select(CardSet).where(CardSet.name.ilike(like_pattern(query)))
        if sport:
            statement = statement.where(CardSet.sport_code == sport.lower())
        if year:
            statement = statement.where(CardSet.year == year)
        statement = statement.order_by(CardSet.year.desc(), CardSet.name).limit(
            min(limit, MAX_SUGGESTIONS)
        )
        return list(self.session.scalars(statement))

    def search_players(
        self, query: str, *, sport: str | None = None, limit: int = 10
    ) -> list[Player]:
        statement = select(Player).where(Player.full_name.ilike(like_pattern(query)))
        if sport:
            statement = statement.where(Player.sport_code == sport.lower())
        statement = statement.order_by(Player.full_name).limit(min(limit, MAX_SUGGESTIONS))
        return list(self.session.scalars(statement))

    def list_parallels(self, set_id: uuid.UUID) -> list[Parallel]:
        return list(
            self.session.scalars(
                select(Parallel)
                .where(Parallel.set_id == set_id)
                .order_by(Parallel.subset.nulls_first(), Parallel.name)
            )
        )
