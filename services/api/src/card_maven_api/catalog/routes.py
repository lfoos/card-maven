from __future__ import annotations

import uuid

from flask_openapi3.blueprint import APIBlueprint
from flask_openapi3.models.tag import Tag
from pydantic import BaseModel, Field

from card_maven.catalog.service import CatalogService
from card_maven_api.auth.decorators import require_user
from card_maven_api.db import transaction
from card_maven_api.openapi import BEARER, PROTECTED_RESPONSES
from card_maven_api.presenters import parallel_out
from card_maven_api.schemas import ParallelOut, PlayerSuggestionOut, SetSuggestionOut

TAG = Tag(name="catalog", description="Autocomplete over known sets, players, and parallels")
bp = APIBlueprint(
    "catalog",
    __name__,
    url_prefix="/api/v1/catalog",
    abp_tags=[TAG],
    abp_security=BEARER,
    abp_responses=PROTECTED_RESPONSES,
)


class SetQuery(BaseModel):
    q: str = Field(min_length=1, max_length=100)
    sport: str | None = Field(default=None, max_length=32)
    year: int | None = Field(default=None, ge=1860, le=2100)
    limit: int = Field(default=10, ge=1, le=20)


class PlayerQuery(BaseModel):
    q: str = Field(min_length=1, max_length=100)
    sport: str | None = Field(default=None, max_length=32)
    limit: int = Field(default=10, ge=1, le=20)


class ParallelQuery(BaseModel):
    set_id: uuid.UUID


class SetList(BaseModel):
    items: list[SetSuggestionOut]


class PlayerList(BaseModel):
    items: list[PlayerSuggestionOut]


class ParallelList(BaseModel):
    items: list[ParallelOut]


@bp.get("/sets", summary="Suggest sets", responses={200: SetList})
@require_user
def search_sets(query: SetQuery) -> dict[str, object]:
    with transaction() as session:
        sets = CatalogService(session).search_sets(
            query.q, sport=query.sport, year=query.year, limit=query.limit
        )
        items = [
            SetSuggestionOut(
                id=s.id, sport=s.sport_code, brand=s.brand_slug, year=s.year, name=s.name
            )
            for s in sets
        ]
    return SetList(items=items).model_dump(mode="json")


@bp.get("/players", summary="Suggest players", responses={200: PlayerList})
@require_user
def search_players(query: PlayerQuery) -> dict[str, object]:
    with transaction() as session:
        players = CatalogService(session).search_players(
            query.q, sport=query.sport, limit=query.limit
        )
        items = [
            PlayerSuggestionOut(id=p.id, sport=p.sport_code, full_name=p.full_name) for p in players
        ]
    return PlayerList(items=items).model_dump(mode="json")


@bp.get("/parallels", summary="Parallels known for a set", responses={200: ParallelList})
@require_user
def list_parallels(query: ParallelQuery) -> dict[str, object]:
    with transaction() as session:
        items = [parallel_out(p) for p in CatalogService(session).list_parallels(query.set_id)]
    return ParallelList(items=items).model_dump(mode="json")
