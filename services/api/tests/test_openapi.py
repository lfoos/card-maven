"""The checked-in OpenAPI contract must match the code. Regenerate with `make openapi`."""

import json
from pathlib import Path

from flask import Flask

from card_maven_api.openapi import spec_json

CONTRACT = Path(__file__).resolve().parents[3] / "contracts" / "openapi.json"


def test_contract_is_up_to_date() -> None:
    assert CONTRACT.read_text() == spec_json(), (
        "contracts/openapi.json is stale; run `make openapi`"
    )


def test_every_api_route_is_documented_and_protected() -> None:
    spec = json.loads(spec_json())
    paths = spec["paths"]
    assert {
        "/api/v1/me",
        "/api/v1/collection/items",
        "/api/v1/collection/items/{item_id}",
        "/api/v1/collection/items/{item_id}/images",
        "/api/v1/collection/items/{item_id}/images/{image_id}/complete",
        "/api/v1/catalog/sets",
        "/api/v1/catalog/players",
        "/api/v1/catalog/parallels",
    } <= set(paths)
    for path, operations in paths.items():
        for method, operation in operations.items():
            assert operation.get("security") == [{"bearer": []}], (
                f"{method.upper()} {path} is unauthenticated"
            )
            assert "401" in operation["responses"], f"{method.upper()} {path} lacks a 401"


def test_spec_served(app: Flask) -> None:
    response = app.test_client().get("/api/v1/openapi.json")
    assert response.status_code == 200
    assert response.json["info"]["title"] == "Card Maven API"
