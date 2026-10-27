from pathlib import Path

import pytest

from card_maven.market.tracked_sets import (
    TrackedSetSpec,
    brand_slug,
    expand,
    load_tracked_sets,
    parse_tracked_sets,
)
from card_maven.shared.errors import InvalidInputError

REPO_ROOT = Path(__file__).resolve().parents[3]

MINIMAL = """
defaults:
  years: { from: 2024, to: 2025 }
sets:
  - { sport: baseball, brand: Bowman, name: Bowman Chrome }
"""


def test_repository_config_is_valid() -> None:
    """Guards the real config file: a bad edit fails CI, not the nightly job."""
    config = load_tracked_sets(REPO_ROOT / "config" / "tracked_sets.yaml")
    specs = expand(config)
    assert len(specs) == len(config.sets) * 3  # 2024-2026
    assert {s.sport_code for s in specs} == {"baseball", "basketball", "football", "hockey"}
    young_guns = [s for s in specs if s.brand_slug == "upper-deck"]
    assert young_guns
    assert all(s.focus == "Young Guns" for s in young_guns)


def test_expand_uses_defaults() -> None:
    assert expand(parse_tracked_sets(MINIMAL)) == [
        TrackedSetSpec("baseball", "bowman", "Bowman Chrome", 2024),
        TrackedSetSpec("baseball", "bowman", "Bowman Chrome", 2025),
    ]


@pytest.mark.parametrize(
    ("override", "years"),
    [
        ("{ from: 2022 }", [2022, 2023, 2024, 2025]),
        ("{ to: 2024 }", [2024]),
        ("{ from: 2020, to: 2021 }", [2020, 2021]),
        ("{}", [2024, 2025]),
    ],
)
def test_per_set_year_override(override: str, years: list[int]) -> None:
    raw = f"""
defaults:
  years: {{ from: 2024, to: 2025 }}
sets:
  - {{ sport: baseball, brand: Topps, name: Topps Chrome, years: {override} }}
"""
    assert [s.year for s in expand(parse_tracked_sets(raw))] == years


def test_normalizes_sport_and_brand() -> None:
    raw = MINIMAL.replace(
        "sport: baseball, brand: Bowman", "sport: Baseball, brand: '  Upper  Deck '"
    )
    spec = expand(parse_tracked_sets(raw))[0]
    assert spec.sport_code == "baseball"
    assert spec.brand_slug == "upper-deck"


ONE_SET = (
    "defaults:\n  years: {{ from: {start}, to: {end} }}\n"
    "sets:\n  - {{ sport: a, brand: b, name: c }}"
)


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ("defaults: [unclosed", "not valid YAML"),
        ("", "invalid"),
        (ONE_SET.format(start=2026, end=2024), "must not be after"),
        (ONE_SET.format(start=1700, end=2024), "invalid"),
        ("defaults:\n  years: { from: 2024, to: 2025 }\nsets: []", "invalid"),
        (MINIMAL + "  - { sport: baseball, brand: bowman, name: bowman chrome }", "duplicate"),
        (
            MINIMAL.replace("Bowman, name: Bowman Chrome", "Upper Deck, name: S1")
            + "  - { sport: baseball, brand: upper  deck, name: s1 }",
            "duplicate",
        ),
        (MINIMAL.replace("name: Bowman Chrome", "name: Bowman Chrome, colour: red"), "invalid"),
        (MINIMAL.replace("name: Bowman Chrome", "name: ''"), "invalid"),
    ],
)
def test_rejects_invalid_config(raw: str, message: str) -> None:
    with pytest.raises(InvalidInputError, match=message):
        parse_tracked_sets(raw)


def test_override_resolving_to_inverted_range_is_rejected() -> None:
    raw = MINIMAL.replace("name: Bowman Chrome", "name: Bowman Chrome, years: { from: 2030 }")
    with pytest.raises(ValueError, match="must not be after"):
        expand(parse_tracked_sets(raw))


def test_missing_file(tmp_path: Path) -> None:
    with pytest.raises(InvalidInputError, match="cannot read"):
        load_tracked_sets(tmp_path / "missing.yaml")


def test_brand_slug() -> None:
    assert brand_slug("Upper Deck") == "upper-deck"
    assert brand_slug("Panini") == "panini"
