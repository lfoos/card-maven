"""Round trip through a real Kafka broker: publish, consume, dead-letter.

Runs when CARD_MAVEN_TEST_KAFKA is set (CI starts a broker); skipped otherwise.
"""

import os
import threading
import time
import uuid

import pytest

from card_maven.shared.errors import InvalidInputError
from card_maven.shared.events import Event, OutboundMessage
from card_maven_workers.consumer import ConsumerLoop, kafka_consumer
from card_maven_workers.kafka import KafkaPublisher

BOOTSTRAP = os.environ.get("CARD_MAVEN_TEST_KAFKA")
pytestmark = pytest.mark.skipif(
    not BOOTSTRAP, reason="set CARD_MAVEN_TEST_KAFKA to run against a broker"
)


def create_topics(*names: str) -> None:
    from confluent_kafka.admin import AdminClient, NewTopic

    admin = AdminClient({"bootstrap.servers": BOOTSTRAP})
    futures = admin.create_topics(
        [NewTopic(n, num_partitions=1, replication_factor=1) for n in names]
    )
    for future in futures.values():
        future.result(timeout=30)


def test_publish_consume_and_dead_letter_round_trip() -> None:
    assert BOOTSTRAP
    topic = f"it.{uuid.uuid4().hex[:8]}"
    create_topics(topic, f"{topic}.dlq")
    publisher = KafkaPublisher(BOOTSTRAP)
    good = Event(type="market.sync.requested.v1", source="it", data={"n": 1})
    bad = Event(type="market.sync.requested.v1", source="it", data={"n": 2})
    results = publisher.publish(
        [
            OutboundMessage(topic, "k", good.to_json(), {"ce_type": good.type}),
            OutboundMessage(topic, "k", bad.to_json(), {"ce_type": bad.type}),
        ]
    )
    assert results == [None, None]

    seen: list[int] = []

    def handler(event: Event) -> None:
        if event.data["n"] == 2:
            raise InvalidInputError("not wanted")
        seen.append(event.data["n"])

    group = f"it-{uuid.uuid4().hex[:6]}"
    handled = 0
    deadline = time.monotonic() + 60
    while handled < 2 and time.monotonic() < deadline:
        # Each run closes its consumer; the group's committed offsets carry over.
        consumer = kafka_consumer(BOOTSTRAP, group)
        loop = ConsumerLoop(consumer, topic, handler, publisher, poll_timeout=0.5)
        stop = threading.Event()
        timer = threading.Timer(10, stop.set)
        timer.start()
        handled += loop.run(stop, max_messages=2 - handled)
        timer.cancel()
    assert seen == [1]

    dlq = kafka_consumer(BOOTSTRAP, f"dlq-{uuid.uuid4().hex[:6]}")
    dlq.subscribe([f"{topic}.dlq"])
    message = None
    deadline = time.monotonic() + 30
    while message is None and time.monotonic() < deadline:
        candidate = dlq.poll(1.0)
        if candidate is not None and not candidate.error():
            message = candidate
    dlq.close()
    assert message is not None
    assert Event.from_json(message.value() or b"").id == bad.id
