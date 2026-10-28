"""Deterministic sample sales for development and tests (``config/market_fixtures.yaml``).

Refused in deployed environments (see ``Settings``). Dates are relative to the
``now`` passed to ``fetch``, so results are stable in tests.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from card_maven.market.parsing import tokens
from card_maven.market.sources.port import MarketQuery, MarketRecord
from card_maven.shared.errors import InvalidInputError
from card_maven.shared.money import Money


class FixtureSale(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    price: str
    days_ago: int = Field(ge=0, le=3650)
    type: Literal["auction", "fixed_price", "best_offer", "other"] = "auction"


class FixtureFile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sales: list[FixtureSale]


class FixtureSource:
    code = "fixture"

    def __init__(self, sales: Sequence[FixtureSale]) -> None:
        self._sales = list(sales)

    @classmethod
    def from_file(cls, path: Path) -> FixtureSource:
        try:
            data = FixtureFile.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
        except (OSError, yaml.YAMLError, ValidationError) as exc:
            raise InvalidInputError(f"market fixtures at {path} are invalid: {exc}") from exc
        return cls(data.sales)

    def fetch(self, query: MarketQuery, *, now: datetime) -> Sequence[MarketRecord]:
        """Sales whose title mentions the query's year and every set-name word."""
        wanted = {str(query.year), *tokens(query.set_name)}
        records = []
        for sale in self._sales:
            if not wanted <= set(tokens(sale.title)):
                continue
            records.append(
                MarketRecord(
                    kind="sale",
                    source_listing_id=sale.id,
                    title=sale.title,
                    price=Money.from_decimal(sale.price, "USD"),
                    occurred_at=now - timedelta(days=sale.days_ago),
                    option=sale.type,
                )
            )
        return records[: query.limit]
