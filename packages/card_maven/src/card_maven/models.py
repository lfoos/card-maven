"""Imports every ORM model so ``Base.metadata`` is complete (used by Alembic)."""

from card_maven.catalog.models import (
    Brand,
    Card,
    CardSet,
    CardVariant,
    Parallel,
    Player,
    Sport,
    card_player,
)
from card_maven.collection.models import CollectionItem, Image
from card_maven.identity.models import User
from card_maven.market.models import TrackedSet
from card_maven.shared.db import Base
from card_maven.shared.outbox import OutboxMessage

__all__ = [
    "Base",
    "Brand",
    "Card",
    "CardSet",
    "CardVariant",
    "CollectionItem",
    "Image",
    "OutboxMessage",
    "Parallel",
    "Player",
    "Sport",
    "TrackedSet",
    "User",
    "card_player",
]
