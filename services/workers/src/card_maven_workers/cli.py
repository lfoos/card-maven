"""``card-maven`` admin and worker CLI."""

from __future__ import annotations

import signal
import threading
from dataclasses import asdict
from pathlib import Path

import click
from pydantic import ValidationError
from sqlalchemy import Engine, delete
from sqlalchemy.orm import Session, sessionmaker

import card_maven.models  # noqa: F401  (registers every table, for cross-context foreign keys)
from card_maven.collection.maintenance import sweep_abandoned_uploads
from card_maven.market.ingestion import MarketSyncService, sync_event
from card_maven.market.maintenance import purge_market_data
from card_maven.market.models import CatalogTerm
from card_maven.market.parsing import parse_title
from card_maven.market.sources.ebay import EbayApi, EbayConfig, EbayTaxonomyClient
from card_maven.market.sources.port import MarketQuery
from card_maven.market.sources.registry import build_sources
from card_maven.market.tracked_sets import expand, load_tracked_sets, sync_tracked_sets
from card_maven.reference_data import load_reference_data, seed_reference_data
from card_maven.shared.clock import utcnow
from card_maven.shared.config import Settings
from card_maven.shared.db import make_engine, make_session_factory, session_scope
from card_maven.shared.errors import CardMavenError
from card_maven.shared.logging import configure_logging
from card_maven.shared.outbox import OutboxRelay
from card_maven.shared.storage.s3 import S3ObjectStore
from card_maven_workers.consumer import ConsumerLoop, kafka_consumer
from card_maven_workers.kafka import KafkaPublisher
from card_maven_workers.market_worker import CONSUMER as MARKET_CONSUMER
from card_maven_workers.market_worker import TOPIC as MARKET_TOPIC
from card_maven_workers.market_worker import MarketSyncHandler
from card_maven_workers.relay import run_relay


class Context:
    """Per-invocation dependencies. The engine is created on first use and
    disposed when the command finishes, so no connections outlive the command."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._engine: Engine | None = None

    def session_factory(self) -> sessionmaker[Session]:
        if self._engine is None:
            self._engine = make_engine(self.settings.database_url.get_secret_value())
        return make_session_factory(self._engine)

    def close(self) -> None:
        if self._engine is not None:
            self._engine.dispose()
            self._engine = None


def _fail(error: CardMavenError) -> None:
    message = error.detail
    if error.extra:
        message += f" {error.extra}"
    raise click.ClickException(message)


@click.group()
@click.pass_context
def cli(ctx: click.Context) -> None:
    """Card Maven operational commands."""
    try:
        settings = Settings()
    except ValidationError as error:
        problems = "; ".join(e["msg"].removeprefix("Value error, ") for e in error.errors())
        raise click.ClickException(f"invalid settings: {problems}") from None
    configure_logging(settings.log_level, json=settings.log_json)
    ctx.obj = Context(settings)
    ctx.call_on_close(ctx.obj.close)


@cli.command("check-config")
@click.pass_obj
def check_config(obj: Context) -> None:
    """Validate the config files without touching the database (used in CI)."""
    try:
        reference = load_reference_data(obj.settings.reference_data_path)
        specs = expand(load_tracked_sets(obj.settings.tracked_sets_path))
    except CardMavenError as error:
        _fail(error)
        return
    sports = {s.code for s in reference.sports}
    brands = {b.slug for b in reference.brands}
    unknown = sorted(
        {f"sport:{s.sport_code}" for s in specs if s.sport_code not in sports}
        | {f"brand:{s.brand_slug}" for s in specs if s.brand_slug not in brands}
    )
    if unknown:
        raise click.ClickException(f"tracked sets reference unknown entries: {unknown}")
    click.echo(f"config ok: {len(specs)} tracked set-years across {len(sports)} sports")


@cli.command()
@click.pass_obj
def seed(obj: Context) -> None:
    """Load sports and brands from the reference data file. Idempotent."""
    try:
        data = load_reference_data(obj.settings.reference_data_path)
        with session_scope(obj.session_factory()) as session:
            result = seed_reference_data(session, data)
    except CardMavenError as error:
        _fail(error)
        return
    click.echo(
        f"seeded {result.sports} sports, {result.brands} brands, "
        f"{result.market_sources} market sources"
    )


@cli.command("sync-tracked-sets")
@click.option("--dry-run", is_flag=True, help="Report changes without saving them.")
@click.option(
    "--config",
    "config_path",
    type=click.Path(path_type=Path, dir_okay=False),
    default=None,
    help="Override the tracked sets file.",
)
@click.pass_obj
def sync_tracked_sets_command(obj: Context, dry_run: bool, config_path: Path | None) -> None:
    """Make the tracked_set table match config/tracked_sets.yaml."""
    path = config_path or obj.settings.tracked_sets_path
    try:
        specs = expand(load_tracked_sets(path))
        with obj.session_factory()() as session:
            result = sync_tracked_sets(session, specs)
            if dry_run:
                session.rollback()
            else:
                session.commit()
    except CardMavenError as error:
        _fail(error)
        return
    summary = ", ".join(f"{k}={v}" for k, v in asdict(result).items())
    click.echo(f"{'dry run: ' if dry_run else ''}tracked sets synced ({summary})")


@cli.command("init-storage")
@click.pass_obj
def init_storage(obj: Context) -> None:
    """Create the media bucket and allow browser uploads (local/test only).

    On AWS, Terraform owns the bucket and its CORS rules.
    """
    if obj.settings.is_deployed:
        raise click.ClickException("init-storage is for local/test; Terraform manages AWS buckets")
    store = S3ObjectStore.from_settings(obj.settings)
    try:
        created = store.ensure_bucket(cors_origins=obj.settings.cors_origins)
    except Exception as exc:  # boto raises many types; report any as a CLI failure
        raise click.ClickException(f"could not reach object storage: {exc}") from exc
    verb = "created" if created else "already exists;"
    click.echo(f"bucket {obj.settings.s3_bucket} {verb} CORS allows {obj.settings.cors_origins}")


@cli.command("outbox-relay")
@click.option("--once", is_flag=True, help="Publish one batch and exit.")
@click.pass_obj
def outbox_relay(obj: Context, once: bool) -> None:
    """Publish pending outbox events to Kafka until SIGTERM/SIGINT."""
    relay = OutboxRelay(
        obj.session_factory(),
        KafkaPublisher(obj.settings.kafka_bootstrap_servers),
        batch_size=obj.settings.outbox_batch_size,
    )
    if once:
        result = relay.run_once()
        click.echo(f"published={result.published} failed={result.failed}")
        return

    run_relay(
        relay,
        poll_interval_seconds=obj.settings.outbox_poll_interval_seconds,
        stop=_stop_on_signals(),
    )


def _stop_on_signals() -> threading.Event:
    stop = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())
    return stop


# ---- Market data -------------------------------------------------------------


@cli.command("market-worker")
@click.option("--max-messages", type=int, default=None, help="Exit after this many (testing).")
@click.pass_obj
def market_worker(obj: Context, max_messages: int | None) -> None:
    """Consume market.sync.requested and run each sync job until SIGTERM/SIGINT."""
    settings = obj.settings
    loop = ConsumerLoop(
        kafka_consumer(settings.kafka_bootstrap_servers, group_id=MARKET_CONSUMER),
        MARKET_TOPIC,
        MarketSyncHandler(obj.session_factory(), build_sources(settings)),
        KafkaPublisher(settings.kafka_bootstrap_servers),
    )
    handled = loop.run(_stop_on_signals(), max_messages=max_messages)
    click.echo(f"handled={handled}")


@cli.command("request-market-sync")
@click.option(
    "--run-now",
    is_flag=True,
    help="Also run the jobs here, without Kafka (local development and CI).",
)
@click.pass_obj
def request_market_sync(obj: Context, run_now: bool) -> None:
    """Queue a market sync for every active tracked set (the nightly job)."""
    factory = obj.session_factory()
    with session_scope(factory) as session:
        jobs = MarketSyncService(session).request_tracked_set_syncs()
        events = [sync_event(job) for job in jobs]
    click.echo(f"queued {len(jobs)} tracked-set sync jobs")
    if run_now:
        # Same handler as the worker, so the queued events are later skipped
        # as already processed if a worker does pick them up.
        handler = MarketSyncHandler(factory, build_sources(obj.settings))
        for event in events:
            handler(event)
        click.echo(f"ran {len(events)} jobs")


@cli.command("purge-market-data")
@click.pass_obj
def purge_market_data_command(obj: Context) -> None:
    """Delete display-only listings past their license's max age, and old sync jobs."""
    with session_scope(obj.session_factory()) as session:
        result = purge_market_data(session)
    click.echo(
        f"purged listings={result.listings} jobs={result.jobs} "
        f"processed_events={result.processed_events}"
    )


