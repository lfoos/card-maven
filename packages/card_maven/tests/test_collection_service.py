import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError
from sqlalchemy.orm import Session

from card_maven.collection.schemas import Holding, ItemChanges, MoneyInput, NewItem
from card_maven.collection.service import CollectionService, ItemFilters, Sort
from card_maven.identity.models import User
from card_maven.shared.clock import utcnow
from card_maven.shared.errors import InvalidInputError, NotFoundError
from card_maven.shared.money import Money

pytestmark = pytest.mark.db


def card(**overrides: object) -> dict[str, object]:
    fields: dict[str, object] = {
        "sport": "baseball",
        "brand": "Bowman",
        "year": 2025,
        "set_name": "Bowman Chrome",
        "card_number": "BCP-50",
        "name": "Roman Anthony",
        "players": ["Roman Anthony"],
        "team": "Red Sox",
        "subset": "Prospects",
    }
    fields.update(overrides)
    return fields


def new_item(**overrides: object) -> NewItem:
    fields: dict[str, object] = {"card": card()}
    fields.update(overrides)
    return NewItem.model_validate(fields)


@pytest.fixture
def owner(seeded_session: Session) -> User:
    user = User(idp_issuer="https://idp.test", idp_subject="owner")
    seeded_session.add(user)
    seeded_session.flush()
    return user


@pytest.fixture
def stranger(seeded_session: Session) -> User:
    user = User(idp_issuer="https://idp.test", idp_subject="stranger")
    seeded_session.add(user)
    seeded_session.flush()
    return user


@pytest.fixture
def service(seeded_session: Session, owner: User) -> CollectionService:
    return CollectionService(seeded_session, owner.id)


class TestHoldingValidation:
    @pytest.mark.parametrize(
        ("fields", "message"),
        [
            ({"condition": "graded"}, "grader and a grade"),
            ({"condition": "graded", "grader": "PSA"}, "grader and a grade"),
            ({"grader": "PSA", "grade": "9"}, "raw cards"),
            ({"cert_number": "1"}, "raw cards"),
            ({"condition": "graded", "grader": "PSA", "grade": "9.3"}, "0.5"),
            ({"condition": "graded", "grader": "PSA", "grade": "11"}, "less than or equal"),
            ({"condition": "graded", "grader": "XYZ", "grade": "9"}, "grader"),
            ({"serial_number": 0}, "greater than or equal"),
            ({"purchase_price": {"amount": 49.99}}, "as a string"),
            ({"purchase_price": {"amount": "-1"}}, "greater than or equal"),
            ({"purchase_price": {"amount": "1.234"}}, "decimal places"),
            ({"purchase_price": {"amount": "5", "currency": "usd"}}, "pattern"),
            ({"acquired_on": (utcnow() + timedelta(days=2)).date().isoformat()}, "future"),
            ({"notes": "x" * 2001}, "at most 2000"),
            ({"surprise": True}, "Extra inputs"),
        ],
    )
    def test_rejects(self, fields: dict[str, object], message: str) -> None:
        with pytest.raises(ValidationError, match=message):
            Holding.model_validate(fields)

    def test_accepts_graded_half_point(self) -> None:
        holding = Holding.model_validate(
            {"condition": "graded", "grader": "BGS", "grade": "9.5", "cert_number": " 0012 "}
        )
        assert holding.grade == Decimal("9.5")
        assert holding.cert_number == "0012"

    def test_blank_notes_become_none(self) -> None:
        assert Holding(notes="   ").notes is None

    def test_money_input(self) -> None:
        assert MoneyInput(amount=Decimal("49.99")).to_money() == Money(4999, "USD")


class TestCreateAndGet:
    def test_create_resolves_catalog_and_stores_holding(
        self, service: CollectionService, owner: User
    ) -> None:
        item = service.create(
            new_item(
                purchase_price={"amount": "125.00"},
                serial_number=12,
                card=card(parallel={"name": "Gold Refractor", "print_run": 50}),
            )
        )
        assert item.owner_id == owner.id
        assert item.variant.card.name == "Roman Anthony"
        assert item.variant.parallel.name == "Gold Refractor"
        assert item.purchase_price == Money(12500, "USD")
        assert service.get(item.id).id == item.id

    def test_serial_cannot_exceed_print_run(self, service: CollectionService) -> None:
        with pytest.raises(InvalidInputError, match="exceeds the print run of /50"):
            service.create(
                new_item(serial_number=51, card=card(parallel={"name": "Gold", "print_run": 50}))
            )

    def test_serial_allowed_when_print_run_unknown(self, service: CollectionService) -> None:
        assert service.create(new_item(serial_number=999)).serial_number == 999

    def test_other_owners_items_are_invisible(
        self, seeded_session: Session, service: CollectionService, stranger: User
    ) -> None:
        item = service.create(new_item())
        theirs = CollectionService(seeded_session, stranger.id)
        with pytest.raises(NotFoundError):
            theirs.get(item.id)
        with pytest.raises(NotFoundError):
            theirs.update(item.id, ItemChanges(notes="mine now"))
        with pytest.raises(NotFoundError):
            theirs.delete(item.id)
        assert theirs.page().items == []

    def test_unknown_id(self, service: CollectionService) -> None:
        with pytest.raises(NotFoundError, match="collection item not found"):
            service.get(uuid.uuid4())


