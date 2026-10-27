from __future__ import annotations

from flask_openapi3.blueprint import APIBlueprint
from flask_openapi3.models.tag import Tag

from card_maven_api.auth.decorators import current_principal, current_user, require_user
from card_maven_api.openapi import BEARER, PROTECTED_RESPONSES
from card_maven_api.schemas import MeOut

TAG = Tag(name="identity", description="The signed-in collector")
bp = APIBlueprint(
    "identity",
    __name__,
    url_prefix="/api/v1",
    abp_tags=[TAG],
    abp_security=BEARER,
    abp_responses=PROTECTED_RESPONSES,
)


@bp.get("/me", summary="The signed-in user", responses={200: MeOut})
@require_user
def me() -> dict[str, object]:
    user = current_user()
    return MeOut(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        roles=sorted(current_principal().roles),
    ).model_dump(mode="json")
