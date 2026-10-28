"""Fixtures shared by the core package's tests (the root conftest provides the database)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from sqlalchemy.orm import Session

from card_maven.catalog.models import CardVariant
from card_maven.catalog.schemas import CardIdentity
from card_maven.catalog.service import CatalogService
from card_maven.collection.models import CollectionItem
from card_maven.collection.schemas import NewItem
from card_maven.collection.service import CollectionService
from card_maven.identity.models import User

WETHERHOLT_GOLD: dict[str, Any] = {
    "sport": "baseball",
    "brand": "Bowman",
    "year": 2025,
    "set_name": "Bowman Chrome",
    "card_number": "CPA-JW",
    "name": "JJ Wetherholt",
    "players": ["JJ Wetherholt"],
    "subset": "Chrome Prospect Autographs",
    "is_autograph": True,
    "parallel": {"name": "Gold Refractor", "print_run": 50},
}
SKENES_BASE: dict[str, Any] = {
    "sport": "baseball",
    "brand": "Topps",
    "year": 2024,
    "set_name": "Topps Chrome",
    "card_number": "1",
    "name": "Paul Skenes",
    "players": ["Paul Skenes"],
    "is_rookie": True,
}


@pytest.fixture
def make_user(seeded_session: Session) -> Callable[[str], User]:
    def make(subject: str = "owner") -> User:
        user = User(idp_issuer="https://idp.test", idp_subject=subject)
        seeded_session.add(user)
        seeded_session.flush()
        return user

    return make


@pytest.fixture
def make_variant(seeded_session: Session) -> Callable[..., CardVariant]:
    def make(**card: Any) -> CardVariant:
        return CatalogService(seeded_session).resolve_variant(CardIdentity.model_validate(card))

    return make


@pytest.fixture
def make_item(seeded_session: Session) -> Callable[..., CollectionItem]:
    def make(owner: User, card: dict[str, Any], **holding: Any) -> CollectionItem:
        command = NewItem.model_validate({"card": card, **holding})
        return CollectionService(seeded_session, owner.id).create(command)

    return make


@pytest.fixture
def card_specs() -> dict[str, dict[str, Any]]:
    """Card identities for tests: ``card_specs["wetherholt_gold"]``, ``["skenes_base"]``."""
    return {"wetherholt_gold": dict(WETHERHOLT_GOLD), "skenes_base": dict(SKENES_BASE)}


@pytest.fixture
def gold(make_variant: Callable[..., CardVariant]) -> CardVariant:
    """2025 Bowman Chrome JJ Wetherholt CPA-JW Gold Refractor Auto /50."""
    return make_variant(**WETHERHOLT_GOLD)
