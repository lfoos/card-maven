"""The JSON Schema in contracts/ must agree with the Python envelope, since
consumers in other languages (and dbt sources) validate against the schema."""

import json
from pathlib import Path

import jsonschema
import pytest

from card_maven.shared.events import Event

SCHEMA = json.loads(
    (Path(__file__).resolve().parents[3] / "contracts/events/envelope.schema.json").read_text()
)
VALIDATOR = jsonschema.Draft202012Validator(SCHEMA, format_checker=jsonschema.FormatChecker())


def test_schema_is_valid() -> None:
    jsonschema.Draft202012Validator.check_schema(SCHEMA)


@pytest.mark.parametrize("subject", [None, "set:2025-bowman-chrome"])
def test_python_events_satisfy_schema(subject: str | None) -> None:
    event = Event(type="market.sync.requested.v1", source="api", subject=subject, data={"a": 1})
    VALIDATOR.validate(json.loads(event.to_json()))


@pytest.mark.parametrize(
    "mutation",
    [
        {"type": "market.sync.requested"},
        {"specversion": "2.0"},
        {"surprise": True},
        {"data": "not-an-object"},
    ],
)
def test_schema_rejects_what_python_rejects(mutation: dict[str, object]) -> None:
    payload = json.loads(Event(type="scan.requested.v1", source="api").to_json())
    payload.update(mutation)
    assert not VALIDATOR.is_valid(payload)
