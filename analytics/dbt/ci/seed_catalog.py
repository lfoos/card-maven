"""CI only: add a few catalog cards that the sample (fixture) sales match.

A fresh database has no catalog yet, so every synced sale would be stored
unmatched and the marts would be empty. Run before `request-market-sync
--run-now` so `dbt build` exercises real rows.
"""

import os

import card_maven.models  # noqa: F401  (register every table)
from card_maven.catalog.schemas import CardIdentity
from card_maven.catalog.service import CatalogService
from card_maven.shared.db import make_engine, make_session_factory, session_scope

CARDS = [
    {
        "sport": "baseball",
        "brand": "Topps",
        "year": 2024,
        "set_name": "Topps Chrome",
        "card_number": "1",
        "name": "Paul Skenes",
        "players": ["Paul Skenes"],
    },
    {
        "sport": "baseball",
        "brand": "Bowman",
        "year": 2025,
        "set_name": "Bowman Chrome",
        "card_number": "CPA-JW",
        "name": "JJ Wetherholt",
        "players": ["JJ Wetherholt"],
        "is_autograph": True,
        "parallel": {"name": "Gold Refractor", "print_run": 50},
    },
    {
        "sport": "basketball",
        "brand": "Panini",
        "year": 2024,
        "set_name": "Prizm",
        "card_number": "135",
        "name": "Stephon Castle",
        "players": ["Stephon Castle"],
        "parallel": {"name": "Silver"},
    },
]


def main() -> None:
    factory = make_session_factory(make_engine(os.environ["CARD_MAVEN_DATABASE_URL"]))
    with session_scope(factory) as session:
        catalog = CatalogService(session)
        for card in CARDS:
            catalog.resolve_variant(CardIdentity.model_validate(card))
    print(f"seeded {len(CARDS)} catalog cards")


if __name__ == "__main__":
    main()