class TestUpdate:
    def test_partial_update_keeps_other_fields(self, service: CollectionService) -> None:
        item = service.create(
            new_item(notes="pulled from a hobby box", purchase_price={"amount": "20"})
        )
        updated = service.update(item.id, ItemChanges.model_validate({"serial_number": 7}))
        assert (updated.serial_number, updated.notes, updated.purchase_price) == (
            7,
            "pulled from a hobby box",
            Money(2000, "USD"),
        )

    def test_explicit_null_clears(self, service: CollectionService) -> None:
        item = service.create(new_item(notes="x", purchase_price={"amount": "20"}))
        updated = service.update(
            item.id, ItemChanges.model_validate({"notes": None, "purchase_price": None})
        )
        assert (updated.notes, updated.purchase_price) == (None, None)

    def test_grading_a_raw_card(self, service: CollectionService) -> None:
        item = service.create(new_item())
        updated = service.update(
            item.id,
            ItemChanges.model_validate({"condition": "graded", "grader": "PSA", "grade": "10"}),
        )
        assert (updated.condition, updated.grader, updated.grade) == (
            "graded",
            "PSA",
            Decimal("10.0"),
        )

    def test_merged_result_is_revalidated(self, service: CollectionService) -> None:
        item = service.create(new_item(condition="graded", grader="PSA", grade="9"))
        with pytest.raises(ValidationError, match="raw cards"):
            service.update(item.id, ItemChanges.model_validate({"condition": "raw"}))

    def test_changing_card_identity(self, service: CollectionService) -> None:
        item = service.create(new_item())
        updated = service.update(
            item.id,
            ItemChanges.model_validate(
                {"card": card(parallel={"name": "Refractor", "print_run": 499})}
            ),
        )
        assert updated.variant.parallel.name == "Refractor"
        assert updated.variant.card.id == item.variant.card.id

    def test_serial_checked_against_new_parallel(self, service: CollectionService) -> None:
        item = service.create(new_item(serial_number=100))
        with pytest.raises(InvalidInputError, match="print run"):
            service.update(
                item.id,
                ItemChanges.model_validate(
                    {"card": card(parallel={"name": "Gold", "print_run": 50})}
                ),
            )


class TestDelete:
    def test_returns_storage_keys(
        self, seeded_session: Session, service: CollectionService, owner: User
    ) -> None:
        from card_maven.collection.models import Image

        item = service.create(new_item())
        seeded_session.add(
            Image(
                owner_id=owner.id,
                collection_item_id=item.id,
                kind="front",
                storage_key="k-front",
                content_type="image/jpeg",
                byte_size=1,
                sha256="a" * 64,
            )
        )
        seeded_session.flush()
        seeded_session.expire(item)
        assert service.delete(item.id) == ["k-front"]
        with pytest.raises(NotFoundError):
            service.get(item.id)