@cli.command("sweep-uploads")
@click.pass_obj
def sweep_uploads(obj: Context) -> None:
    """Delete photo uploads that were started but never completed (older than 24h)."""
    with session_scope(obj.session_factory()) as session:
        result = sweep_abandoned_uploads(session)
    store = S3ObjectStore.from_settings(obj.settings)
    orphaned = 0
    for key in result.storage_keys:
        try:
            store.delete(key)
        except CardMavenError:
            orphaned += 1
    click.echo(f"swept images={result.images} orphaned_objects={orphaned}")


@cli.command("sync-ebay-taxonomy")
@click.pass_obj
def sync_ebay_taxonomy(obj: Context) -> None:
    """Load eBay trading-card item specifics (parallels, graders) for title parsing."""
    try:
        values = EbayTaxonomyClient(EbayApi(EbayConfig.from_settings(obj.settings))).aspect_values()
    except CardMavenError as error:
        _fail(error)
        return
    with session_scope(obj.session_factory()) as session:
        session.execute(delete(CatalogTerm).where(CatalogTerm.source == "ebay"))
        session.add_all(CatalogTerm(source="ebay", aspect=a, value=v) for a, v in values)
    click.echo(f"loaded {len(values)} eBay taxonomy terms")


@cli.command("market-search")
@click.argument("keywords", nargs=-1, required=True)
@click.option("--source", "source_code", default="ebay_browse", show_default=True)
@click.option("--year", type=int, required=True)
@click.option("--sport", default="baseball", show_default=True)
@click.pass_obj
def market_search(
    obj: Context, keywords: tuple[str, ...], source_code: str, year: int, sport: str
) -> None:
    """Query one source and print what it returns (for checking keys and queries).

    Nothing is stored. Example: card-maven market-search Bowman Chrome --year 2025
    """
    sources = build_sources(obj.settings.model_copy(update={"market_sources": [source_code]}))
    source = sources.get(source_code)
    if source is None:
        raise click.ClickException(f"source {source_code} is not available (check its settings)")
    query = MarketQuery(sport=sport, year=year, set_name=" ".join(keywords), limit=10)
    try:
        records = source.fetch(query, now=utcnow())
    except CardMavenError as error:
        _fail(error)
        return
    for record in records:
        parsed = parse_title(record.title)
        grade = f"{parsed.grader} {parsed.grade}" if parsed.grader else "raw"
        click.echo(f"{record.price}  {grade:<8}  {record.title}")
    click.echo(f"{len(records)} records from {source_code}")
