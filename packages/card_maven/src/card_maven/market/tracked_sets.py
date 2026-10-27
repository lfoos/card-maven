"""Declarative tracked-set configuration (``config/tracked_sets.yaml``).

Adding a set or widening a year range is a config edit: no code, no migration.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from card_maven.catalog.models import Brand, Sport
from card_maven.market.models import TrackedSet
from card_maven.shared.errors import InvalidInputError
from card_maven.shared.text import slugify

MIN_YEAR, MAX_YEAR = 1860, 2100


def brand_slug(name: str) -> str:
    return slugify(name)


class YearRange(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    start: int = Field(alias="from", ge=MIN_YEAR, le=MAX_YEAR)
    end: int = Field(alias="to", ge=MIN_YEAR, le=MAX_YEAR)

    @model_validator(mode="after")
    def _ordered(self) -> YearRange:
        if self.start > self.end:
            raise ValueError(f"'from' ({self.start}) must not be after 'to' ({self.end})")
        return self

    def years(self) -> range:
        return range(self.start, self.end + 1)


class YearOverride(BaseModel):
    """Per-set override; either bound may be omitted to inherit the default."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    start: int | None = Field(default=None, alias="from", ge=MIN_YEAR, le=MAX_YEAR)
    end: int | None = Field(default=None, alias="to", ge=MIN_YEAR, le=MAX_YEAR)

    def resolve(self, default: YearRange) -> YearRange:
        return YearRange(
            start=self.start if self.start is not None else default.start,
            end=self.end if self.end is not None else default.end,
        )


class Defaults(BaseModel):
    model_config = ConfigDict(extra="forbid")

    years: YearRange


class TrackedSetEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    sport: str = Field(min_length=1)
    brand: str = Field(min_length=1)
    name: str = Field(min_length=1)
    focus: str | None = None
    years: YearOverride | None = None


class TrackedSetsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    defaults: Defaults
    sets: list[TrackedSetEntry] = Field(min_length=1)

    @model_validator(mode="after")
    def _no_duplicates(self) -> TrackedSetsConfig:
        seen: set[tuple[str, str, str]] = set()
        for entry in self.sets:
            # Compare normalized keys so "Upper Deck" and "upper  deck" collide.
            key = (entry.sport.lower(), brand_slug(entry.brand), entry.name.lower())
            if key in seen:
                raise ValueError(
                    f"duplicate tracked set: {entry.sport} / {entry.brand} / {entry.name}"
                )
            seen.add(key)
        return self


@dataclass(frozen=True, slots=True, order=True)
class TrackedSetSpec:
    """One concrete (set, year) to track, with catalog keys resolved."""

    sport_code: str
    brand_slug: str
    set_name: str
    year: int
    focus: str | None = None

    @property
    def natural_key(self) -> tuple[str, str, str, int]:
        return (self.sport_code, self.brand_slug, self.set_name, self.year)


def parse_tracked_sets(raw: str) -> TrackedSetsConfig:
    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise InvalidInputError(f"tracked sets config is not valid YAML: {exc}") from exc
    try:
        return TrackedSetsConfig.model_validate(data)
    except ValidationError as exc:
        raise InvalidInputError(f"tracked sets config is invalid: {exc}") from exc


def load_tracked_sets(path: Path) -> TrackedSetsConfig:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise InvalidInputError(f"cannot read tracked sets config at {path}: {exc}") from exc
    return parse_tracked_sets(raw)


def expand(config: TrackedSetsConfig) -> list[TrackedSetSpec]:
    """Turn config entries into one spec per year, sorted for stable output."""
    specs: list[TrackedSetSpec] = []
    for entry in config.sets:
        years = (entry.years or YearOverride()).resolve(config.defaults.years)
        specs.extend(
            TrackedSetSpec(
                sport_code=entry.sport.lower(),
                brand_slug=brand_slug(entry.brand),
                set_name=entry.name,
                year=year,
                focus=entry.focus,
            )
            for year in years.years()
        )
    return sorted(specs)


@dataclass(frozen=True, slots=True)
class SyncResult:
    created: int = 0
    updated: int = 0
    reactivated: int = 0
    deactivated: int = 0
    unchanged: int = 0


def _require_known(session: Session, specs: Iterable[TrackedSetSpec]) -> None:
    specs = list(specs)
    sports = set(session.scalars(select(Sport.code)))
    brands = set(session.scalars(select(Brand.slug)))
    unknown_sports = sorted({s.sport_code for s in specs} - sports)
    unknown_brands = sorted({s.brand_slug for s in specs} - brands)
    if unknown_sports or unknown_brands:
        raise InvalidInputError(
            "tracked sets reference unknown catalog entries; add them to "
            "config/reference_data.yaml first",
            unknown_sports=unknown_sports,
            unknown_brands=unknown_brands,
        )


def sync_tracked_sets(session: Session, specs: Sequence[TrackedSetSpec]) -> SyncResult:
    """Make the ``tracked_set`` table match ``specs``. Idempotent.

    Entries missing from ``specs`` are deactivated (not deleted). Entries that
    come back are reactivated. The caller owns the transaction.
    """
    _require_known(session, specs)
    wanted = {spec.natural_key: spec for spec in specs}
    existing = {
        (row.sport_code, row.brand_slug, row.set_name, row.year): row
        for row in session.scalars(select(TrackedSet))
    }

    created = updated = reactivated = deactivated = unchanged = 0
    for key, spec in wanted.items():
        row = existing.get(key)
        if row is None:
            session.add(
                TrackedSet(
                    sport_code=spec.sport_code,
                    brand_slug=spec.brand_slug,
                    set_name=spec.set_name,
                    year=spec.year,
                    focus=spec.focus,
                    active=True,
                )
            )
            created += 1
            continue
        changed = False
        if not row.active:
            row.active = True
            reactivated += 1
            changed = True
        if row.focus != spec.focus:
            row.focus = spec.focus
            if not changed:
                updated += 1
            changed = True
        if not changed:
            unchanged += 1

    for key, row in existing.items():
        if key not in wanted and row.active:
            row.active = False
            deactivated += 1

    session.flush()
    return SyncResult(
        created=created,
        updated=updated,
        reactivated=reactivated,
        deactivated=deactivated,
        unchanged=unchanged,
    )
