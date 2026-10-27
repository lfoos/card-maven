"""End-to-end API tests over a real database. Each user is a different token."""

import hashlib
import uuid
from collections.abc import Callable
from typing import Any

import pytest
from flask import Flask
from flask.testing import FlaskClient

from card_maven.shared.storage.memory import InMemoryObjectStore

pytestmark = pytest.mark.db

Auth = Callable[..., dict[str, str]]
JPEG = b"\xff\xd8\xff\xe0" + b"card photo" * 100

CARD = {
    "sport": "baseball",
    "brand": "Bowman",
    "year": 2025,
    "set_name": "Bowman Chrome",
    "card_number": "CPA-JW",
    "name": "JJ Wetherholt",
    "players": ["JJ Wetherholt"],
    "team": "Cardinals",
    "subset": "Chrome Prospect Autographs",
    "is_autograph": True,
    "parallel": {"name": "Gold Refractor", "print_run": 50},
}


@pytest.fixture
def client(db_app: Flask) -> FlaskClient:
    return db_app.test_client()


def create(
    client: FlaskClient, auth: Auth, user: str = "alice", **overrides: Any
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "card": CARD,
        "serial_number": 12,
        "purchase_price": {"amount": "250.00"},
    }
    body.update(overrides)
    response = client.post("/api/v1/collection/items", json=body, headers=auth(user))
    assert response.status_code == 201, response.json
    return response.json  # type: ignore[return-value]


class TestMe:
    def test_provisions_and_returns_the_user(self, client: FlaskClient, auth: Auth) -> None:
        first = client.get(
            "/api/v1/me", headers=auth("alice", realm_access={"roles": ["collector"]})
        )
        assert first.status_code == 200
        assert first.json["email"] == "alice@example.com"
        assert first.json["roles"] == ["collector"]
        again = client.get("/api/v1/me", headers=auth("alice"))
        assert again.json["id"] == first.json["id"]

    @pytest.mark.parametrize(
        "headers", [{}, {"Authorization": "Bearer junk"}, {"Authorization": "Basic x"}]
    )
    def test_requires_valid_token(self, client: FlaskClient, headers: dict[str, str]) -> None:
        response = client.get("/api/v1/me", headers=headers)
        assert response.status_code == 401
        assert response.content_type == "application/problem+json"


class TestCreate:
    def test_creates_item_with_full_representation(self, client: FlaskClient, auth: Auth) -> None:
        item = create(client, auth)
        card = item["card"]
        assert (card["set_name"], card["year"], card["brand"], card["card_number"]) == (
            "Bowman Chrome",
            2025,
            "bowman",
            "CPA-JW",
        )
        assert card["parallel"]["name"] == "Gold Refractor"
        assert card["parallel"]["print_run"] == 50
        assert card["players"] == ["JJ Wetherholt"]
        assert item["purchase_price"] == {"amount": "250.00", "currency": "USD"}
        assert item["condition"] == "raw"
        assert item["estimated_value"] is None
        assert item["images"] == {"front": None, "back": None}

    def test_graded_item(self, client: FlaskClient, auth: Auth) -> None:
        item = create(
            client, auth, condition="graded", grader="PSA", grade="10", cert_number="12345678"
        )
        assert (item["grader"], item["grade"], item["cert_number"]) == ("PSA", "10.0", "12345678")

    @pytest.mark.parametrize(
        ("body", "loc"),
        [
            ({"card": {**CARD, "year": 1700}}, "card.year"),
            ({"card": {k: v for k, v in CARD.items() if k != "name"}}, "card.name"),
            ({"card": CARD, "condition": "graded"}, "body"),
            ({"card": CARD, "purchase_price": {"amount": 9.99}}, "purchase_price.amount"),
            ({"card": CARD, "serial_number": 51}, "serial_number"),
            ({"card": {**CARD, "sport": "curling"}}, "card.sport"),
            ({"card": CARD, "unexpected": True}, "unexpected"),
        ],
    )
    def test_validation_problems_point_at_the_field(
        self, client: FlaskClient, auth: Auth, body: dict[str, Any], loc: str
    ) -> None:
        response = client.post("/api/v1/collection/items", json=body, headers=auth())
        assert response.status_code == 422
        assert response.content_type == "application/problem+json"
        problem = response.json
        assert problem["code"] == "invalid_input"
        assert any(e["loc"] == loc or e["loc"].startswith(loc) for e in problem["errors"]), problem

    def test_malformed_json(self, client: FlaskClient, auth: Auth) -> None:
        response = client.post(
            "/api/v1/collection/items",
            data="{not json",
            headers={**auth(), "Content-Type": "application/json"},
        )
        assert response.status_code in (400, 422)
        assert response.content_type == "application/problem+json"


