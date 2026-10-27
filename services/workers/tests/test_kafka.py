from collections.abc import Callable
from typing import Any

import pytest

from card_maven.shared.events import OutboundMessage
from card_maven_workers.kafka import PRODUCER_DEFAULTS, KafkaPublisher


class FakeProducer:
    """Records produce calls; delivers, fails, or drops each message on flush."""

    def __init__(self, config: dict[str, Any], outcomes: dict[str, str] | None = None) -> None:
        self.config = config
        self.outcomes = outcomes or {}
        self.produced: list[dict[str, Any]] = []
        self._pending: list[tuple[str, Callable[[Any, Any], None]]] = []

    def produce(
        self,
        topic: str,
        value: bytes,
        key: bytes,
        headers: list[tuple[str, bytes]],
        on_delivery: Callable[[Any, Any], None],
    ) -> None:
        outcome = self.outcomes.get(key.decode())
        if outcome == "buffer_full":
            raise BufferError("queue full")
        self.produced.append({"topic": topic, "value": value, "key": key, "headers": headers})
        self._pending.append((key.decode(), on_delivery))

    def poll(self, timeout: float) -> int:
        return 0

    def flush(self, timeout: float) -> int:
        remaining = 0
        for key, callback in self._pending:
            outcome = self.outcomes.get(key, "ok")
            if outcome == "ok":
                callback(None, object())
            elif outcome == "error":
                callback("Broker: Not enough in-sync replicas", object())
            else:  # "timeout": never acknowledged
                remaining += 1
        self._pending.clear()
        return remaining


def publisher_with(
    outcomes: dict[str, str] | None = None,
) -> tuple[KafkaPublisher, list[FakeProducer]]:
    created: list[FakeProducer] = []

    def factory(config: dict[str, Any]) -> FakeProducer:
        producer = FakeProducer(config, outcomes)
        created.append(producer)
        return producer

    return KafkaPublisher("broker:9092", producer_factory=factory), created


def msg(key: str) -> OutboundMessage:
    return OutboundMessage(
        "market.sync.requested", key, b"{}", {"ce_type": "market.sync.requested.v1"}
    )


def test_producer_configured_for_durability() -> None:
    _, [producer] = publisher_with()
    assert producer.config["bootstrap.servers"] == "broker:9092"
    for key, value in PRODUCER_DEFAULTS.items():
        assert producer.config[key] == value


def test_publishes_with_key_and_headers() -> None:
    publisher, [producer] = publisher_with()
    assert publisher.publish([msg("a"), msg("b")]) == [None, None]
    assert producer.produced[0]["key"] == b"a"
    assert producer.produced[0]["headers"] == [("ce_type", b"market.sync.requested.v1")]


def test_reports_each_failure_mode_per_message() -> None:
    publisher, _ = publisher_with({"err": "error", "slow": "timeout", "full": "buffer_full"})
    ok, err, slow, full = publisher.publish([msg("ok"), msg("err"), msg("slow"), msg("full")])
    assert ok is None
    assert isinstance(err, RuntimeError)
    assert "in-sync replicas" in str(err)
    assert isinstance(slow, TimeoutError)
    assert isinstance(full, BufferError)


def test_empty_batch() -> None:
    publisher, _ = publisher_with()
    assert publisher.publish([]) == []


def test_extra_config_overrides_defaults() -> None:
    created: list[FakeProducer] = []
    KafkaPublisher(
        "b:9092",
        extra_config={"linger.ms": 50},
        producer_factory=lambda c: created.append(FakeProducer(c)) or created[-1],
    )
    assert created[0].config["linger.ms"] == 50


def test_default_factory_builds_real_producer() -> None:
    pytest.importorskip("confluent_kafka")
    # Building a producer does not connect, so this is safe without a broker.
    publisher = KafkaPublisher("localhost:1")
    assert publisher.publish([]) == []
