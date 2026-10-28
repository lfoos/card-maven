"""Market endpoints over a real database: comps, refresh, manual sales, sync jobs."""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from flask import Flask
from flask.testing import FlaskClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from card_maven.market.models import Listing, MarketSyncJob, Sale
from card_maven.shared.db import session_scope
from card_maven.shared.outbox import OutboxMessage

pytestmark = pytest.mark.db

Auth = Callable[..., dict[str, str]]
Factory = sessionmaker[Session]
NOW = datetime.now(UTC)

CARD = {
    "sport": "baseball",
    "brand": "Topps",
    "year": 2024,
    "set_name": "Topps Chrome",
    "card_number": "1",
    "name": "Paul Skenes",
    "players": ["Paul Skenes"],
}


@pytest.fixture
def client(db_app: Flask) -> FlaskClient:
    return db_app.test_client()


def create(client: FlaskClient, auth: Auth, user: str = "alice", **holding: Any) -> dict[str, Any]:
    response = client.post(
        "/api/v1/collection/items", json={"card": CARD, **holding}, headers=auth(user)
    )
    assert response.status_code == 201, response.json
    return response.json  # type: ignore[return-value]


def add_market_row(factory: Factory, variant_id: str, model: type, **fields: Any) -> uuid.UUID:
    base: dict[str, Any] = {
        "source_listing_id": f"t-{uuid.uuid4()}",
        "title": "2024 Topps Chrome Paul Skenes #1",
        "variant_id": uuid.UUID(variant_id),
        "match_confidence": Decimal(1),
        "match_method": "test",
        "price_minor": 1000,
        "currency": "USD",
        "condition": "raw",
    }
    if model is Sale:
        base |= {"source_code": "fixture", "sold_at": NOW - timedelta(days=1)}
    else:
        base |= {"source_code": "ebay_browse", "buying_option": "fixed_price", "observed_at": NOW}
    row = model(**(base | fields))
    with session_scope(factory) as session:
        session.add(row)
        session.flush()
        return row.id  # type: ignore[no-any-return]


def comps(client: FlaskClient, auth: Auth, item_id: str, user: str = "alice") -> Any:
    response = client.get(f"/api/v1/collection/items/{item_id}/comps", headers=auth(user))
    assert response.status_code == 200, response.json
    return response.json


def sale_body(**overrides: Any) -> dict[str, Any]:
    sale = {
        "sold_on": NOW.date().isoformat(),
        "price": {"amount": "20.00", "currency": "USD"},
        "condition": "raw",
    }
    return {"sales": [sale | overrides]}


class TestGetComps:
    def test_empty_market(self, client: FlaskClient, auth: Auth) -> None:
        item = create(client, auth)
        body = comps(client, auth, item["id"])
        assert body == {
            "item_id": item["id"],
            "grade": "Raw",
            "estimate": None,
            "comps": [],
            "asks": [],
            "last_sync": None,
        }
        assert (item["estimated_value"], item["estimate"]) == (None, None)

    def test_comps_estimate_and_asks(
        self, client: FlaskClient, auth: Auth, committing_session_factory: Factory
    ) -> None:
        item = create(client, auth, condition="graded", grader="PSA", grade="10")
        variant = item["card"]["variant_id"]
        f = committing_session_factory
        add_market_row(
            f,
            variant,
            Sale,
            condition="graded",
            grader="PSA",
            grade=Decimal(10),
            price_minor=9500,
            url="https://www.ebay.com/itm/1",
        )
        add_market_row(
            f,
            variant,
            Sale,
            condition="graded",
            grader="PSA",
            grade=Decimal(10),
            price_minor=10250,
            sold_at=NOW - timedelta(days=3),
        )
        add_market_row(
            f,
            variant,
            Sale,
            condition="graded",
            grader="PSA",
            grade=Decimal(9),
            price_minor=4100,
            url="javascript:alert(1)",
        )
        add_market_row(
            f, variant, Listing, price_minor=12000, url="https://ebay.example/itm/9?campid=1"
        )
        add_market_row(f, variant, Listing, price_minor=50, observed_at=NOW - timedelta(hours=7))

        body = comps(client, auth, item["id"])
        assert body["grade"] == "PSA 10"
        assert [(c["price"]["amount"], c["match"]) for c in body["comps"]] == [
            ("95.00", "exact"),
            ("102.50", "exact"),
            ("41.00", "nearest"),
        ]
        assert body["comps"][0]["url"] == "https://www.ebay.com/itm/1"
        assert body["comps"][2]["url"] is None  # never hand a script URL to the browser
        assert body["estimate"]["value"] == {"amount": "98.75", "currency": "USD"}
        assert (body["estimate"]["sample_size"], body["estimate"]["window_days"]) == (2, 180)
        # Fresh ask only; the 7-hour-old one is past eBay's 6-hour limit.
        assert [a["price"]["amount"] for a in body["asks"]] == ["120.00"]

        listed = client.get("/api/v1/collection/items", headers=auth()).json
        assert listed["items"][0]["estimated_value"] == {"amount": "98.75", "currency": "USD"}
        got = client.get(f"/api/v1/collection/items/{item['id']}", headers=auth()).json
        assert got["estimate"]["grade"] == "PSA 10"

    def test_other_collectors_get_404(self, client: FlaskClient, auth: Auth) -> None:
        item = create(client, auth)
        for method, suffix, kwargs in [
            ("get", "/comps", {}),
            ("post", "/comps/refresh", {}),
            ("post", "/comps", {"json": sale_body()}),
        ]:
            response = getattr(client, method)(
                f"/api/v1/collection/items/{item['id']}{suffix}", headers=auth("mallory"), **kwargs
            )
            assert response.status_code == 404, (method, suffix)

    def test_requires_auth(self, client: FlaskClient) -> None:
        url = f"/api/v1/collection/items/{uuid.uuid4()}/comps"
        assert client.get(url).status_code == 401


