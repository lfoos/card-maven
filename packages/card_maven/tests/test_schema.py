"""Database-level invariants. These are the last line of defense, so they are
tested directly against Postgres rather than through application code."""

from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from card_maven.catalog.models import (
    BASE_PARALLEL_NAME,
    Card,
    CardSet,
    CardVariant,
    Parallel,
    Player,
)
from card_maven.collection.models import CollectionItem, Condition, Grader, Image, ImageKind
from card_maven.identity.models import User
from card_maven.shared.money import Money

pytestmark = pytest.mark.db


def make_user(session: Session, subject: str = "sub-1") -> User:
    user = User(idp_issuer="https://idp.test", idp_subject=subject, email=f"{subject}@test")
    session.add(user)
    session.flush()
    return user


def make_variant(session: Session, *, parallel_name: str = BASE_PARALLEL_NAME) -> CardVariant:
    card_set = CardSet(sport_code="baseball", brand_slug="bowman", year=2025, name="Bowman Chrome")
    player = Player(sport_code="baseball", full_name="JJ Wetherholt")
    card = Card(card_set=card_set, card_number="CPA-JW", name="JJ Wetherholt", is_autograph=True)
    card.players.append(player)
    parallel = Parallel(card_set=card_set, name=parallel_name)
    variant = CardVariant(card=card, parallel=parallel)
    session.add(variant)
    session.flush()
    return variant


def assert_violates(session: Session, constraint: str) -> None:
    with pytest.raises(IntegrityError, match=constraint):
        session.flush()
    session.rollback()


class TestCatalog:
    def test_full_graph_persists_with_defaults(self, seeded_session: Session) -> None:
        variant = make_variant(seeded_session)
        seeded_session.expire_all()
        loaded = seeded_session.get(CardVariant, variant.id)
        assert loaded is not None
        assert loaded.parallel.is_base
        assert loaded.card.players[0].full_name == "JJ Wetherholt"
        assert loaded.card.attributes == {}
        assert loaded.card.catalog_source == "user_confirmed"

    def test_set_requires_known_sport(self, seeded_session: Session) -> None:
        seeded_session.add(CardSet(sport_code="curling", brand_slug="topps", year=2025, name="X"))
        assert_violates(seeded_session, "fk_card_set_sport_code_sport")

    def test_set_year_range(self, seeded_session: Session) -> None:
        seeded_session.add(CardSet(sport_code="baseball", brand_slug="topps", year=1700, name="X"))
        assert_violates(seeded_session, "ck_card_set_year_range")

    def test_duplicate_card_number_in_set(self, seeded_session: Session) -> None:
        variant = make_variant(seeded_session)
        seeded_session.add(Card(set_id=variant.card.set_id, card_number="CPA-JW", name="Dup"))
        assert_violates(seeded_session, "uq_card_set_number")

    def test_duplicate_variant(self, seeded_session: Session) -> None:
        variant = make_variant(seeded_session)
        seeded_session.add(CardVariant(card_id=variant.card_id, parallel_id=variant.parallel_id))
        assert_violates(seeded_session, "uq_card_variant_card_id_parallel_id")

    def test_set_wide_parallel_unique_even_with_null_subset(self, seeded_session: Session) -> None:
        variant = make_variant(seeded_session, parallel_name="Refractor")
        seeded_session.add(Parallel(set_id=variant.card.set_id, name="Refractor"))
        assert_violates(seeded_session, "uq_parallel_natural_key")

    def test_same_parallel_name_allowed_in_different_subsets(self, seeded_session: Session) -> None:
        variant = make_variant(seeded_session, parallel_name="Refractor")
        set_id = variant.card.set_id
        seeded_session.add_all(
            [
                Parallel(set_id=set_id, subset="Prospects", name="Refractor", print_run=499),
                Parallel(set_id=set_id, subset="Chrome Prospect Autographs", name="Refractor"),
            ]
        )
        seeded_session.flush()
        count = len(
            seeded_session.scalars(select(Parallel).where(Parallel.name == "Refractor")).all()
        )
        assert count == 3

    def test_print_run_must_be_positive(self, seeded_session: Session) -> None:
        variant = make_variant(seeded_session)
        seeded_session.add(Parallel(set_id=variant.card.set_id, name="Gold", print_run=0))
        assert_violates(seeded_session, "ck_parallel_print_run_positive")

    def test_parallel_in_use_cannot_be_deleted(self, seeded_session: Session) -> None:
        variant = make_variant(seeded_session, parallel_name="Gold")
        seeded_session.delete(variant.parallel)
        with pytest.raises(IntegrityError):
            seeded_session.flush()
        seeded_session.rollback()


