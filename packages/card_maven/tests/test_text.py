import pytest

from card_maven.shared.text import clean, like_pattern, slugify


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("  Bowman   Chrome ", "Bowman Chrome"), ("a\tb\nc", "a b c"), ("", ""), ("x", "x")],
)
def test_clean(raw: str, expected: str) -> None:
    assert clean(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("skenes", "%skenes%"),
        ("100%", "%100\\%%"),
        ("a_b", "%a\\_b%"),
        ("back\\slash", "%back\\\\slash%"),
    ],
)
def test_like_pattern_escapes_wildcards(raw: str, expected: str) -> None:
    assert like_pattern(raw) == expected


def test_slugify() -> None:
    assert slugify("  Upper   Deck ") == "upper-deck"