class TestRefresh:
    def test_queues_once_and_holders_can_poll(
        self, client: FlaskClient, auth: Auth, committing_session_factory: Factory
    ) -> None:
        alice_item = create(client, auth)
        bob_item = create(client, auth, user="bob")
        first = client.post(
            f"/api/v1/collection/items/{alice_item['id']}/comps/refresh", headers=auth()
        )
        assert first.status_code == 202
        assert first.json is not None
        assert first.json["status"] == "queued"
        again = client.post(
            f"/api/v1/collection/items/{bob_item['id']}/comps/refresh", headers=auth("bob")
        )
        assert again.json is not None
        assert again.json["id"] == first.json["id"]  # one job for the same card

        job_url = f"/api/v1/market/sync-jobs/{first.json['id']}"
        assert client.get(job_url, headers=auth("bob")).status_code == 200
        assert client.get(job_url, headers=auth("mallory")).status_code == 404
        assert comps(client, auth, alice_item["id"])["last_sync"]["id"] == first.json["id"]

        with session_scope(committing_session_factory) as session:
            events = session.scalars(select(OutboxMessage.event_type)).all()
            assert events.count("market.sync.requested.v1") == 1
            job = session.get(MarketSyncJob, uuid.UUID(first.json["id"]))
            assert job is not None
            assert job.requested_by is not None

    def test_job_body_hides_requester(self, client: FlaskClient, auth: Auth) -> None:
        item = create(client, auth)
        job = client.post(
            f"/api/v1/collection/items/{item['id']}/comps/refresh", headers=auth()
        ).json
        assert job is not None
        assert set(job) == {"id", "status", "created_at", "started_at", "finished_at", "error"}

    def test_unknown_job_is_404(self, client: FlaskClient, auth: Auth) -> None:
        assert (
            client.get(f"/api/v1/market/sync-jobs/{uuid.uuid4()}", headers=auth()).status_code
            == 404
        )


class TestManualSales:
    def test_add_and_delete(self, client: FlaskClient, auth: Auth) -> None:
        item = create(client, auth)
        response = client.post(
            f"/api/v1/collection/items/{item['id']}/comps",
            json=sale_body(title="Card show", url="https://example.com/s/1"),
            headers=auth(),
        )
        assert response.status_code == 201, response.json
        assert response.json is not None
        assert response.json["added"] == 1
        [comp] = response.json["market"]["comps"]
        assert (comp["mine"], comp["source"], comp["title"]) == (True, "manual", "Card show")
        assert response.json["market"]["estimate"]["value"]["amount"] == "20.00"

        # Private: another holder of the same card doesn't see it.
        bob_item = create(client, auth, user="bob")
        assert comps(client, auth, bob_item["id"], user="bob")["comps"] == []
        assert (
            client.delete(f"/api/v1/market/sales/{comp['id']}", headers=auth("bob")).status_code
            == 404
        )

        assert (
            client.delete(f"/api/v1/market/sales/{comp['id']}", headers=auth()).status_code == 204
        )
        assert comps(client, auth, item["id"])["comps"] == []

    def test_market_sales_cannot_be_deleted(
        self, client: FlaskClient, auth: Auth, committing_session_factory: Factory
    ) -> None:
        item = create(client, auth)
        sale_id = add_market_row(committing_session_factory, item["card"]["variant_id"], Sale)
        assert client.delete(f"/api/v1/market/sales/{sale_id}", headers=auth()).status_code == 404

    @pytest.mark.parametrize(
        ("overrides", "loc"),
        [
            ({"sold_on": (NOW + timedelta(days=2)).date().isoformat()}, "sales.0.sold_on"),
            ({"condition": "graded"}, "sales.0"),
            ({"grader": "PSA", "grade": "10"}, "sales.0"),
            ({"url": "javascript:alert(1)"}, "sales.0.url"),
            ({"price": {"amount": "-1", "currency": "USD"}}, "sales.0.price.amount"),
        ],
    )
    def test_validation(
        self, client: FlaskClient, auth: Auth, overrides: dict[str, Any], loc: str
    ) -> None:
        item = create(client, auth)
        response = client.post(
            f"/api/v1/collection/items/{item['id']}/comps",
            json=sale_body(**overrides),
            headers=auth(),
        )
        assert response.status_code == 422
        assert response.json is not None
        assert any(e["loc"].startswith(loc) for e in response.json["errors"]), response.json

    def test_batch_size_limits(self, client: FlaskClient, auth: Auth) -> None:
        item = create(client, auth)
        url = f"/api/v1/collection/items/{item['id']}/comps"
        assert client.post(url, json={"sales": []}, headers=auth()).status_code == 422
        many = {"sales": sale_body()["sales"] * 201}
        assert client.post(url, json=many, headers=auth()).status_code == 422
