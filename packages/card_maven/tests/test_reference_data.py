from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from card_maven.market.tracked_sets import expand, load_tracked_sets
from card_maven.reference_data import load_reference_data

if TYPE_CHECKING:
    from sqlalchemy.orm import Session
from card_maven.shared.errors import InvalidInputError

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_repository_reference_data_is_valid() -> None:
    data = load_reference_data(REPO_ROOT / "config" / "reference_data.yaml")
    assert {s.code for s in data.sports} == {"baseball", "basketball", "football", "hockey"}
    licenses = {s.code: (s.license, s.max_age_hours) for s in data.market_sources}
    assert licenses["ebay_browse"] == ("display_only", 6)  # ADR-0009
    assert licenses["manual"][0] == "analytics"


def test_every_tracked_set_references_known_sport_and_brand() -> None:
    data = load_reference_data(REPO_ROOT / "config" / "reference_data.yaml")
    specs = expand(load_tracked_sets(REPO_ROOT / "config" / "tracked_sets.yaml"))
    assert {s.sport_code for s in specs} <= {s.code for s in data.sports}
    assert {s.brand_slug for s in specs} <= {b.slug for b in data.brands}


@pytest.mark.parametrize(
    "content",
    [
        "sports: []\nbrands: [{slug: 'Bad Slug', name: X}]",
        "sports: [{code: a, name: A}, {code: a, name: B}]\nbrands: []",
        "sports: []",
        "{not yaml",
        "sports: []\nbrands: []\nmarket_sources: [{code: x, name: X, license: display_only}]",
        "sports: []\nbrands: []\nmarket_sources: [{code: x, name: X, license: resale}]",
        "sports: []\nbrands: []\nmarket_sources: [{code: x, name: X, license: analytics},"
        " {code: x, name: Y, license: analytics}]",
    ],
)
def test_rejects_invalid(tmp_path: Path, content: str) -> None:
    path = tmp_path / "ref.yaml"
    path.write_text(content)
    with pytest.raises(InvalidInputError):
        load_reference_data(path)


def test_missing_file(tmp_path: Path) -> None:
    with pytest.raises(InvalidInputError, match="cannot read"):
        load_reference_data(tmp_path / "nope.yaml")


def test_seeding_market_sources_is_idempotent_and_updates_licenses(
    seeded_session: "Session", tmp_path: Path
) -> None:
    from card_maven.market.models import MarketSource
    from card_maven.reference_data import seed_reference_data

    assert seeded_session.get(MarketSource, "ebay_browse").license == "display_only"
    path = tmp_path / "ref.yaml"
    path.write_text(
        "sports: []\nbrands: []\nmarket_sources:\n"
        "  - {code: ebay_browse, name: eBay, license: analytics}\n"
    )
    result = seed_reference_data(seeded_session, load_reference_data(path))
    assert result.market_sources == 1
    assert seeded_session.get(MarketSource, "ebay_browse").license == "analytics"
