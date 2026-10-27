"""Event envelope and publisher port.

Events follow a CloudEvents-style envelope. ``type`` is versioned
(``<context>.<entity>.<action>.v<N>``, e.g. ``market.sync.requested.v1``) and
maps to a Kafka topic by dropping the version, so compatible schema revisions
share a topic. JSON Schemas for each type live in ``contracts/events/``.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator

from card_maven.shared.clock import utcnow

EVENT_TYPE_RE = re.compile(r"^[a-z]+(?:\.[a-z_]+)+\.v[1-9][0-9]*$")


class Event(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    type: str
    source: str
    time: datetime = Field(default_factory=utcnow)
    subject: str | None = None
    specversion: str = "1.0"
    data: dict[str, Any] = Field(default_factory=dict)

    @field_validator("type")
    @classmethod
    def _valid_type(cls, value: str) -> str:
        if not EVENT_TYPE_RE.match(value):
            raise ValueError(
                f"event type must look like '<context>.<entity>.<action>.v<N>', got {value!r}"
            )
        return value

    @field_validator("time")
    @classmethod
    def _aware_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("event time must be timezone-aware")
        return value

    @property
    def topic(self) -> str:
        return topic_for(self.type)

    @property
    def partition_key(self) -> str:
        """Events about the same subject land on the same partition, preserving order."""
        return self.subject or str(self.id)

    def to_json(self) -> bytes:
        return self.model_dump_json().encode("utf-8")

    @classmethod
    def from_json(cls, raw: bytes | str) -> Event:
        return cls.model_validate_json(raw)


def topic_for(event_type: str) -> str:
    if not EVENT_TYPE_RE.match(event_type):
        raise ValueError(f"invalid event type: {event_type!r}")
    return event_type.rsplit(".", 1)[0]


@dataclass(frozen=True, slots=True)
class OutboundMessage:
    topic: str
    key: str
    value: bytes
    headers: dict[str, str] = field(default_factory=dict)


class EventPublisher(Protocol):
    """Port for publishing to the message bus.

    ``publish`` returns one entry per message, in order: ``None`` on confirmed
    delivery, or the exception that prevented it. It must not raise for
    per-message failures, so a batch can partially succeed.
    """

    def publish(self, messages: Sequence[OutboundMessage]) -> list[Exception | None]: ...


class InMemoryPublisher:
    """Test and local-dev publisher. Optionally fails messages for chosen topics."""

    def __init__(self, failing_topics: set[str] | None = None) -> None:
        self.sent: list[OutboundMessage] = []
        self.failing_topics = failing_topics or set()

    def publish(self, messages: Sequence[OutboundMessage]) -> list[Exception | None]:
        results: list[Exception | None] = []
        for message in messages:
            if message.topic in self.failing_topics:
                results.append(ConnectionError(f"simulated failure for {message.topic}"))
            else:
                self.sent.append(message)
                results.append(None)
        return results
