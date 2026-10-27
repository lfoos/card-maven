import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from card_maven.identity.models import User
from card_maven.identity.service import VerifiedIdentity, provision_user

pytestmark = pytest.mark.db

LOGAN = VerifiedIdentity("https://idp.test", "sub-1", "logan@example.com", "Logan")


def test_first_login_creates_user(db_session: Session) -> None:
    user = provision_user(db_session, LOGAN)
    assert (user.idp_subject, user.email, user.display_name) == (
        "sub-1",
        "logan@example.com",
        "Logan",
    )


def test_repeat_login_reuses_and_refreshes_profile(db_session: Session) -> None:
    first = provision_user(db_session, LOGAN)
    again = provision_user(
        db_session, VerifiedIdentity("https://idp.test", "sub-1", "new@example.com", "L. Foos")
    )
    assert again.id == first.id
    assert (again.email, again.display_name) == ("new@example.com", "L. Foos")
    assert db_session.scalar(select(func.count()).select_from(User)) == 1


def test_same_subject_from_another_issuer_is_another_person(db_session: Session) -> None:
    a = provision_user(db_session, LOGAN)
    b = provision_user(db_session, VerifiedIdentity("https://cognito.test", "sub-1"))
    assert a.id != b.id


def test_insert_race_recovers_the_winner(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Simulate losing a first-login race: our lookup misses, but by the time we
    insert, a concurrent login has created the row. We must return that row."""
    from card_maven.identity import service

    winner = provision_user(db_session, LOGAN)
    real_find = service._find
    calls = {"n": 0}

    def stale_then_real(session: Session, identity: VerifiedIdentity) -> User | None:
        calls["n"] += 1
        return None if calls["n"] == 1 else real_find(session, identity)

    monkeypatch.setattr(service, "_find", stale_then_real)
    assert provision_user(db_session, LOGAN).id == winner.id
    assert db_session.scalar(select(func.count()).select_from(User)) == 1


def test_unrelated_integrity_errors_propagate(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sqlalchemy.exc import IntegrityError

    from card_maven.identity import service

    monkeypatch.setattr(service, "_find", lambda *_: None)
    provision_user(db_session, LOGAN)
    with pytest.raises(IntegrityError):
        provision_user(db_session, LOGAN)  # race path, but the row "vanished"