class TestReadUpdateDelete:
    def test_get_patch_delete(self, client: FlaskClient, auth: Auth) -> None:
        item = create(client, auth)
        url = f"/api/v1/collection/items/{item['id']}"
        assert client.get(url, headers=auth()).json["id"] == item["id"]

        patched = client.patch(
            url, json={"notes": "  case hit  ", "purchase_price": None}, headers=auth()
        )
        assert patched.status_code == 200
        assert (
            patched.json["notes"],
            patched.json["purchase_price"],
            patched.json["serial_number"],
        ) == ("case hit", None, 12)

        assert client.delete(url, headers=auth()).status_code == 204
        assert client.get(url, headers=auth()).status_code == 404

    def test_patch_revalidates_merged_state(self, client: FlaskClient, auth: Auth) -> None:
        item = create(client, auth, condition="graded", grader="PSA", grade="9")
        response = client.patch(
            f"/api/v1/collection/items/{item['id']}", json={"condition": "raw"}, headers=auth()
        )
        assert response.status_code == 422
        assert "raw cards" in response.json["detail"]

    def test_bad_ids(self, client: FlaskClient, auth: Auth) -> None:
        assert (
            client.get(f"/api/v1/collection/items/{uuid.uuid4()}", headers=auth()).status_code
            == 404
        )
        assert client.get("/api/v1/collection/items/not-a-uuid", headers=auth()).status_code == 404


class TestIsolation:
    """Security: one collector can never see, change, or detect another's cards."""

    def test_every_endpoint_hides_other_users_items(
        self, client: FlaskClient, auth: Auth, store: InMemoryObjectStore
    ) -> None:
        item = create(client, auth, "alice")
        base = f"/api/v1/collection/items/{item['id']}"
        bob = auth("bob")
        assert client.get(base, headers=bob).status_code == 404
        assert client.patch(base, json={"notes": "mine"}, headers=bob).status_code == 404
        assert client.delete(base, headers=bob).status_code == 404
        start = {"kind": "front", "content_type": "image/jpeg", "byte_size": 10, "sha256": "a" * 64}
        assert client.post(f"{base}/images", json=start, headers=bob).status_code == 404
        assert client.get("/api/v1/collection/items", headers=bob).json == {
            "items": [],
            "next_cursor": None,
        }
        # Alice's item is untouched.
        assert client.get(base, headers=auth("alice")).json["notes"] is None

    def test_other_users_image_ids_are_unknown(
        self, client: FlaskClient, auth: Auth, store: InMemoryObjectStore
    ) -> None:
        alice_item = create(client, auth, "alice")
        started = client.post(
            f"/api/v1/collection/items/{alice_item['id']}/images",
            json={
                "kind": "front",
                "content_type": "image/jpeg",
                "byte_size": len(JPEG),
                "sha256": hashlib.sha256(JPEG).hexdigest(),
            },
            headers=auth("alice"),
        ).json
        bob_item = create(client, auth, "bob")
        url = f"/api/v1/collection/items/{bob_item['id']}/images/{started['image_id']}"
        assert client.post(f"{url}/complete", headers=auth("bob")).status_code == 404
        assert client.delete(url, headers=auth("bob")).status_code == 404


class TestListing:
    def test_filters_sort_and_pagination(self, client: FlaskClient, auth: Auth) -> None:
        for number, name, year in [
            ("1", "Roman Anthony", 2024),
            ("2", "Ethan Salas", 2025),
            ("3", "Max Clark", 2025),
        ]:
            create(
                client,
                auth,
                card={
                    **CARD,
                    "card_number": number,
                    "name": name,
                    "players": [name],
                    "year": year,
                    "parallel": None,
                },
                serial_number=None,
            )
        names: list[str] = []
        cursor = None
        while True:
            params = {"sort": "name", "limit": 2, **({"cursor": cursor} if cursor else {})}
            page = client.get("/api/v1/collection/items", query_string=params, headers=auth()).json
            names += [i["card"]["name"] for i in page["items"]]
            cursor = page["next_cursor"]
            if cursor is None:
                break
        assert names == ["Ethan Salas", "Max Clark", "Roman Anthony"]
        filtered = client.get(
            "/api/v1/collection/items", query_string={"year": 2024}, headers=auth()
        ).json
        assert [i["card"]["name"] for i in filtered["items"]] == ["Roman Anthony"]
        searched = client.get(
            "/api/v1/collection/items", query_string={"q": "sal"}, headers=auth()
        ).json
        assert [i["card"]["name"] for i in searched["items"]] == ["Ethan Salas"]

    @pytest.mark.parametrize(
        "params",
        [
            {"limit": 0},
            {"limit": 101},
            {"sort": "random"},
            {"cursor": "garbage!"},
            {"condition": "mint"},
        ],
    )
    def test_invalid_query(self, client: FlaskClient, auth: Auth, params: dict[str, Any]) -> None:
        response = client.get("/api/v1/collection/items", query_string=params, headers=auth())
        assert response.status_code == 422
        assert response.json["code"] == "invalid_input"


