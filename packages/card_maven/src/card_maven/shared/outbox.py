"""Transactional outbox.

Writers call :func:`enqueue` inside their own database transaction, so an event
is recorded if and only if the business change commits. :class:`OutboxRelay`
publishes pending rows to the bus. Delivery is at-least-once: consumers must be
idempotent on ``Event.id``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from pydantic import ValidationError
from sqlalchemy import BigInteger, Index, String, Text, func, select, text
from sqlalchemy.orm import Mapped, Session, mapped_column, sessionmaker

from card_maven.shared.clock import utcnow
from card_maven.shared.db import Base, session_scope
from card_maven.shared.events import Event, EventPublisher, OutboundMessage
from card_maven.shared.logging import get_logger

log = get_logger(__name__)

MAX_BACKOFF = timedelta(minutes=5)


class OutboxMessage(Base):
    __tablename__ = "outbox_message"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_id: Mapped[uuid.UUID] = mapped_column(unique=True)
    event_type: Mapped[str] = mapped_column(String(200))
    topic: Mapped[str] = mapped_column(String(200))
    partition_key: Mapped[str] = mapped_column(String(200))
    payload: Mapped[dict[str, Any]]
    created_at: Mapped[datetime] = mapped_column(default=utcnow, server_default=func.now())
    available_at: Mapped[datetime] = mapped_column(default=utcnow, server_default=func.now())
    published_at: Mapped[datetime | None]
    attempts: Mapped[int] = mapped_column(default=0, server_default=text("0"))
    last_error: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        # Partial index: the relay only ever scans unpublished rows.
        Index(
            "ix_outbox_message_pending",
            "available_at",
            "id",
            postgresql_where=text("published_at IS NULL"),
        ),
    )


def enqueue(session: Session, event: Event) -> OutboxMessage:
    """Record ``event`` for publication as part of the caller's transaction."""
    message = OutboxMessage(
        event_id=event.id,
        event_type=event.type,
        topic=event.topic,
        partition_key=event.partition_key,
        payload=event.model_dump(mode="json"),
    )
    session.add(message)
    return message


def backoff_for(attempts: int) -> timedelta:
    """Exponential backoff (2s, 4s, 8s, ...) capped at five minutes."""
    if attempts <= 0:
        return timedelta(0)
    return min(timedelta(seconds=2 ** min(attempts, 16)), MAX_BACKOFF)


@dataclass(frozen=True, slots=True)
class RelayResult:
    published: int
    failed: int

    @property
    def claimed(self) -> int:
        return self.published + self.failed


class OutboxRelay:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        publisher: EventPublisher,
        *,
        batch_size: int = 100,
    ) -> None:
        if batch_size < 1:
            raise ValueError("batch_size must be at least 1")
        self._session_factory = session_factory
        self._publisher = publisher
        self._batch_size = batch_size

    def run_once(self) -> RelayResult:
        """Claim one batch, publish it, and record each outcome in one transaction.

        ``FOR UPDATE SKIP LOCKED`` lets several relay replicas run concurrently
        without claiming the same rows.
        """
        with session_scope(self._session_factory) as session:
            now = utcnow()
            rows = list(
                session.scalars(
                    select(OutboxMessage)
                    .where(OutboxMessage.published_at.is_(None))
                    .where(OutboxMessage.available_at <= now)
                    .order_by(OutboxMessage.available_at, OutboxMessage.id)
                    .limit(self._batch_size)
                    .with_for_update(skip_locked=True)
                )
            )
            if not rows:
                return RelayResult(published=0, failed=0)

            # Decode each row on its own: one corrupt payload must not block the
            # rows behind it (a poison message). Bad rows are parked with an error.
            errors: dict[int, Exception] = {}
            sendable: list[tuple[OutboxMessage, OutboundMessage]] = []
            for row in rows:
                try:
                    value = Event.model_validate(row.payload).to_json()
                except ValidationError as exc:
                    errors[row.id] = exc
                    continue
                headers = {"ce_type": row.event_type, "ce_id": str(row.event_id)}
                sendable.append(
                    (row, OutboundMessage(row.topic, row.partition_key, value, headers))
                )

            if sendable:
                try:
                    results = self._publisher.publish([message for _, message in sendable])
                except Exception as exc:  # a publisher that violates its contract
                    results = [exc] * len(sendable)
                if len(results) != len(sendable):
                    mismatch = RuntimeError("publisher returned a result count mismatch")
                    results = [mismatch] * len(sendable)
                for (row, _), error in zip(sendable, results, strict=True):
                    if error is not None:
                        errors[row.id] = error

            published = failed = 0
            for row in rows:
                error = errors.get(row.id)
                if error is None:
                    row.published_at = now
                    published += 1
                else:
                    row.attempts += 1
                    row.last_error = f"{type(error).__name__}: {error}"[:2000]
                    row.available_at = now + backoff_for(row.attempts)
                    failed += 1
            if failed:
                log.warning("outbox_publish_failures", failed=failed, published=published)
            return RelayResult(published=published, failed=failed)
