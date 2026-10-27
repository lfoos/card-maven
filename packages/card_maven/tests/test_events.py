import uuid
from datetime import datetime

import pytest
from pydantic import ValidationError

from card_maven.shared.events import Event, InMemoryPublisher, OutboundMessage, topic_for


def make_event(**overrides: object) -> Event:
    fields: dict[str, object] = {"type": "market.sync.requested.v1", "source": "test"}
    fields.update(overrides)
    return Event.model_validate(fields)


class TestEnvelope:
    def test_defaults(self) -> None:
        event = make_event()
        assert isinstance(event.id, uuid.UUID)
        assert event.time.tzinfo is not None
        assert event.specversion == "1.0"
        assert event.data == {}

    @pytest.mark.parametrize(
        "event_type",
        ["market.sync.requested", "Market.sync.requested.v1", "sync.v1", "market.sync.v0", ""],
    )
    def test_rejects_bad_types(self, event_type: str) -> None:
        with pytest.raises(ValidationError, match="event type"):
            make_event(type=event_type)

    def test_rejects_naive_time(self) -> None:
        with pytest.raises(ValidationError, match="timezone-aware"):
            make_event(time=datetime(2026, 1, 1))  # noqa: DTZ001 (naive on purpose)

    def test_rejects_unknown_fields(self) -> None:
        with pytest.raises(ValidationError):
            make_event(unexpected="x")

    def test_json_round_trip(self) -> None:
        event = make_event(subject="set:123", data={"year": 2025, "names": ["a"]})
        assert Event.from_json(event.to_json()) == event

    def test_immutable(self) -> None:
        with pytest.raises(ValidationError):
            make_event().type = "x.y.v1"  # type: ignore[misc]


class TestRouting:
    def test_topic_drops_version(self) -> None:
        assert make_event(type="scan.requested.v2").topic == "scan.requested"
        assert topic_for("market.sales.ingested.v10") == "market.sales.ingested"

    def test_topic_for_rejects_invalid(self) -> None:
        with pytest.raises(ValueError, match="invalid event type"):
            topic_for("nope")

    def test_partition_key_prefers_subject(self) -> None:
        event = make_event(subject="variant:42")
        assert event.partition_key == "variant:42"
        unkeyed = make_event()
        assert unkeyed.partition_key == str(unkeyed.id)


class TestInMemoryPublisher:
    def test_records_and_fails_per_topic(self) -> None:
        publisher = InMemoryPublisher(failing_topics={"bad"})
        results = publisher.publish(
            [OutboundMessage("good", "k", b"1"), OutboundMessage("bad", "k", b"2")]
        )
        assert results[0] is None
        assert isinstance(results[1], ConnectionError)
        assert [m.topic for m in publisher.sent] == ["good"]
