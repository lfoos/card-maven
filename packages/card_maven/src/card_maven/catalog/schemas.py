"""Validated input describing a card's identity, used to find or create catalog rows."""

from __future__ import annotations

from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator

from card_maven.shared.text import clean

Text = Annotated[str, AfterValidator(clean)]


class ParallelSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[Text, Field(min_length=1, max_length=200)]
    print_run: int | None = Field(default=None, ge=1, le=100_000)
    color: Annotated[Text, Field(max_length=64)] | None = None


class CardIdentity(BaseModel):
    """What a card *is*, as a collector would describe it."""

    model_config = ConfigDict(extra="forbid")

    sport: Annotated[Text, Field(min_length=1, max_length=32)]
    brand: Annotated[Text, Field(min_length=1, max_length=128)]
    year: int = Field(ge=1860, le=2100)
    set_name: Annotated[Text, Field(min_length=1, max_length=200)]
    card_number: Annotated[Text, Field(min_length=1, max_length=32)]
    name: Annotated[Text, Field(min_length=1, max_length=200)]
    players: list[Annotated[Text, Field(min_length=1, max_length=200)]] = Field(
        default_factory=list, max_length=6
    )
    team: Annotated[Text, Field(max_length=200)] | None = None
    subset: Annotated[Text, Field(max_length=200)] | None = None
    parallel: ParallelSpec | None = None
    is_rookie: bool = False
    is_autograph: bool = False
    is_memorabilia: bool = False

    @field_validator("sport")
    @classmethod
    def _sport_code(cls, value: str) -> str:
        return value.lower()

    @field_validator("team", "subset")
    @classmethod
    def _blank_is_none(cls, value: str | None) -> str | None:
        return value or None

    @field_validator("players")
    @classmethod
    def _unique_players(cls, value: list[str]) -> list[str]:
        seen: set[str] = set()
        unique: list[str] = []
        for name in value:
            if name.lower() not in seen:
                seen.add(name.lower())
                unique.append(name)
        return unique
