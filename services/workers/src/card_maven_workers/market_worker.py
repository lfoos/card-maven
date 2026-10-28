"""Handles ``market.sync.requested`` events: runs the sync for one job."""

from __future__ import annotations

import uuid
from collections.abc import Callable, Mapping
from datetime import datetime

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, sessionmaker

from card_maven.market.ingestion import SYNC_REQUESTED, MarketSyncService
from card_maven.market.models import ProcessedEvent
from card_maven.market.sources.port import MarketDataSource
from card_maven.shared.clock import utcnow
from card_maven.shared.db import session_scope
from card_maven.shared.errors import DependencyUnavailableError, InvalidInputError
from card_maven.shared.events import Event
from card_maven.shared.logging import get_logger

log = get_logger(__name__)

CONSUMER = "market-worker"
TOPIC = "market.sync.requested"


class MarketSyncHandler:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        sources: Mapping[str, MarketDataSource],
        *,
        clock: Callable[[], datetime] = utcnow,
        max_attempts: int = 3,
    ) -> None:
        self._sessions = session_factory
        self._sources = sources
        self._clock = clock
        self._max_attempts = max_attempts

    def __call__(self, event: Event) -> None:
        if event.type != SYNC_REQUESTED:
            raise InvalidInputError(f"unexpected event type {event.type}")
        try:
            job_id = uuid.UUID(str(event.data["job_id"]))
        except (KeyError, ValueError) as exc:
            raise InvalidInputError("event has no valid job_id") from exc

        with session_scope(self._sessions) as session:
            if session.get(ProcessedEvent, (CONSUMER, event.id)) is not None:
                log.info("event_already_processed", event_id=str(event.id))
                return
            plan = MarketSyncService(session).plan(job_id)

        now = self._clock()
        fetched = MarketSyncService.fetch(plan, self._sources, now=now)
        if fetched.errors and not fetched.records and fetched.transient:
            attempts = self._attempts(job_id)
            if attempts < self._max_attempts:
                # Every source failed transiently: let the consumer loop retry.
                raise DependencyUnavailableError(
                    f"all market sources unavailable: {fetched.errors}"
                )

        with session_scope(self._sessions) as session:
            # Record the event in the same transaction as its effects.
            inserted = session.execute(
                insert(ProcessedEvent)
                .values(consumer=CONSUMER, event_id=event.id)
                .on_conflict_do_nothing()
                .returning(ProcessedEvent.event_id)
            ).first()
            if inserted is None:
                return  # a concurrent delivery finished first
            stats = MarketSyncService(session).store(plan, fetched, now=now)
        log.info("market_sync_finished", job_id=str(job_id), stats=stats)

    def _attempts(self, job_id: uuid.UUID) -> int:
        from card_maven.market.models import MarketSyncJob

        with session_scope(self._sessions) as session:
            job = session.get(MarketSyncJob, job_id)
            return job.attempts if job else self._max_attempts
