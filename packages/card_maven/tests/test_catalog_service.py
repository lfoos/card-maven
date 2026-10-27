import pytest
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from card_maven.catalog.models import Brand, Card, CardSet, CardVariant, Parallel, Player
from card_maven.catalog.schemas import CardIdentity, ParallelSpec
from card_maven.catalog.service import CatalogService, get_or_create
from card_maven.shared.errors import InvalidInputError

pytestmark = pytest.mark.db


def spec(**overrides: object) -> CardIdentity:
    fields: dict[str, object] = {
        "sport": "baseball",
        "brand": "Bowman",
        "year": 2025,
        "set_name": "Bowman Chrome",
        "card_number": "CPA-JW",
        "name": "JJ Wetherholt",
        "players": ["JJ Wetherholt"],
        "subset": "Chrome Prospect Autographs",
        "is_autograph": True,
    }
    fields.update(overrides)
    return CardIdentity.model_validate(fields)


def count(session: Session, model: type) -> int:
    return session.scalar(select(func.count()).select_from(model)) or 0


class TestCardIdentity:
    def test_normalizes_text(self) -> None:
        card = spec(
            sport=" Baseball ", set_name="  Bowman   Chrome ", team="", players=["A", "a", "B"]
        )
        assert card.sport == "baseball"
        assert card.set_name == "Bowman Chrome"
        assert card.team is None
        assert card.players == ["A", "B"]

    @pytest.mark.parametrize(
        "overrides",
        [
            {"year": 1700},
            {"card_number": "  "},
            {"name": ""},
            {"players": ["x"] * 7},
            {"parallel": {"name": "Gold", "print_run": 0}},
            {"surprise": 1},
        ],
    )
    def test_rejects_invalid(self, overrides: dict[str, object]) -> None:
        with pytest.raises(ValidationError):
            spec(**overrides)


class TestResolveVariant:
    def test_creates_the_whole_chain_with_base_parallel(self, seeded_session: Session) -> None:
        variant = CatalogService(seeded_session).resolve_variant(spec())
        assert variant.parallel.name == "Base"
        assert variant.parallel.subset is None  # Base is set-wide
        card = variant.card
        assert (card.card_set.name, card.card_set.year, card.card_set.brand_slug) == (
            "Bowman Chrome",
            2025,
            "bowman",
        )
        assert [p.full_name for p in card.players] == ["JJ Wetherholt"]
        assert card.is_autograph
        assert card.catalog_source == "user_confirmed"

    def test_reuses_existing_rows_case_insensitively(self, seeded_session: Session) -> None:
        service = CatalogService(seeded_session)
        first = service.resolve_variant(spec())
        second = service.resolve_variant(
            spec(
                brand="BOWMAN",
                set_name="bowman  chrome",
                card_number="cpa-jw",
                players=["jj wetherholt"],
            )
        )
        assert second.id == first.id
        assert (
            count(seeded_session, CardSet),
            count(seeded_session, Card),
            count(seeded_session, Player),
        ) == (1, 1, 1)

    def test_existing_card_details_win(self, seeded_session: Session) -> None:
        service = CatalogService(seeded_session)
        service.resolve_variant(spec(team="Cardinals"))
        again = service.resolve_variant(spec(name="Typo Name", team="Mets"))
        assert (again.card.name, again.card.team) == ("JJ Wetherholt", "Cardinals")

    def test_parallels_are_scoped_to_the_subset(self, seeded_session: Session) -> None:
        service = CatalogService(seeded_session)
        auto = service.resolve_variant(spec(parallel=ParallelSpec(name="Refractor", print_run=499)))
        prospect = service.resolve_variant(
            spec(
                card_number="BCP-50",
                subset="Prospects",
                is_autograph=False,
                parallel=ParallelSpec(name="refractor", print_run=499),
            )
        )
        assert auto.parallel.id != prospect.parallel.id
        assert (auto.parallel.subset, prospect.parallel.subset) == (
            "Chrome Prospect Autographs",
            "Prospects",
        )
        same = service.resolve_variant(spec(parallel=ParallelSpec(name="REFRACTOR")))
        assert same.id == auto.id

    def test_base_parallel_shared_across_subsets(self, seeded_session: Session) -> None:
        service = CatalogService(seeded_session)
        a = service.resolve_variant(spec())
        b = service.resolve_variant(spec(card_number="BCP-50", subset="Prospects"))
        assert a.parallel.id == b.parallel.id

    def test_new_brand_is_created(self, seeded_session: Session) -> None:
        variant = CatalogService(seeded_session).resolve_variant(spec(brand="Leaf  Metal"))
        assert variant.card.card_set.brand_slug == "leaf-metal"
        assert seeded_session.get(Brand, "leaf-metal").name == "Leaf Metal"

    def test_unknown_sport_rejected(self, seeded_session: Session) -> None:
        with pytest.raises(InvalidInputError, match="unknown sport") as excinfo:
            CatalogService(seeded_session).resolve_variant(spec(sport="curling"))
        assert excinfo.value.extra == {"field": "card.sport"}
        assert count(seeded_session, CardSet) == 0

    def test_player_reused_by_name_within_sport_only(self, seeded_session: Session) -> None:
        service = CatalogService(seeded_session)
        service.resolve_variant(spec(players=["Will Smith"]))
        service.resolve_variant(
            spec(
                sport="football",
                brand="Panini",
                set_name="Prizm",
                card_number="1",
                players=["Will Smith"],
            )
        )
        service.resolve_variant(spec(card_number="2", players=["will smith"]))
        assert count(seeded_session, Player) == 2  # one baseball, one football


