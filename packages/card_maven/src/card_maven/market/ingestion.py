"""Market sync: plan a job, fetch from sources, and store what matches.

A job runs in three steps so network calls never hold a database transaction:

1. ``plan``   (transaction): mark the job running; work out what to search for.
2. ``fetch``  (no database): ask each source; collect records and errors.
3. ``store``  (transaction): parse, match, enforce licenses, upsert, finish the job.
"""

from __future__ import annotations

import uuid
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, selectinload

from card_maven.catalog.models import Card, CardSet, CardVariant
from card_maven.market.matching import METHOD, MatchResult, MatchTarget, build_target, score
from card_maven.market.models import (
    CatalogTerm,
    License,
    Listing,
    MarketSource,
    MarketSyncJob,
    Sale,
    SyncStatus,
    SyncTargetType,
    TrackedSet,
)
from card_maven.market.parsing import ParsedTitle, parse_title
from card_maven.market.sources.port import MarketDataSource, MarketQuery, MarketRecord
from card_maven.shared.clock import utcnow
from card_maven.shared.errors import CardMavenError, DependencyUnavailableError, NotFoundError
from card_maven.shared.events import Event
from card_maven.shared.logging import get_logger
from card_maven.shared.outbox import enqueue

log = get_logger(__name__)

SYNC_REQUESTED = "market.sync.requested.v1"
SALES_INGESTED = "market.sales.ingested.v1"
EVENT_SOURCE = "card-maven/market"
# Reuse a recent successful variant sync instead of hitting sources again.
REUSE_WINDOW = timedelta(minutes=15)
# A queued/running job older than this is presumed lost (e.g. dead-lettered)
# and no longer blocks a new request.
STALE_AFTER = timedelta(minutes=10)
PARALLEL_ASPECT = "Parallel/Variety"


@dataclass(frozen=True, slots=True)
class SearchPlan:
    query: MarketQuery
    targets: tuple[MatchTarget, ...]
    # Display-only sources only serve on-demand variant syncs: their data
    # expires within hours, so nightly set-wide pulls would be wasted quota.
    include_display_only: bool


@dataclass(frozen=True, slots=True)
class SyncPlan:
    job_id: uuid.UUID
    searches: tuple[SearchPlan, ...]
    licenses: Mapping[str, str]


@dataclass
class FetchResult:
    records: dict[str, list[tuple[SearchPlan, MarketRecord]]] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)
    transient: set[str] = field(default_factory=set)


@dataclass(frozen=True, slots=True)
class RequestedJob:
    job: MarketSyncJob
    created: bool


def sync_event(job: MarketSyncJob) -> Event:
    return Event(
        type=SYNC_REQUESTED,
        source=EVENT_SOURCE,
        subject=f"{job.target_type}:{job.target_id}",
        data={
            "job_id": str(job.id),
            "target_type": job.target_type,
            "target_id": str(job.target_id),
        },
    )


