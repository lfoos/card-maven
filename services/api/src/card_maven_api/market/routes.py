from __future__ import annotations

import uuid

from flask_openapi3.blueprint import APIBlueprint
from flask_openapi3.models.tag import Tag
from pydantic import BaseModel

from card_maven.market.collector import CollectorMarket
from card_maven_api.auth.decorators import current_user, require_user
from card_maven_api.db import transaction
from card_maven_api.openapi import BEARER, NOT_FOUND, PROTECTED_RESPONSES
from card_maven_api.presenters import sync_job_out
from card_maven_api.rate_limits import WRITE_LIMIT, rate_limited
from card_maven_api.schemas import SyncJobOut

TAG = Tag(name="market", description="Sales you entered, and market sync jobs")
bp = APIBlueprint(
    "market",
    __name__,
    url_prefix="/api/v1/market",
    abp_tags=[TAG],
    abp_security=BEARER,
    abp_responses=PROTECTED_RESPONSES,
)


class SalePath(BaseModel):
    sale_id: uuid.UUID


class JobPath(BaseModel):
    job_id: uuid.UUID


@bp.delete(
    "/sales/<uuid:sale_id>",
    summary="Delete a sale you entered",
    responses={204: None, **NOT_FOUND},
)
@rate_limited(WRITE_LIMIT)
@require_user
def delete_sale(path: SalePath) -> tuple[str, int]:
    with transaction() as session:
        CollectorMarket(session, current_user().id).delete_sale(path.sale_id)
    return "", 204


@bp.get(
    "/sync-jobs/<uuid:job_id>",
    summary="Check a market sync",
    description="Visible to collectors who hold the card being synced.",
    responses={200: SyncJobOut, **NOT_FOUND},
)
@require_user
def get_sync_job(path: JobPath) -> dict[str, object]:
    with transaction() as session:
        out = sync_job_out(CollectorMarket(session, current_user().id).job(path.job_id))
    return out.model_dump(mode="json")
