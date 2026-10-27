import uuid
from datetime import UTC, datetime

import pytest

from card_maven.shared.errors import InvalidInputError
from card_maven.shared.pagination import decode_cursor, encode_cursor


def test_round_trip_preserves_types() -> None:
    values = (
        datetime(2026, 10, 26, 12, 0, 0, 123456, tzinfo=UTC),
        uuid.uuid4(),
        2025,
        "skenes",
        None,
    )
    token = encode_cursor("year_desc", values)
    assert "=" not in token  # URL-safe, unpadded
    assert decode_cursor(token, expected_sort="year_desc", size=5).values == values


@pytest.mark.parametrize("token", ["!!!", "bm90LWpzb24", "e30", "W10"])
def test_rejects_garbage(token: str) -> None:
    with pytest.raises(InvalidInputError, match="cursor"):
        decode_cursor(token, expected_sort="newest", size=2)


def test_rejects_other_sort_or_shape() -> None:
    token = encode_cursor("oldest", (1, 2))
    with pytest.raises(InvalidInputError, match="does not match"):
        decode_cursor(token, expected_sort="newest", size=2)
    with pytest.raises(InvalidInputError, match="does not match"):
        decode_cursor(token, expected_sort="oldest", size=3)


def test_rejects_unknown_value_tags() -> None:
    import base64
    import json

    raw = base64.urlsafe_b64encode(
        json.dumps({"s": "newest", "v": [{"x": 1}, [1]]}).encode()
    ).decode()
    with pytest.raises(InvalidInputError):
        decode_cursor(raw, expected_sort="newest", size=2)
    raw = base64.urlsafe_b64encode(json.dumps({"s": "newest", "v": [1.5, 2]}).encode()).decode()
    with pytest.raises(InvalidInputError):
        decode_cursor(raw, expected_sort="newest", size=2)