class MarketSyncService:
    def __init__(self, session: Session) -> None:
        self.session = session

    # ---- Requesting ---------------------------------------------------------

    def request_variant_sync(
        self, variant_id: uuid.UUID, *, requested_by: uuid.UUID | None, now: datetime | None = None
    ) -> RequestedJob:
        """Queue a sync for one card, reusing an active or recent job if there is one."""
        now = now or utcnow()
        latest = self.session.scalars(
            select(MarketSyncJob)
            .where(
                MarketSyncJob.target_type == SyncTargetType.VARIANT,
                MarketSyncJob.target_id == variant_id,
            )
            .order_by(MarketSyncJob.created_at.desc())
            .limit(1)
        ).one_or_none()
        if latest is not None and (
            (
                latest.status in (SyncStatus.QUEUED, SyncStatus.RUNNING)
                and now - latest.created_at < STALE_AFTER
            )
            or (
                latest.status == SyncStatus.SUCCEEDED
                and latest.finished_at is not None
                and now - latest.finished_at < REUSE_WINDOW
            )
        ):
            return RequestedJob(latest, created=False)
        return RequestedJob(self._create(SyncTargetType.VARIANT, variant_id, requested_by), True)

    def request_tracked_set_syncs(self) -> list[MarketSyncJob]:
        sets = self.session.scalars(select(TrackedSet).where(TrackedSet.active)).all()
        return [self._create(SyncTargetType.TRACKED_SET, s.id, None) for s in sets]

    def _create(
        self, target_type: SyncTargetType, target_id: uuid.UUID, requested_by: uuid.UUID | None
    ) -> MarketSyncJob:
        job = MarketSyncJob(
            id=uuid.uuid4(),
            target_type=target_type.value,
            target_id=target_id,
            requested_by=requested_by,
            status=SyncStatus.QUEUED,
        )
        self.session.add(job)
        self.session.flush()
        enqueue(self.session, sync_event(job))
        return job

    # ---- Step 1: plan ---------------------------------------------------------

    def plan(self, job_id: uuid.UUID) -> SyncPlan:
        job = self.session.get(MarketSyncJob, job_id, with_for_update=True)
        if job is None:
            raise NotFoundError(f"sync job {job_id} not found")
        job.status = SyncStatus.RUNNING
        job.attempts += 1
        job.started_at = job.started_at or utcnow()
        vocabulary = list(
            self.session.scalars(
                select(CatalogTerm.value).where(CatalogTerm.aspect == PARALLEL_ASPECT)
            )
        )
        if job.target_type == SyncTargetType.VARIANT:
            searches = self._plan_variant(job.target_id, vocabulary)
        else:
            searches = self._plan_tracked_set(job.target_id, vocabulary)
        licenses = {
            s.code: s.license for s in self.session.scalars(select(MarketSource)) if s.enabled
        }
        self.session.flush()
        return SyncPlan(job_id=job.id, searches=tuple(searches), licenses=licenses)

    def _variants_query(self) -> Any:
        return select(CardVariant).options(
            selectinload(CardVariant.card).options(
                selectinload(Card.players),
                selectinload(Card.card_set).selectinload(CardSet.parallels),
            ),
            selectinload(CardVariant.parallel),
        )

    def _plan_variant(self, variant_id: uuid.UUID, vocabulary: list[str]) -> list[SearchPlan]:
        variant = self.session.scalars(
            self._variants_query().where(CardVariant.id == variant_id)
        ).one_or_none()
        if variant is None:
            raise NotFoundError(f"card variant {variant_id} not found")
        card = variant.card
        query = MarketQuery(
            sport=card.card_set.sport_code,
            year=card.card_set.year,
            set_name=card.card_set.name,
            card_number=card.card_number,
            players=tuple(p.full_name for p in card.players),
            parallel_name=variant.parallel.name,
        )
        return [SearchPlan(query, (build_target(variant, vocabulary),), include_display_only=True)]

    def _plan_tracked_set(self, tracked_id: uuid.UUID, vocabulary: list[str]) -> list[SearchPlan]:
        tracked = self.session.get(TrackedSet, tracked_id)
        if tracked is None:
            raise NotFoundError(f"tracked set {tracked_id} not found")
        variants = self.session.scalars(
            self._variants_query()
            .join(CardVariant.card)
            .join(Card.card_set)
            .where(
                CardSet.sport_code == tracked.sport_code,
                CardSet.brand_slug == tracked.brand_slug,
                CardSet.year == tracked.year,
                func.lower(CardSet.name) == tracked.set_name.lower(),
            )
        ).all()
        query = MarketQuery(
            sport=tracked.sport_code, year=tracked.year, set_name=tracked.set_name, limit=200
        )
        targets = tuple(build_target(v, vocabulary) for v in variants)
        return [SearchPlan(query, targets, include_display_only=False)]

    # ---- Step 2: fetch (no database) --------------------------------------------

    @staticmethod
    def fetch(
        plan: SyncPlan, sources: Mapping[str, MarketDataSource], *, now: datetime
    ) -> FetchResult:
        result = FetchResult()
        for code, source in sources.items():
            license_ = plan.licenses.get(code)
            if license_ is None:
                continue  # not registered (or disabled) in market_source
            collected: list[tuple[SearchPlan, MarketRecord]] = []
            try:
                for search in plan.searches:
                    if license_ == License.DISPLAY_ONLY and not search.include_display_only:
                        continue
                    collected.extend((search, r) for r in source.fetch(search.query, now=now))
            except DependencyUnavailableError as exc:
                result.errors[code] = exc.detail
                result.transient.add(code)
                continue
            except CardMavenError as exc:
                result.errors[code] = exc.detail
                continue
            except Exception:
                # A bug in one adapter (e.g. an unexpected payload shape) must
                # not discard the other sources' results. Details go to logs,
                # not to the job (which collectors can see).
                log.exception("market_source_crashed", source=code, job_id=str(plan.job_id))
                result.errors[code] = "unexpected error (see worker logs)"
                continue
            result.records[code] = collected
        return result

    # ---- Step 3: store ----------------------------------------------------------

    def store(self, plan: SyncPlan, fetched: FetchResult, *, now: datetime) -> dict[str, Any]:
        stats: dict[str, Any] = {}
        for code, pairs in fetched.records.items():
            counts: Counter[str] = Counter(fetched=len(pairs))
            license_ = plan.licenses[code]
            for search, record in pairs:
                counts[self._store_one(code, license_, search, record, now)] += 1
            stats[code] = dict(counts)
        for code, error in fetched.errors.items():
            stats[code] = {"error": error, "transient": code in fetched.transient}

        job = self.session.get(MarketSyncJob, plan.job_id)
        assert job is not None
        job.stats = stats
        job.finished_at = now
        if fetched.records or not fetched.errors:
            job.status = SyncStatus.SUCCEEDED
            job.error = None
        else:
            job.status = SyncStatus.FAILED
            job.error = "; ".join(f"{c}: {e}" for c, e in sorted(fetched.errors.items()))
        enqueue(
            self.session,
            Event(
                type=SALES_INGESTED,
                source=EVENT_SOURCE,
                subject=f"{job.target_type}:{job.target_id}",
                data={"job_id": str(job.id), "status": job.status, "stats": stats},
            ),
        )
        self.session.flush()
        return stats

    def fail(self, job_id: uuid.UUID, error: str) -> None:
        job = self.session.get(MarketSyncJob, job_id)
        if job is not None:
            job.status = SyncStatus.FAILED
            job.error = error[:2000]
            job.finished_at = utcnow()
            self.session.flush()

    def _store_one(
        self, code: str, license_: str, search: SearchPlan, record: MarketRecord, now: datetime
    ) -> str:
        if record.kind == "sale" and license_ != License.ANALYTICS:
            return "rejected_license"  # display-only data can never become a comp
        parsed = parse_title(record.title)
        if parsed.disqualified:
            return "disqualified"
        best: tuple[MatchResult, MatchTarget] | None = None
        for target in search.targets:
            result = score(parsed, target)
            if result.is_match and (best is None or result.confidence > best[0].confidence):
                best = (result, target)
        if record.kind == "listing":
            if best is None:
                return "unmatched"  # only matched listings are kept (data minimization)
            self._upsert_listing(code, record, parsed, best)
            return "stored"
        self._upsert_sale(code, record, parsed, best)
        return "stored" if best else "stored_unmatched"

    @staticmethod
    def _common(
        code: str,
        record: MarketRecord,
        parsed: ParsedTitle,
        best: tuple[MatchResult, MatchTarget] | None,
    ) -> dict[str, Any]:
        graded = parsed.condition == "graded"
        return {
            "id": uuid.uuid4(),
            "source_code": code,
            "source_listing_id": record.source_listing_id,
            "variant_id": best[1].variant_id if best else None,
            "match_confidence": best[0].confidence if best else None,
            "match_method": METHOD if best else None,
            "title": record.title[:500],
            "price_minor": record.price.amount_minor,
            "currency": record.price.currency,
            "condition": parsed.condition,
            "grader": parsed.grader if graded else None,
            "grade": parsed.grade if graded else None,
            "url": record.url,
            "payload": record.payload,
        }

    def _upsert_sale(
        self,
        code: str,
        record: MarketRecord,
        parsed: ParsedTitle,
        best: tuple[MatchResult, MatchTarget] | None,
    ) -> None:
        values = {
            **self._common(code, record, parsed, best),
            "sold_at": record.occurred_at,
            "sale_type": record.option,
        }
        statement = insert(Sale).values(**values)
        updatable: dict[str, Any] = {
            k: statement.excluded[k]
            for k in values
            if k not in {"id", "source_code", "source_listing_id"}
        }
        updatable["updated_at"] = func.now()
        # Re-ingesting never demotes an existing match to unmatched.
        updatable["variant_id"] = func.coalesce(statement.excluded.variant_id, Sale.variant_id)
        updatable["match_confidence"] = func.coalesce(
            statement.excluded.match_confidence, Sale.match_confidence
        )
        updatable["match_method"] = func.coalesce(
            statement.excluded.match_method, Sale.match_method
        )
        self.session.execute(
            statement.on_conflict_do_update(
                index_elements=["source_code", "source_listing_id"], set_=updatable
            )
        )

    def _upsert_listing(
        self,
        code: str,
        record: MarketRecord,
        parsed: ParsedTitle,
        best: tuple[MatchResult, MatchTarget],
    ) -> None:
        values = {
            **self._common(code, record, parsed, best),
            "buying_option": record.option,
            "bid_count": record.bid_count,
            "image_url": record.image_url,
            "observed_at": record.occurred_at,
            "ends_at": record.ends_at,
        }
        statement = insert(Listing).values(**values)
        updatable: dict[str, Any] = {
            k: statement.excluded[k]
            for k in values
            if k not in {"id", "source_code", "source_listing_id"}
        }
        updatable["updated_at"] = func.now()
        self.session.execute(
            statement.on_conflict_do_update(
                index_elements=["source_code", "source_listing_id"], set_=updatable
            )
        )
