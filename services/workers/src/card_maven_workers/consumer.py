"""A small, testable Kafka consumer loop with retries and a dead-letter topic.

Delivery is at-least-once: offsets are committed only after a message is
handled (or dead-lettered). Handlers must be idempotent; ``processed_event``
in the database gives them a cheap way to be.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol, cast

from card_maven.shared.errors import CardMavenError
from card_maven.shared.events import Event, EventPublisher, OutboundMessage
from card_maven.shared.logging import get_logger

log = get_logger(__name__)

DLQ_SUFFIX = ".dlq"


class Message(Protocol):
    def value(self) -> bytes | None: ...
    def topic(self) -> str: ...
    def key(self) -> bytes | None: ...
    def error(self) -> Any: ...


class Consumer(Protocol):
    def subscribe(self, topics: list[str]) -> None: ...
    def poll(self, timeout: float) -> Message | None: ...
    def commit(self, message: Message, asynchronous: bool) -> None: ...
    def close(self) -> None: ...


Handler = Callable[[Event], None]


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    attempts: int = 3
    base_delay_seconds: float = 1.0
    max_delay_seconds: float = 30.0

    def delay(self, attempt: int) -> float:
        return float(min(self.base_delay_seconds * 2 ** (attempt - 1), self.max_delay_seconds))


def kafka_consumer(bootstrap_servers: str, group_id: str) -> Consumer:
    from confluent_kafka import Consumer as KafkaConsumer

    return cast(
        Consumer,
        KafkaConsumer(
            {
                "bootstrap.servers": bootstrap_servers,
                "group.id": group_id,
                "enable.auto.commit": False,
                "auto.offset.reset": "earliest",
                # Long handlers (eBay calls) must not trigger a rebalance.
                "max.poll.interval.ms": 600_000,
            }
        ),
    )


class ConsumerLoop:
    def __init__(
        self,
        consumer: Consumer,
        topic: str,
        handler: Handler,
        dead_letters: EventPublisher,
        *,
        retry: RetryPolicy | None = None,
        sleep: Callable[[float], None] = time.sleep,
        poll_timeout: float = 1.0,
    ) -> None:
        self._consumer = consumer
        self._topic = topic
        self._handler = handler
        self._dead_letters = dead_letters
        self._retry = retry or RetryPolicy()
        self._sleep = sleep
        self._poll_timeout = poll_timeout

    def run(self, stop: threading.Event, *, max_messages: int | None = None) -> int:
        """Handle messages until ``stop`` is set. Returns how many were handled."""
        self._consumer.subscribe([self._topic])
        handled = 0
        try:
            while not stop.is_set() and (max_messages is None or handled < max_messages):
                message = self._consumer.poll(self._poll_timeout)
                if message is None:
                    continue
                if message.error():
                    log.warning("kafka_poll_error", error=str(message.error()))
                    continue
                self._handle(message)
                self._consumer.commit(message, asynchronous=False)
                handled += 1
        finally:
            self._consumer.close()
        return handled

    def _handle(self, message: Message) -> None:
        raw = message.value() or b""
        try:
            event = Event.from_json(raw)
        except ValueError as exc:
            self._dead_letter(message, f"undecodable event: {exc}")
            return
        for attempt in range(1, self._retry.attempts + 1):
            try:
                self._handler(event)
                return
            except CardMavenError as exc:
                if not exc.retryable:
                    self._dead_letter(message, f"{exc.code}: {exc.detail}")
                    return
                error = f"{exc.code}: {exc.detail}"
            except Exception as exc:  # unexpected: retry, then dead-letter
                error = f"{type(exc).__name__}: {exc}"
            log.warning(
                "event_handler_failed", event_id=str(event.id), attempt=attempt, error=error
            )
            if attempt < self._retry.attempts:
                self._sleep(self._retry.delay(attempt))
        self._dead_letter(message, f"gave up after {self._retry.attempts} attempts: {error}")

    def _dead_letter(self, message: Message, reason: str) -> None:
        topic = f"{message.topic()}{DLQ_SUFFIX}"
        log.error("event_dead_lettered", topic=topic, reason=reason)
        [result] = self._dead_letters.publish(
            [
                OutboundMessage(
                    topic=topic,
                    key=(message.key() or b"").decode("utf-8", "replace"),
                    value=message.value() or b"",
                    headers={"dlq_reason": reason[:500], "dlq_source_topic": message.topic()},
                )
            ]
        )
        if result is not None:
            # Never commit past a message we couldn't park: stop and let it redeliver.
            raise RuntimeError(f"could not dead-letter message to {topic}") from result
