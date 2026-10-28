from decimal import Decimal

import pytest

from card_maven.market.parsing import compact, parse_title, tokens


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        (
            "2025 Bowman Chrome JJ Wetherholt 1st Gold Refractor Auto /50 PSA 10",
            {
                "year": 2025,
                "grader": "PSA",
                "grade": Decimal(10),
                "print_run": 50,
                "serial": None,
                "is_autograph": True,
                "condition": "graded",
            },
        ),
        (
            "2023-24 Panini Prizm Victor Wembanyama #136 Silver RC BGS 9.5 GEM MINT",
            {"year": 2023, "grader": "BGS", "grade": Decimal("9.5"), "is_rookie": True},
        ),
        (
            "Paul Skenes 2024 Topps Chrome RC 12/50 Gold",
            {"serial": 12, "print_run": 50, "condition": "raw"},
        ),
        ("2024 Topps Chrome Skenes #'d /99", {"print_run": 99, "serial": None}),
        ("2024 Topps Chrome Skenes numbered to 25", {"print_run": 25}),
        ("2025 Bowman Chrome Anthony 1/1 Superfractor", {"serial": 1, "print_run": 1}),
        ("2024 Topps Chrome Skenes PSA GEM MT 10", {"grader": "PSA", "grade": Decimal(10)}),
        ("2024 Bowman BVG 9 Holliday", {"grader": "BGS", "grade": Decimal(9)}),
        ("2024 Prizm CSG 9.5 Stroud", {"grader": "CGC", "grade": Decimal("9.5")}),
        ("2024 Prizm Stroud SGC 10/10", {"grader": None}),  # "10/10" isn't a grade
        ("2024 Score Stroud Rookie Signed On-Card Auto", {"is_autograph": True, "is_rookie": True}),
        ("Wetherholt Bowman Chrome no year", {"year": None}),
        ("1993 SP Derek Jeter Foil", {"year": 1993}),
    ],
)
def test_extracts(title: str, expected: dict[str, object]) -> None:
    parsed = parse_title(title)
    for key, value in expected.items():
        assert getattr(parsed, key) == value, key


@pytest.mark.parametrize(
    ("title", "reason"),
    [
        ("2024 Topps Chrome Lot of 5 Rookies", "lot"),
        ("2024 Topps Chrome YOU PICK base RC", "pick-your-card"),
        ("Pick your card 2024 Bowman", "pick-your-card"),
        ("2025 Bowman Chrome Hobby Case Break Spot - Cardinals", "break"),
        ("2024 Topps Chrome Skenes RP reprint", "reprint"),
        ("Custom art card Skenes 2024", "custom"),
        ("2024 Topps Chrome Skenes x2", "multiple-cards"),
        ("2024 Prizm 3 cards Stroud", "multiple-cards"),
    ],
)
def test_disqualifies_non_single_cards(title: str, reason: str) -> None:
    assert parse_title(title).disqualified == reason


def test_clean_single_card_is_not_disqualified() -> None:
    assert parse_title("2024 Topps Chrome Paul Skenes #1 Refractor RC").disqualified is None


def test_phrases_and_compact_numbers() -> None:
    parsed = parse_title("2025 Bowman Chrome #BCP-50 Gold Refractor Wetherholt")
    assert parsed.has_phrase("Gold Refractor")
    assert not parsed.has_phrase("Refractor Gold")
    assert not parsed.has_phrase("")
    assert parsed.has_compact("BCP-50")
    assert parsed.has_compact("bcp 50")
    assert not parsed.has_compact("CP-50")  # must align with token boundaries
    assert not parsed.has_compact("BCP-5")
    assert not parsed.has_compact("--")


def test_tokens_and_compact() -> None:
    assert tokens("Gold-Refractor #BCP-50") == ["gold", "refractor", "bcp", "50"]
    assert compact("CPA-JW") == "cpajw"


def test_whitespace_is_normalized() -> None:
    assert parse_title("  2025   Bowman\tChrome  ").year == 2025
