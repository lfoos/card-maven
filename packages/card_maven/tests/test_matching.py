from decimal import Decimal

import pytest

from card_maven.market.matching import MATCH_THRESHOLD, MatchTarget, build_target, score
from card_maven.market.parsing import parse_title


def target(**overrides: object) -> MatchTarget:
    fields: dict[str, object] = {
        "variant_id": "v1",
        "year": 2025,
        "card_number": "CPA-JW",
        "surnames": ("wetherholt",),
        "parallel_name": "Gold Refractor",
        "print_run": 50,
        "is_autograph": True,
        "conflicting_terms": frozenset({"orange", "blue", "silver", "superfractor", "red"}),
    }
    fields.update(overrides)
    return MatchTarget(**fields)  # type: ignore[arg-type]


def match(title: str, **overrides: object):  # type: ignore[no-untyped-def]
    return score(parse_title(title), target(**overrides))


class TestNumberedAutoParallel:
    def test_full_title_matches_with_high_confidence(self) -> None:
        result = match("2025 Bowman Chrome JJ Wetherholt CPA-JW Gold Refractor Auto /50 PSA 10")
        assert result.is_match
        assert result.confidence == Decimal(1)

    def test_names_without_number_still_match_when_specific(self) -> None:
        result = match("2025 Bowman Chrome JJ Wetherholt 1st Gold Refractor Auto 12/50")
        assert result.is_match
        assert "number" not in result.reasons

    @pytest.mark.parametrize(
        ("title", "reason"),
        [
            ("2024 Bowman Chrome Wetherholt Gold Refractor Auto /50", "year differs"),
            ("Bowman Chrome Wetherholt Gold Refractor Auto /50", "no year"),
            ("2025 Bowman Chrome Wetherholt Gold Refractor /50", "autograph mismatch"),
            ("2025 Bowman Chrome Wetherholt Gold Refractor Auto /25", "print run"),
            ("2025 Bowman Chrome Wetherholt Orange Refractor Auto /50", "different parallel"),
            ("2025 Bowman Chrome Wetherholt Refractor Auto /50", "missing parallel"),
            (
                "2025 Bowman Chrome Smith Gold Refractor Auto /50",
                "neither card number nor player names",
            ),
            ("2025 Bowman Chrome Wetherholt Gold Refractor Auto /50 lot", "disqualified"),
        ],
    )
    def test_rejections(self, title: str, reason: str) -> None:
        result = match(title)
        assert not result.is_match
        assert result.confidence == 0
        assert reason in result.reasons[0]


class TestBaseCards:
    def base(self, title: str, **overrides: object):  # type: ignore[no-untyped-def]
        return match(
            title,
            parallel_name=None,
            print_run=None,
            is_autograph=False,
            card_number="1",
            surnames=("skenes",),
            year=2024,
            **overrides,
        )

    def test_base_matches_by_number(self) -> None:
        assert self.base("2024 Topps Chrome Paul Skenes #1 RC").is_match

    def test_base_rejects_parallels_and_numbered(self) -> None:
        assert not self.base("2024 Topps Chrome Paul Skenes #1 Silver RC").is_match
        assert not self.base("2024 Topps Chrome Paul Skenes #1 RC /99").is_match

    def test_names_alone_are_not_enough_for_a_base_card(self) -> None:
        result = self.base("2024 Topps Chrome Paul Skenes RC")
        assert not result.is_match
        assert result.confidence < MATCH_THRESHOLD


def test_multi_player_cards_need_every_surname() -> None:
    dual = {
        "surnames": ("mcgonigle", "clark"),
        "card_number": "FS-1",
        "parallel_name": None,
        "print_run": None,
        "is_autograph": False,
    }
    assert (
        match("2025 Bowman Chrome McGonigle Clark Future Stars", **dual).confidence
        < MATCH_THRESHOLD
    )
    assert not match("2025 Bowman Chrome McGonigle Future Stars", **dual).is_match
    assert match("2025 Bowman Chrome McGonigle Clark FS-1", **dual).is_match


class TestBuildTarget:
    def test_identity_words_never_count_as_conflicts(self) -> None:
        from card_maven.catalog.models import Card, CardSet, CardVariant, Parallel, Player

        card_set = CardSet(sport_code="football", brand_slug="panini", year=2024, name="Prizm")
        base = Parallel(card_set=card_set, name="Base")
        Parallel(card_set=card_set, name="Neon Green Pulsar")
        card = Card(
            card_set=card_set, card_number="1", name="Jordan Love", team="Green Bay Packers"
        )
        card.players = [Player(sport_code="football", full_name="Jordan Love")]
        variant = CardVariant(card=card, parallel=base)

        built = build_target(variant, vocabulary=["Hyper Pink"])
        assert built.parallel_name is None
        assert "green" not in built.conflicting_terms  # team name
        assert "prizm" not in built.conflicting_terms  # set name
        assert {"neon", "pulsar", "hyper", "pink"} <= built.conflicting_terms
        assert built.surnames == ("love",)
        assert score(parse_title("2024 Prizm Jordan Love #1 Green Bay Packers"), built).is_match
        assert not score(parse_title("2024 Prizm Jordan Love #1 Neon Green Pulsar"), built).is_match

    def test_own_parallel_words_are_not_conflicts(self) -> None:
        from card_maven.catalog.models import Card, CardSet, CardVariant, Parallel

        card_set = CardSet(
            sport_code="baseball", brand_slug="bowman", year=2025, name="Bowman Chrome"
        )
        gold = Parallel(card_set=card_set, name="Gold Refractor", print_run=50)
        card = Card(card_set=card_set, card_number="BCP-50", name="X")
        built = build_target(CardVariant(card=card, parallel=gold))
        assert built.parallel_name == "Gold Refractor"
        assert "gold" not in built.conflicting_terms
        assert "refractor" not in built.conflicting_terms
        assert built.surnames == ()
