from collections.abc import Sequence
from datetime import timedelta

import pytest
from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from card_maven.shared.clock import utcnow
from card_maven.shared.db import session_scope
from card_maven.shared.events import Event, InMemoryPublisher, OutboundMessage
from card_maven.shared.outbox import OutboxMessage, OutboxRelay, backoff_for, enqueue

pytestmark = pytest.mark.db


def event(subject: str = "set:1", event_type: str = "market.sync.requested.v1") -> Event:
    return Event(type=event_type, source="test", subject=subject, data={"n": 1})


def pending(factory: sessionmaker[Session]) -> list[OutboxMessage]:
    with session_scope(factory) as session:
        return list(
            session.scalars(select(OutboxMessage).where(OutboxMessage.published_at.is_(None)))
        )


class TestEnqueue:
    def test_enqueue_is_part_of_the_callers_transaction(self, db_session: Session) -> None:
        e = event()
        row = enqueue(db_session, e)
        db_session.flush()
        assert row.topic == "market.sync.requested"
        assert row.partition_key == "set:1"
        assert row.payload["id"] == str(e.id)
        assert row.published_at is None
        assert row.attempts == 0

    def test_rolled_back_transaction_drops_the_event(
        self, committing_session_factory: sessionmaker[Session]
    ) -> None:
        def enqueue_then_fail() -> None:
            with session_scope(committing_session_factory) as session:
                enqueue(session, event())
                raise RuntimeError("business change failed")

        with pytest.raises(RuntimeError):
            enqueue_then_fail()
        assert pending(committing_session_factory) == []

    def test_same_event_cannot_be_enqueued_twice(self, db_session: Session) -> None:
        e = event()
        enqueue(db_session, e)
        db_session.flush()
        enqueue(db_session, e)
        with pytest.raises(Exception, match="uq_outbox_message_event_id"):
            db_session.flush()
        db_session.rollback()


