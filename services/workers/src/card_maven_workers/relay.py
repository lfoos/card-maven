"""Long-running outbox relay loop."""

from __future__ import annotations

import threading

from card_maven.shared.logging import get_logger
from card_maven.shared.outbox import OutboxRelay

log = get_logger(__name__)


def run_relay(
    relay: OutboxRelay,
    *,
    poll_interval_seconds: float,
    stop: threading.Event,
    max_iterations: int | None = None,
) -> int:
    """Publish until ``stop`` is set. Returns the number of events published.

    Drains continuously while there is work, and sleeps only when a pass finds
    nothing due. An unexpected error is logged and retried after the poll
    interval, so a transient database outage doesn't kill the process.
    """
    published = 0
    iterations = 0
    while not stop.is_set():
        if max_iterations is not None and iterations >= max_iterations:
            break
        iterations += 1
        try:
            result = relay.run_once()
        except Exception:
            log.exception("outbox_relay_iteration_failed")
            stop.wait(poll_interval_seconds)
            continue
        published += result.published
        if result.claimed == 0:
            stop.wait(poll_interval_seconds)
    log.info("outbox_relay_stopped", published=published)
    return published
