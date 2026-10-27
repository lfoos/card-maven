"""Reference data (sports, brands) from ``config/reference_data.yaml``. Idempotent."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from sqlalchemy.orm import Session

from card_maven.catalog.models import Brand, Sport
from card_maven.shared.errors import InvalidInputError


class SportEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(pattern=r"^[a-z][a-z0-9_]*$", max_length=32)
    name: str = Field(min_length=1, max_length=64)


class BrandEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    slug: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=64)
    name: str = Field(min_length=1, max_length=128)


class ReferenceData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sports: list[SportEntry]
    brands: list[BrandEntry]

    @field_validator("sports", "brands")
    @classmethod
    def _unique(
        cls, entries: list[SportEntry] | list[BrandEntry]
    ) -> list[SportEntry] | list[BrandEntry]:
        keys = [e.code if isinstance(e, SportEntry) else e.slug for e in entries]
        duplicates = sorted({k for k in keys if keys.count(k) > 1})
        if duplicates:
            raise ValueError(f"duplicate keys: {duplicates}")
        return entries


def load_reference_data(path: Path) -> ReferenceData:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return ReferenceData.model_validate(data)
    except OSError as exc:
        raise InvalidInputError(f"cannot read reference data at {path}: {exc}") from exc
    except (yaml.YAMLError, ValidationError) as exc:
        raise InvalidInputError(f"reference data is invalid: {exc}") from exc


@dataclass(frozen=True, slots=True)
class SeedResult:
    sports: int
    brands: int


def seed_reference_data(session: Session, data: ReferenceData) -> SeedResult:
    """Upsert sports and brands. Never deletes: rows may already be referenced."""
    for sport in data.sports:
        session.merge(Sport(code=sport.code, name=sport.name))
    for brand in data.brands:
        session.merge(Brand(slug=brand.slug, name=brand.name))
    session.flush()
    return SeedResult(sports=len(data.sports), brands=len(data.brands))