class TestCatalogAutocomplete:
    def test_suggestions(self, client: FlaskClient, auth: Auth) -> None:
        item = create(client, auth)
        sets = client.get(
            "/api/v1/catalog/sets", query_string={"q": "chrome"}, headers=auth()
        ).json["items"]
        assert [(s["name"], s["year"], s["brand"]) for s in sets] == [
            ("Bowman Chrome", 2025, "bowman")
        ]
        players = client.get(
            "/api/v1/catalog/players", query_string={"q": "wether"}, headers=auth()
        ).json["items"]
        assert [p["full_name"] for p in players] == ["JJ Wetherholt"]
        parallels = client.get(
            "/api/v1/catalog/parallels",
            query_string={"set_id": item["card"]["set_id"]},
            headers=auth(),
        ).json["items"]
        assert [p["name"] for p in parallels] == ["Gold Refractor"]

    def test_query_required(self, client: FlaskClient, auth: Auth) -> None:
        assert client.get("/api/v1/catalog/sets", headers=auth()).status_code == 422
        assert client.get("/api/v1/catalog/sets", query_string={"q": "x"}).status_code == 401


class TestPhotos:
    def upload(
        self,
        client: FlaskClient,
        auth: Auth,
        store: InMemoryObjectStore,
        item_id: str,
        kind: str = "front",
        data: bytes = JPEG,
    ) -> dict[str, Any]:
        started = client.post(
            f"/api/v1/collection/items/{item_id}/images",
            json={
                "kind": kind,
                "content_type": "image/jpeg",
                "byte_size": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            },
            headers=auth(),
        )
        assert started.status_code == 201, started.json
        body = started.json
        assert body["expires_in"] == 900
        key = body["upload"]["fields"]["key"]
        assert key.endswith(body["image_id"])
        assert f"/items/{item_id}/" in key
        store.put(key, data, "image/jpeg")  # the browser's direct upload
        return body

    def test_upload_complete_replace_delete(
        self, client: FlaskClient, auth: Auth, store: InMemoryObjectStore
    ) -> None:
        item = create(client, auth)
        url = f"/api/v1/collection/items/{item['id']}"
        first = self.upload(client, auth, store, item["id"])
        done = client.post(f"{url}/images/{first['image_id']}/complete", headers=auth())
        assert done.status_code == 200
        assert done.json["kind"] == "front"
        assert "expires=600" in done.json["url"]
        assert client.get(url, headers=auth()).json["images"]["front"]["id"] == first["image_id"]

        second = self.upload(client, auth, store, item["id"])
        client.post(f"{url}/images/{second['image_id']}/complete", headers=auth())
        first_key = first["upload"]["fields"]["key"]
        assert first_key in store.deleted  # replaced photo removed after commit

        assert (
            client.delete(f"{url}/images/{second['image_id']}", headers=auth()).status_code == 204
        )
        assert client.get(url, headers=auth()).json["images"]["front"] is None

    def test_complete_before_upload_is_conflict(self, client: FlaskClient, auth: Auth) -> None:
        item = create(client, auth)
        started = client.post(
            f"/api/v1/collection/items/{item['id']}/images",
            json={"kind": "back", "content_type": "image/png", "byte_size": 10, "sha256": "b" * 64},
            headers=auth(),
        ).json
        response = client.post(
            f"/api/v1/collection/items/{item['id']}/images/{started['image_id']}/complete",
            headers=auth(),
        )
        assert response.status_code == 409
        assert response.json["code"] == "conflict"

    @pytest.mark.parametrize(
        "body",
        [
            {"kind": "crop", "content_type": "image/jpeg", "byte_size": 10, "sha256": "a" * 64},
            {"kind": "front", "content_type": "image/gif", "byte_size": 10, "sha256": "a" * 64},
            {
                "kind": "front",
                "content_type": "image/jpeg",
                "byte_size": 16 * 1024 * 1024,
                "sha256": "a" * 64,
            },
            {"kind": "front", "content_type": "image/jpeg", "byte_size": 10, "sha256": "not-hex"},
        ],
    )
    def test_rejects_bad_upload_requests(
        self, client: FlaskClient, auth: Auth, body: dict[str, Any]
    ) -> None:
        item = create(client, auth)
        response = client.post(
            f"/api/v1/collection/items/{item['id']}/images", json=body, headers=auth()
        )
        assert response.status_code == 422

    def test_deleting_item_removes_its_photos(
        self, client: FlaskClient, auth: Auth, store: InMemoryObjectStore
    ) -> None:
        item = create(client, auth)
        started = self.upload(client, auth, store, item["id"])
        client.post(
            f"/api/v1/collection/items/{item['id']}/images/{started['image_id']}/complete",
            headers=auth(),
        )
        client.delete(f"/api/v1/collection/items/{item['id']}", headers=auth())
        assert started["upload"]["fields"]["key"] in store.deleted

    def test_storage_outage_during_cleanup_does_not_fail_the_request(
        self,
        client: FlaskClient,
        auth: Auth,
        store: InMemoryObjectStore,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from card_maven.shared.errors import DependencyUnavailableError

        item = create(client, auth)

        def down(key: str) -> None:
            raise DependencyUnavailableError("storage down")

        monkeypatch.setattr(store, "delete", down)
        started = self.upload(client, auth, store, item["id"])
        client.post(
            f"/api/v1/collection/items/{item['id']}/images/{started['image_id']}/complete",
            headers=auth(),
        )
        assert (
            client.delete(f"/api/v1/collection/items/{item['id']}", headers=auth()).status_code
            == 204
        )
