"""Market events must satisfy their payload schemas in contracts/events."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import jsonschema
import pytest
from sqlalchemy.orm import Session

from card_maven.catalog.models import CardVariant
from card_maven.market.ingestion import SALES_INGESTED, FetchResult, MarketSyncService, sync_event
from card_maven.market.sources.fixture import FixtureSource
from card_maven.shared.outbox import OutboxMessage

REPO_ROOT = Path(__file__).resolve().parents[3]
CONTRACTS = REPO_ROOT / "contracts/events"


def validator(event_type: str) -> jsonschema.Draft202012Validator:
    schema = json.loads((CONTRACTS / f"{event_type}.schema.json").read_text())
    jsonschema.Draft202012Validator.check_schema(schema)
    return jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())


@pytest.mark.parametrize("event_type", ["market.sync.requested.v1", "market.sales.ingested.v1"])
def test_schemas_are_valid(event_type: str) -> None:
    validator(event_type)


@pytest.mark.db
def test_sync_requested_matches_schema(seeded_session: Session, gold: CardVariant) -> None:
    job = MarketSyncService(seeded_session).request_variant_sync(gold.id, requested_by=None).job
    validator("market.sync.requested.v1").validate(sync_event(job).data)


@pytest.mark.db
def test_sales_ingested_matches_schema_for_success_and_failure(
    seeded_session: Session, gold: CardVariant
) -> None:
    now = datetime(2026, 10, 27, tzinfo=UTC)
    service = MarketSyncService(seeded_session)
    fixtures = {"fixture": FixtureSource.from_file(REPO_ROOT / "config/market_fixtures.yaml")}
    succeeded = service.request_variant_sync(gold.id, requested_by=None).job
    plan = service.plan(succeeded.id)
    service.store(plan, MarketSyncService.fetch(plan, fixtures, now=now), now=now)
    # A second, failing run (the first would otherwise be reused).
    succeeded.finished_at = now.replace(year=2025)
    failed = service.request_variant_sync(gold.id, requested_by=None).job
    plan = service.plan(failed.id)
    fetched = FetchResult(errors={"ebay_browse": "rate limited"}, transient={"ebay_browse"})
    service.store(plan, fetched, now=now)
    seeded_session.flush()
    rows = seeded_session.query(OutboxMessage).filter(OutboxMessage.event_type == SALES_INGESTED)
    payloads: list[dict[str, Any]] = [r.payload["data"] for r in rows]
    assert {d["status"] for d in payloads} == {"succeeded", "failed"}
    for data in payloads:
        validator("market.sales.ingested.v1").validate(data)


@pytest.mark.parametrize(
    "data",
    [
        {
            "job_id": "x",
            "target_type": "variant",
            "target_id": "00000000-0000-0000-0000-000000000000",
        },
        {
            "job_id": "00000000-0000-0000-0000-000000000000",
            "target_type": "set",
            "target_id": "00000000-0000-0000-0000-000000000000",
        },
    ],
)
def test_sync_requested_rejects_bad_payloads(data: dict[str, str]) -> None:
    assert not validator("market.sync.requested.v1").is_valid(data)
