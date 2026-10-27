import pytest
from sqlalchemy import Engine, select, text
from sqlalchemy.orm import Session, sessionmaker

from card_maven.catalog.models import Sport
from card_maven.shared.db import make_session_factory, session_scope

pytestmark = pytest.mark.db


def test_session_scope_commits(committing_session_factory: sessionmaker[Session]) -> None:
    with session_scope(committing_session_factory) as session:
        session.add(Sport(code="cricket", name="Cricket"))
    with session_scope(committing_session_factory) as session:
        assert session.get(Sport, "cricket") is not None


def test_session_scope_rolls_back_on_error(
    committing_session_factory: sessionmaker[Session],
) -> None:
    def add_then_fail() -> None:
        with session_scope(committing_session_factory) as session:
            session.add(Sport(code="cricket", name="Cricket"))
            session.flush()
            raise ValueError("boom")

    with pytest.raises(ValueError, match="boom"):
        add_then_fail()
    with session_scope(committing_session_factory) as session:
        assert session.scalars(select(Sport)).all() == []


def test_make_session_factory_keeps_objects_usable_after_commit(engine: Engine) -> None:
    factory = make_session_factory(engine)
    with factory() as session:
        assert session.execute(text("SELECT 1")).scalar_one() == 1


def test_pgvector_extension_installed(db_session: Session) -> None:
    version = db_session.execute(
        text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
    ).scalar_one_or_none()
    assert version is not None
