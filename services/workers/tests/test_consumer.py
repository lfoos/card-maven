import threading
from collections.abc import Sequence
from typing import Any

import pytest

from card_maven.shared.errors import DependencyUnavailableError, InvalidInputError
from card_maven.shared.events import Event, InMemoryPublisher, OutboundMessage
from card_maven_workers.consumer import ConsumerLoop, RetryPolicy


class FakeMessage:
    def __init__(
        self,
        value: bytes | None,
        topic: str = "market.sync.requested",
        key: bytes | None = b"k",
        error: Any = None,
    ) -> None:
        self._value, self._topic, self._key, self._error = value, topic, key, error

    def value(self) -> bytes | None:
        return self._value

    def topic(self) -> str:
        return self._topic

    def key(self) -> bytes | None:
        return self._key

    def error(self) -> Any:
        return self._error


class FakeConsumer:
    def __init__(self, messages: Sequence[FakeMessage | None]) -> None:
        self.queue = list(messages)
        self.subscribed: list[str] = []
        self.committed: list[FakeMessage] = []
        self.closed = False
        self.stop = threading.Event()

    def subscribe(self, topics: list[str]) -> None:
        self.subscribed = topics

    def poll(self, timeout: float) -> FakeMessage | None:
        if not self.queue:
            self.stop.set()
            return None
        return self.queue.pop(0)

    def commit(self, message: FakeMessage, asynchronous: bool) -> None:
        assert asynchronous is False
        self.committed.append(message)

    def close(self) -> None:
        self.closed = True


def event_bytes(**data: Any) -> bytes:
    return Event(type="market.sync.requested.v1", source="test", data=data).to_json()


def loop(
    consumer: FakeConsumer, handler: Any, publisher: Any = None, sleeps: list[float] | None = None
) -> ConsumerLoop:
    recorded = sleeps if sleeps is not None else []
    return ConsumerLoop(
        consumer,
        "market.sync.requested",
        handler,
        publisher or InMemoryPublisher(),
        retry=RetryPolicy(attempts=3, base_delay_seconds=1),
        sleep=recorded.append,
    )


def test_handles_and_commits_in_order() -> None:
    seen: list[str] = []
    consumer = FakeConsumer([FakeMessage(event_bytes(n=1)), None, FakeMessage(event_bytes(n=2))])
    handled = loop(consumer, lambda e: seen.append(e.data["n"])).run(consumer.stop)
    assert (handled, seen, len(consumer.committed)) == (2, [1, 2], 2)
    assert consumer.subscribed == ["market.sync.requested"]
    assert consumer.closed


def test_transient_errors_retry_with_backoff_then_succeed() -> None:
    calls = {"n": 0}

    def flaky(event: Event) -> None:
        calls["n"] += 1
        if calls["n"] < 3:
            raise DependencyUnavailableError("down")

    sleeps: list[float] = []
    publisher = InMemoryPublisher()
    consumer = FakeConsumer([FakeMessage(event_bytes())])
    loop(consumer, flaky, publisher, sleeps).run(consumer.stop)
    assert calls["n"] == 3
    assert sleeps == [1.0, 2.0]
    assert publisher.sent == []
    assert len(consumer.committed) == 1


def test_exhausted_retries_go_to_dead_letter_topic() -> None:
    def always_down(event: Event) -> None:
        raise DependencyUnavailableError("down")

    publisher = InMemoryPublisher()
    consumer = FakeConsumer([FakeMessage(event_bytes())])
    loop(consumer, always_down, publisher).run(consumer.stop)
    [dead] = publisher.sent
    assert dead.topic == "market.sync.requested.dlq"
    assert dead.headers["dlq_source_topic"] == "market.sync.requested"
    assert "gave up after 3 attempts" in dead.headers["dlq_reason"]
    assert len(consumer.committed) == 1  # parked, so the partition moves on


@pytest.mark.parametrize(("value", "reason"), [(b"not json", "undecodable"), (None, "undecodable")])
def test_poison_messages_are_dead_lettered_without_retry(value: bytes | None, reason: str) -> None:
    publisher = InMemoryPublisher()
    consumer = FakeConsumer([FakeMessage(value, key=None)])
    loop(consumer, lambda e: None, publisher).run(consumer.stop)
    assert reason in publisher.sent[0].headers["dlq_reason"]
    assert publisher.sent[0].key == ""


def test_permanent_errors_skip_retries() -> None:
    calls = {"n": 0}

    def invalid(event: Event) -> None:
        calls["n"] += 1
        raise InvalidInputError("bad payload")

    publisher = InMemoryPublisher()
    consumer = FakeConsumer([FakeMessage(event_bytes())])
    loop(consumer, invalid, publisher).run(consumer.stop)
    assert calls["n"] == 1
    assert publisher.sent[0].headers["dlq_reason"] == "invalid_input: bad payload"


def test_unexpected_errors_are_retried_then_parked() -> None:
    def crash(event: Event) -> None:
        raise KeyError("surprise")

    publisher = InMemoryPublisher()
    consumer = FakeConsumer([FakeMessage(event_bytes())])
    loop(consumer, crash, publisher).run(consumer.stop)
    assert "KeyError" in publisher.sent[0].headers["dlq_reason"]


def test_never_commits_past_a_message_it_could_not_park() -> None:
    class Broken:
        def publish(self, messages: Sequence[OutboundMessage]) -> list[Exception | None]:
            return [ConnectionError("broker gone")]

    consumer = FakeConsumer([FakeMessage(b"garbage")])
    with pytest.raises(RuntimeError, match="could not dead-letter"):
        loop(consumer, lambda e: None, Broken()).run(consumer.stop)
    assert consumer.committed == []
    assert consumer.closed


def test_poll_errors_are_skipped_and_max_messages_bounds() -> None:
    consumer = FakeConsumer(
        [
            FakeMessage(b"x", error="broker hiccup"),
            FakeMessage(event_bytes()),
            FakeMessage(event_bytes()),
        ]
    )
    assert loop(consumer, lambda e: None).run(threading.Event(), max_messages=1) == 1


def test_retry_delay_is_capped() -> None:
    policy = RetryPolicy(attempts=10, base_delay_seconds=1, max_delay_seconds=5)
    assert [policy.delay(n) for n in (1, 2, 3, 4, 5)] == [1, 2, 4, 5, 5]