class TestListing:
    @pytest.fixture
    def items(self, service: CollectionService) -> list[uuid.UUID]:
        made = [
            service.create(new_item(card=card(card_number="BCP-1", name="Roman Anthony"))),
            service.create(
                new_item(
                    card=card(
                        year=2024,
                        card_number="BCP-2",
                        name="Jackson Holliday",
                        players=["Jackson Holliday"],
                    )
                )
            ),
            service.create(
                new_item(
                    condition="graded",
                    grader="PSA",
                    grade="10",
                    card=card(
                        sport="basketball",
                        brand="Panini",
                        set_name="Prizm",
                        card_number="1",
                        name="Victor Wembanyama",
                        players=["Victor Wembanyama"],
                        subset=None,
                        team="Spurs",
                    ),
                )
            ),
            service.create(
                new_item(
                    card=card(
                        card_number="BCP-3",
                        name="Ethan Salas",
                        players=["Ethan Salas"],
                        parallel={"name": "Gold Refractor", "print_run": 50},
                    )
                )
            ),
        ]
        return [i.id for i in made]

    def all_pages(
        self, service: CollectionService, sort: Sort, limit: int, filters: ItemFilters | None = None
    ) -> list[str]:
        names: list[str] = []
        cursor = None
        while True:
            page = service.page(filters, sort=sort, cursor=cursor, limit=limit)
            names += [i.variant.card.name for i in page.items]
            if page.next_cursor is None:
                return names
            cursor = page.next_cursor

    @pytest.mark.parametrize(
        ("sort", "expected"),
        [
            (
                Sort.NEWEST,
                ["Ethan Salas", "Victor Wembanyama", "Jackson Holliday", "Roman Anthony"],
            ),
            (
                Sort.OLDEST,
                ["Roman Anthony", "Jackson Holliday", "Victor Wembanyama", "Ethan Salas"],
            ),
            (
                Sort.YEAR_DESC,
                ["Ethan Salas", "Victor Wembanyama", "Roman Anthony", "Jackson Holliday"],
            ),
            (
                Sort.YEAR_ASC,
                ["Jackson Holliday", "Roman Anthony", "Victor Wembanyama", "Ethan Salas"],
            ),
            (Sort.NAME, ["Ethan Salas", "Jackson Holliday", "Roman Anthony", "Victor Wembanyama"]),
        ],
    )
    @pytest.mark.parametrize("limit", [1, 3, 100])
    def test_every_sort_pages_without_gaps(
        self,
        service: CollectionService,
        items: list[uuid.UUID],
        sort: Sort,
        expected: list[str],
        limit: int,
    ) -> None:
        assert self.all_pages(service, sort, limit) == expected

    def test_insertions_between_pages_do_not_shift_results(
        self, service: CollectionService, items: list[uuid.UUID]
    ) -> None:
        first = service.page(sort=Sort.OLDEST, limit=2)
        service.create(new_item(card=card(card_number="BCP-9", name="Aaron Newcomer", players=[])))
        second = service.page(sort=Sort.OLDEST, cursor=first.next_cursor, limit=2)
        assert [i.variant.card.name for i in first.items + second.items] == [
            "Roman Anthony",
            "Jackson Holliday",
            "Victor Wembanyama",
            "Ethan Salas",
        ]

    @pytest.mark.parametrize(
        ("filters", "expected"),
        [
            (ItemFilters(sport="Basketball"), {"Victor Wembanyama"}),
            (ItemFilters(year=2024), {"Jackson Holliday"}),
            (ItemFilters(brand="panini"), {"Victor Wembanyama"}),
            (ItemFilters(condition="graded"), {"Victor Wembanyama"}),
            (ItemFilters(query="holli"), {"Jackson Holliday"}),
            (ItemFilters(query="spurs"), {"Victor Wembanyama"}),
            (ItemFilters(query="gold"), {"Ethan Salas"}),
            (ItemFilters(query="bcp-2"), {"Jackson Holliday"}),
            (ItemFilters(query="prizm"), {"Victor Wembanyama"}),
            (
                ItemFilters(query="   "),
                {"Roman Anthony", "Jackson Holliday", "Victor Wembanyama", "Ethan Salas"},
            ),
            (ItemFilters(query="%"), set()),
            (ItemFilters(sport="baseball", year=2025, query="salas"), {"Ethan Salas"}),
        ],
    )
    def test_filters(
        self,
        service: CollectionService,
        items: list[uuid.UUID],
        filters: ItemFilters,
        expected: set[str],
    ) -> None:
        assert set(self.all_pages(service, Sort.NEWEST, 100, filters)) == expected

    def test_player_search_matches_players_not_just_card_name(
        self, service: CollectionService
    ) -> None:
        service.create(
            new_item(
                card=card(
                    card_number="DUAL-1",
                    name="Future Stars",
                    players=["Kevin McGonigle", "Max Clark"],
                )
            )
        )
        assert self.all_pages(service, Sort.NEWEST, 10, ItemFilters(query="mcgonigle")) == [
            "Future Stars"
        ]

    def test_limits_and_cursor_validation(
        self, service: CollectionService, items: list[uuid.UUID]
    ) -> None:
        for bad in (0, 101):
            with pytest.raises(InvalidInputError, match="limit"):
                service.page(limit=bad)
        page = service.page(sort=Sort.NEWEST, limit=1)
        with pytest.raises(InvalidInputError, match="does not match"):
            service.page(sort=Sort.NAME, cursor=page.next_cursor, limit=1)
        with pytest.raises(InvalidInputError, match="invalid cursor"):
            service.page(cursor="garbage!", limit=1)
