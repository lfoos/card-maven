"""``card-maven`` admin and worker CLI."""

from __future__ import annotations

import signal
import threading
from dataclasses import asdict
from pathlib import Path

import click
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from card_maven.catalog.reference_data import load_reference_data, seed_reference_data
from card_maven.market.tracked_sets import expand, load_tracked_sets, sync_tracked_sets
from card_maven.shared.config import Settings
from card_maven.shared.db import make_engine, make_session_factory, session_scope
from card_maven.shared.errors import CardMavenError
from card_maven.shared.logging import configure_logging
from card_maven.shared.outbox import OutboxRelay
from card_maven_workers.kafka import KafkaPublisher
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
    settings = Settings()
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
    click.echo(f"seeded {result.sports} sports and {result.brands} brands")


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

    stop = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())
    run_relay(relay, poll_interval_seconds=obj.settings.outbox_poll_interval_seconds, stop=stop)
