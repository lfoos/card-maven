from pathlib import Path

import pytest

from card_maven.catalog.reference_data import load_reference_data
from card_maven.market.tracked_sets import expand, load_tracked_sets
from card_maven.shared.errors import InvalidInputError

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_repository_reference_data_is_valid() -> None:
    data = load_reference_data(REPO_ROOT / "config" / "reference_data.yaml")
    assert {s.code for s in data.sports} == {"baseball", "basketball", "football", "hockey"}


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