class TestCollection:
    def test_raw_item_with_purchase_price(self, seeded_session: Session) -> None:
        user = make_user(seeded_session)
        item = CollectionItem(owner_id=user.id, variant=make_variant(seeded_session))
        item.purchase_price = Money(4999, "USD")
        seeded_session.add(item)
        seeded_session.flush()
        seeded_session.expire_all()
        loaded = seeded_session.get(CollectionItem, item.id)
        assert loaded is not None
        assert loaded.condition == Condition.RAW
        assert loaded.purchase_price == Money(4999, "USD")

    def test_purchase_price_setter_clears(self) -> None:
        item = CollectionItem()
        item.purchase_price = Money(1, "USD")
        item.purchase_price = None
        assert item.purchase_price_minor is None
        assert item.purchase_currency is None
        assert item.purchase_price is None

    def test_graded_item(self, seeded_session: Session) -> None:
        user = make_user(seeded_session)
        seeded_session.add(
            CollectionItem(
                owner_id=user.id,
                variant=make_variant(seeded_session),
                condition=Condition.GRADED,
                grader=Grader.BGS,
                grade=Decimal("9.5"),
                cert_number="0012345678",
                serial_number=123,
            )
        )
        seeded_session.flush()

    @pytest.mark.parametrize(
        ("fields", "constraint"),
        [
            ({"condition": "graded"}, "grade_matches_condition"),
            ({"condition": "graded", "grader": "PSA"}, "grade_matches_condition"),
            ({"condition": "raw", "grader": "PSA", "grade": Decimal(9)}, "grade_matches_condition"),
            ({"cert_number": "123"}, "grade_matches_condition"),
            ({"condition": "mint"}, "condition_valid"),
            ({"condition": "graded", "grader": "PSA", "grade": Decimal(11)}, "grade_range"),
            ({"condition": "graded", "grader": "PSA", "grade": Decimal("0.5")}, "grade_range"),
            ({"serial_number": 0}, "serial_positive"),
            ({"purchase_price_minor": 100}, "purchase_price_has_currency"),
            ({"purchase_currency": "USD"}, "purchase_price_has_currency"),
            (
                {"purchase_price_minor": -1, "purchase_currency": "USD"},
                "purchase_price_non_negative",
            ),
        ],
    )
    def test_rejects_invalid_items(
        self, seeded_session: Session, fields: dict[str, object], constraint: str
    ) -> None:
        user = make_user(seeded_session)
        seeded_session.add(
            CollectionItem(owner_id=user.id, variant=make_variant(seeded_session), **fields)
        )
        assert_violates(seeded_session, constraint)

    def test_item_requires_owner(self, seeded_session: Session) -> None:
        seeded_session.add(CollectionItem(variant=make_variant(seeded_session)))
        assert_violates(seeded_session, "owner_id")

    def test_images_cascade_with_item_and_user(self, seeded_session: Session) -> None:
        user = make_user(seeded_session)
        item = CollectionItem(owner_id=user.id, variant=make_variant(seeded_session))
        item.images.append(
            Image(
                owner_id=user.id,
                kind=ImageKind.FRONT,
                storage_key=f"users/{user.id}/front.jpg",
                content_type="image/jpeg",
                byte_size=1024,
                sha256="a" * 64,
            )
        )
        seeded_session.add(item)
        seeded_session.flush()
        seeded_session.delete(user)
        seeded_session.flush()
        assert seeded_session.scalars(select(Image)).all() == []
        assert seeded_session.scalars(select(CollectionItem)).all() == []

    def test_image_kind_and_size(self, seeded_session: Session) -> None:
        user = make_user(seeded_session)
        seeded_session.add(
            Image(
                owner_id=user.id,
                kind="thumbnail",
                storage_key="k",
                content_type="image/png",
                byte_size=10,
                sha256="b" * 64,
            )
        )
        assert_violates(seeded_session, "ck_image_kind_valid")
        user = make_user(seeded_session, "sub-2")
        seeded_session.add(
            Image(
                owner_id=user.id,
                kind="front",
                storage_key="k2",
                content_type="image/png",
                byte_size=0,
                sha256="b" * 64,
            )
        )
        assert_violates(seeded_session, "ck_image_byte_size_positive")


class TestIdentity:
    def test_subject_unique_per_issuer(self, db_session: Session) -> None:
        make_user(db_session, "same")
        db_session.add(User(idp_issuer="https://other-idp.test", idp_subject="same"))
        db_session.flush()  # same subject from another issuer is a different person
        db_session.add(User(idp_issuer="https://idp.test", idp_subject="same"))
        assert_violates(db_session, "uq_app_user_idp_issuer_idp_subject")


class TestPhaseOneConstraints:
    def test_set_names_are_unique_case_insensitively(self, seeded_session: Session) -> None:
        seeded_session.add(
            CardSet(sport_code="baseball", brand_slug="topps", year=2025, name="Chrome")
        )
        seeded_session.flush()
        seeded_session.add(
            CardSet(sport_code="baseball", brand_slug="topps", year=2025, name="CHROME")
        )
        assert_violates(seeded_session, "uq_card_set_natural_key")

    def test_card_numbers_are_unique_case_insensitively(self, seeded_session: Session) -> None:
        variant = make_variant(seeded_session)
        seeded_session.add(Card(set_id=variant.card.set_id, card_number="cpa-jw", name="Dup"))
        assert_violates(seeded_session, "uq_card_set_number")

    def test_one_live_front_per_item(self, seeded_session: Session) -> None:
        user = make_user(seeded_session)
        item = CollectionItem(owner_id=user.id, variant=make_variant(seeded_session))
        seeded_session.add(item)
        seeded_session.flush()

        def image(key: str, status: str) -> Image:
            return Image(
                owner_id=user.id,
                collection_item_id=item.id,
                kind="front",
                storage_key=key,
                content_type="image/jpeg",
                byte_size=1,
                sha256="c" * 64,
                status=status,
            )

        # Any number of pending uploads may coexist with one live photo...
        seeded_session.add_all(
            [image("k1", "ready"), image("k2", "pending"), image("k3", "pending")]
        )
        seeded_session.flush()
        # ...but never two live ones.
        seeded_session.add(image("k4", "ready"))
        assert_violates(seeded_session, "uq_image_live_side")

    def test_image_status_defaults_to_pending(self, seeded_session: Session) -> None:
        user = make_user(seeded_session)
        img = Image(
            owner_id=user.id,
            kind="crop",
            storage_key="k",
            content_type="image/png",
            byte_size=1,
            sha256="d" * 64,
        )
        seeded_session.add(img)
        seeded_session.flush()
        seeded_session.refresh(img)
        assert img.status == "pending"
        img.status = "archived"
        assert_violates(seeded_session, "ck_image_status_valid")
