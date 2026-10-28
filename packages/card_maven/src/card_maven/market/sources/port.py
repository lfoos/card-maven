from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal, Protocol

from card_maven.shared.errors import CardMavenError
from card_maven.shared.money import Money

Kind = Literal["sale", "listing"]
Option = Literal["auction", "fixed_price", "best_offer", "other"]


class MarketSourceError(CardMavenError):
    """A source rejected the request in a way retrying won't fix (bad config, 4xx)."""

    code = "market_source_error"
    status = 502
    title = "Market data source error"


@dataclass(frozen=True, slots=True)
class MarketQuery:
    """What to look for. Sources turn this into their own search syntax."""

    sport: str
    year: int
    set_name: str
    card_number: str | None = None
    players: tuple[str, ...] = ()
    parallel_name: str | None = None
    limit: int = 50

    @property
    def keywords(self) -> str:
        parts = [str(self.year), self.set_name, *self.players]
        if self.card_number:
            parts.append(self.card_number)
        if self.parallel_name and self.parallel_name.lower() != "base":
            parts.append(self.parallel_name)
        return " ".join(parts)


@dataclass(frozen=True, slots=True)
class MarketRecord:
    """One sale or listing as a source reports it, before matching."""

    kind: Kind
    source_listing_id: str
    title: str
    price: Money
    occurred_at: datetime  # sold_at for sales; observed_at for listings
    option: Option = "other"
    bid_count: int | None = None
    url: str | None = None
    image_url: str | None = None
    ends_at: datetime | None = None
    condition_hint: Literal["raw", "graded"] | None = None
    payload: dict[str, Any] = field(default_factory=dict)


class MarketDataSource(Protocol):
    code: str

    def fetch(self, query: MarketQuery, *, now: datetime) -> Sequence[MarketRecord]:
        """Records relevant to ``query``. Raise ``DependencyUnavailableError`` for
        transient failures (retried) and ``MarketSourceError`` for permanent ones."""
