"""What a collector sees and does with market data for their own cards.

The API calls this facade; it applies ownership (items are owner-scoped) and
the license gate (via :mod:`card_maven.market.comps`).

Sync jobs are shared between collectors: two people refreshing the same card
reuse one job. So a variant job is visible to anyone who holds that variant,
and a job never reveals who requested it.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from card_maven.collection.models import CollectionItem
from card_maven.collection.service import CollectionRepository
from card_maven.market.comps import Comp, Estimate, Grade, comps_for, current_asks, estimates_for
from card_maven.market.ingestion import MarketSyncService, RequestedJob
from card_maven.market.manual import ManualCompsService, ManualSales
from card_maven.market.models import Listing, MarketSyncJob, Sale, SyncTargetType
from card_maven.shared.clock import utcnow
from card_maven.shared.errors import NotFoundError


@dataclass(frozen=True, slots=True)
class ItemMarket:
    item: CollectionItem
    grade: Grade
    estimate: Estimate | None
    comps: list[Comp]
    asks: list[Listing]
    last_sync: MarketSyncJob | None


class CollectorMarket:
    def __init__(self, session: Session, viewer_id: uuid.UUID) -> None:
        self.session = session
        self.viewer_id = viewer_id
        self.items = CollectionRepository(session, viewer_id)

    def overview(self, item_id: uuid.UUID, *, now: datetime | None = None) -> ItemMarket:
        now = now or utcnow()
        item = self.items.get(item_id)
        return ItemMarket(
            item=item,
            grade=Grade.of(item),
            estimate=estimates_for(self.session, [item], self.viewer_id, now=now).get(item.id),
            comps=comps_for(self.session, item, self.viewer_id),
            asks=current_asks(self.session, item.variant_id, now=now),
            last_sync=self._latest_job(item.variant_id),
        )

    def refresh(self, item_id: uuid.UUID) -> RequestedJob:
        item = self.items.get(item_id)
        return MarketSyncService(self.session).request_variant_sync(
            item.variant_id, requested_by=self.viewer_id
        )

    def job(self, job_id: uuid.UUID) -> MarketSyncJob:
        holds_variant = exists().where(
            CollectionItem.owner_id == self.viewer_id,
            CollectionItem.variant_id == MarketSyncJob.target_id,
        )
        job = self.session.scalars(
            select(MarketSyncJob).where(
                MarketSyncJob.id == job_id,
                MarketSyncJob.target_type == SyncTargetType.VARIANT,
                holds_variant,
            )
        ).one_or_none()
        if job is None:
            raise NotFoundError("sync job not found")
        return job

    def add_sales(self, item_id: uuid.UUID, command: ManualSales) -> list[Sale]:
        return ManualCompsService(self.session, self.viewer_id).add(item_id, command)

    def delete_sale(self, sale_id: uuid.UUID) -> None:
        ManualCompsService(self.session, self.viewer_id).delete(sale_id)

    def estimates(self, items: list[CollectionItem]) -> dict[uuid.UUID, Estimate]:
        return estimates_for(self.session, items, self.viewer_id)

    def _latest_job(self, variant_id: uuid.UUID) -> MarketSyncJob | None:
        return self.session.scalars(
            select(MarketSyncJob)
            .where(
                MarketSyncJob.target_type == SyncTargetType.VARIANT,
                MarketSyncJob.target_id == variant_id,
            )
            .order_by(MarketSyncJob.created_at.desc())
            .limit(1)
        ).one_or_none()