class TestGetOrCreateRace:
    def test_loser_returns_the_winner(self, seeded_session: Session) -> None:
        seeded_session.add(Brand(slug="leaf", name="Leaf"))
        seeded_session.flush()
        calls = {"n": 0}

        def stale_find() -> Brand | None:
            calls["n"] += 1
            return None if calls["n"] == 1 else seeded_session.get(Brand, "leaf")

        result = get_or_create(seeded_session, stale_find, lambda: Brand(slug="leaf", name="Leaf"))
        assert result.name == "Leaf"
        assert count(seeded_session, Brand) == 5  # 4 seeded + Leaf, no duplicate

    def test_unexplained_integrity_error_propagates(self, seeded_session: Session) -> None:
        from sqlalchemy.exc import IntegrityError

        seeded_session.add(Brand(slug="leaf", name="Leaf"))
        seeded_session.flush()
        with pytest.raises(IntegrityError):
            get_or_create(seeded_session, lambda: None, lambda: Brand(slug="leaf", name="Leaf"))


class TestSuggestions:
    @pytest.fixture
    def catalog(self, seeded_session: Session) -> CatalogService:
        service = CatalogService(seeded_session)
        service.resolve_variant(spec())
        service.resolve_variant(
            spec(year=2024, card_number="BCP-1", players=["Roman Anthony"], name="Roman Anthony")
        )
        service.resolve_variant(
            spec(
                sport="basketball",
                brand="Panini",
                set_name="Prizm",
                card_number="1",
                players=["Victor Wembanyama"],
                name="Victor Wembanyama",
                subset=None,
            )
        )
        return service

    def test_sets_filtered_and_newest_first(self, catalog: CatalogService) -> None:
        assert [(s.name, s.year) for s in catalog.search_sets("chrome")] == [
            ("Bowman Chrome", 2025),
            ("Bowman Chrome", 2024),
        ]
        assert [s.year for s in catalog.search_sets("chrome", year=2024)] == [2024]
        assert catalog.search_sets("chrome", sport="Basketball") == []

    def test_players(self, catalog: CatalogService) -> None:
        assert [p.full_name for p in catalog.search_players("an")] == [
            "Roman Anthony",
            "Victor Wembanyama",
        ]
        assert [p.full_name for p in catalog.search_players("an", sport="basketball")] == [
            "Victor Wembanyama"
        ]

    def test_wildcards_in_queries_are_literal(self, catalog: CatalogService) -> None:
        assert catalog.search_players("%") == []
        assert catalog.search_sets("_") == []

    def test_limit_is_capped(self, catalog: CatalogService) -> None:
        assert len(catalog.search_players("a", limit=1)) == 1
        assert len(catalog.search_players("a", limit=10_000)) <= 20

    def test_parallels_for_set(self, catalog: CatalogService, seeded_session: Session) -> None:
        catalog.resolve_variant(spec(parallel=ParallelSpec(name="Gold Refractor", print_run=50)))
        set_id = seeded_session.scalars(
            select(CardSet.id).where(CardSet.year == 2025, CardSet.name == "Bowman Chrome")
        ).one()
        names = [(p.subset, p.name) for p in catalog.list_parallels(set_id)]
        assert names == [(None, "Base"), ("Chrome Prospect Autographs", "Gold Refractor")]
        assert seeded_session.scalar(select(func.count()).select_from(Parallel)) >= 2
        assert count(seeded_session, CardVariant) == 4
