"""Kafka adapter for the ``EventPublisher`` port."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any, Protocol, cast

from card_maven.shared.events import OutboundMessage

# Durable, ordered, duplicate-free per partition (idempotent producer).
PRODUCER_DEFAULTS: dict[str, Any] = {
    "acks": "all",
    "enable.idempotence": True,
    "linger.ms": 5,
    "compression.type": "zstd",
}


class Producer(Protocol):
    def produce(
        self,
        topic: str,
        value: bytes,
        key: bytes,
        headers: list[tuple[str, bytes]],
        on_delivery: Callable[[Any, Any], None],
    ) -> None: ...

    def poll(self, timeout: float) -> int: ...

    def flush(self, timeout: float) -> int: ...


def _default_producer(config: dict[str, Any]) -> Producer:
    # Imported lazily so this module loads without librdkafka (tests, tooling).
    from confluent_kafka import Producer as KafkaProducer

    return cast(Producer, KafkaProducer(config))


class KafkaPublisher:
    def __init__(
        self,
        bootstrap_servers: str,
        *,
        flush_timeout_seconds: float = 10.0,
        extra_config: dict[str, Any] | None = None,
        producer_factory: Callable[[dict[str, Any]], Producer] = _default_producer,
    ) -> None:
        config = {
            **PRODUCER_DEFAULTS,
            "bootstrap.servers": bootstrap_servers,
            **(extra_config or {}),
        }
        self._producer = producer_factory(config)
        self._flush_timeout = flush_timeout_seconds

    def publish(self, messages: Sequence[OutboundMessage]) -> list[Exception | None]:
        """Produce every message, then wait for broker acknowledgements."""
        results: list[Exception | None] = [None] * len(messages)
        delivered = [False] * len(messages)

        def callback_for(index: int) -> Callable[[Any, Any], None]:
            def on_delivery(error: Any, _message: Any) -> None:
                if error is not None:
                    results[index] = RuntimeError(f"kafka delivery failed: {error}")
                delivered[index] = True

            return on_delivery

        for index, message in enumerate(messages):
            try:
                self._producer.produce(
                    message.topic,
                    value=message.value,
                    key=message.key.encode("utf-8"),
                    headers=[(k, v.encode("utf-8")) for k, v in message.headers.items()],
                    on_delivery=callback_for(index),
                )
            except (BufferError, ValueError, RuntimeError) as exc:
                results[index] = exc
                delivered[index] = True
            self._producer.poll(0)

        self._producer.flush(self._flush_timeout)
        for index, done in enumerate(delivered):
            if not done:
                results[index] = TimeoutError("kafka delivery not acknowledged before timeout")
        return results