class TestRelay:
    def test_publishes_pending_in_order(
        self, committing_session_factory: sessionmaker[Session]
    ) -> None:
        with session_scope(committing_session_factory) as session:
            for i in range(3):
                enqueue(session, event(subject=f"set:{i}"))
        publisher = InMemoryPublisher()
        result = OutboxRelay(committing_session_factory, publisher).run_once()
        assert (result.published, result.failed, result.claimed) == (3, 0, 3)
        assert [m.key for m in publisher.sent] == ["set:0", "set:1", "set:2"]
        assert publisher.sent[0].headers["ce_type"] == "market.sync.requested.v1"
        assert Event.from_json(publisher.sent[0].value).subject == "set:0"
        assert pending(committing_session_factory) == []

    def test_nothing_pending(self, committing_session_factory: sessionmaker[Session]) -> None:
        result = OutboxRelay(committing_session_factory, InMemoryPublisher()).run_once()
        assert result.claimed == 0

    def test_respects_batch_size(self, committing_session_factory: sessionmaker[Session]) -> None:
        with session_scope(committing_session_factory) as session:
            for i in range(5):
                enqueue(session, event(subject=f"s{i}"))
        relay = OutboxRelay(committing_session_factory, InMemoryPublisher(), batch_size=2)
        assert [relay.run_once().published for _ in range(4)] == [2, 2, 1, 0]

    def test_partial_failure_records_error_and_backs_off(
        self, committing_session_factory: sessionmaker[Session]
    ) -> None:
        with session_scope(committing_session_factory) as session:
            enqueue(session, event(event_type="market.sync.requested.v1"))
            enqueue(session, event(event_type="scan.requested.v1"))
        publisher = InMemoryPublisher(failing_topics={"scan.requested"})
        relay = OutboxRelay(committing_session_factory, publisher)

        result = relay.run_once()
        assert (result.published, result.failed) == (1, 1)
        [failed] = pending(committing_session_factory)
        assert failed.topic == "scan.requested"
        assert failed.attempts == 1
        assert failed.last_error is not None
        assert "simulated failure" in failed.last_error
        assert failed.available_at > utcnow()

        # Backed-off rows are not retried early...
        assert relay.run_once().claimed == 0
        # ...but are retried once due, and succeed when the bus recovers.
        with session_scope(committing_session_factory) as session:
            session.execute(update(OutboxMessage).values(available_at=utcnow()))
        publisher.failing_topics.clear()
        assert relay.run_once().published == 1
        assert pending(committing_session_factory) == []

    def test_publisher_that_raises_is_treated_as_batch_failure(
        self, committing_session_factory: sessionmaker[Session]
    ) -> None:
        class Exploding:
            def publish(self, messages: Sequence[OutboundMessage]) -> list[Exception | None]:
                raise RuntimeError("broker gone")

        with session_scope(committing_session_factory) as session:
            enqueue(session, event())
        result = OutboxRelay(committing_session_factory, Exploding()).run_once()
        assert result.failed == 1
        [row] = pending(committing_session_factory)
        assert row.last_error == "RuntimeError: broker gone"

    def test_publisher_result_count_mismatch_fails_safe(
        self, committing_session_factory: sessionmaker[Session]
    ) -> None:
        class Short:
            def publish(self, messages: Sequence[OutboundMessage]) -> list[Exception | None]:
                return []

        with session_scope(committing_session_factory) as session:
            enqueue(session, event())
        assert OutboxRelay(committing_session_factory, Short()).run_once().failed == 1

    def test_concurrent_relays_never_claim_the_same_row(
        self, committing_session_factory: sessionmaker[Session]
    ) -> None:
        with session_scope(committing_session_factory) as session:
            for i in range(4):
                enqueue(session, event(subject=f"s{i}"))

        second_publisher = InMemoryPublisher()
        second_relay = OutboxRelay(committing_session_factory, second_publisher)
        second_results = []

        class PublishesWhileSecondRelayRuns:
            """Runs the second relay while the first still holds its row locks."""

            def __init__(self) -> None:
                self.sent: list[OutboundMessage] = []

            def publish(self, messages: Sequence[OutboundMessage]) -> list[Exception | None]:
                second_results.append(second_relay.run_once())
                self.sent.extend(messages)
                return [None] * len(messages)

        first_publisher = PublishesWhileSecondRelayRuns()
        first = OutboxRelay(committing_session_factory, first_publisher, batch_size=2).run_once()

        assert first.published == 2
        assert second_results[0].published == 2
        first_keys = {m.key for m in first_publisher.sent}
        second_keys = {m.key for m in second_publisher.sent}
        assert first_keys.isdisjoint(second_keys)
        assert first_keys | second_keys == {"s0", "s1", "s2", "s3"}

    def test_rejects_invalid_batch_size(
        self, committing_session_factory: sessionmaker[Session]
    ) -> None:
        with pytest.raises(ValueError, match="batch_size"):
            OutboxRelay(committing_session_factory, InMemoryPublisher(), batch_size=0)


@pytest.mark.parametrize(
    ("attempts", "expected"),
    [
        (0, timedelta(0)),
        (1, timedelta(seconds=2)),
        (3, timedelta(seconds=8)),
        (50, timedelta(minutes=5)),
    ],
)
def test_backoff(attempts: int, expected: timedelta) -> None:
    assert backoff_for(attempts) == expected


class TestPoisonMessages:
    """QA: one undecodable row must not block every event queued behind it."""

    def test_corrupt_payload_is_parked_and_others_still_publish(
        self, committing_session_factory: sessionmaker[Session]
    ) -> None:
        with session_scope(committing_session_factory) as session:
            bad = enqueue(session, event(subject="bad"))
            enqueue(session, event(subject="good"))
            session.flush()
            bad.payload = {"type": "not a valid event"}

        publisher = InMemoryPublisher()
        result = OutboxRelay(committing_session_factory, publisher).run_once()

        assert (result.published, result.failed) == (1, 1)
        assert [m.key for m in publisher.sent] == ["good"]
        [parked] = pending(committing_session_factory)
        assert parked.partition_key == "bad"
        assert parked.last_error is not None
        assert parked.last_error.startswith("ValidationError")
