import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from card_maven.market.models import TrackedSet
from card_maven.market.tracked_sets import SyncResult, TrackedSetSpec, sync_tracked_sets
from card_maven.shared.errors import InvalidInputError

pytestmark = pytest.mark.db

CHROME_2024 = TrackedSetSpec("baseball", "bowman", "Bowman Chrome", 2024)
CHROME_2025 = TrackedSetSpec("baseball", "bowman", "Bowman Chrome", 2025)
YOUNG_GUNS = TrackedSetSpec("hockey", "upper-deck", "Series 1", 2025, focus="Young Guns")


def active_keys(session: Session) -> set[tuple[str, int]]:
    rows = session.scalars(select(TrackedSet).where(TrackedSet.active)).all()
    return {(r.set_name, r.year) for r in rows}


def test_creates_then_is_idempotent(seeded_session: Session) -> None:
    first = sync_tracked_sets(seeded_session, [CHROME_2024, CHROME_2025])
    assert first == SyncResult(created=2)
    second = sync_tracked_sets(seeded_session, [CHROME_2024, CHROME_2025])
    assert second == SyncResult(unchanged=2)


def test_deactivates_removed_and_reactivates_returning(seeded_session: Session) -> None:
    sync_tracked_sets(seeded_session, [CHROME_2024, CHROME_2025])
    assert sync_tracked_sets(seeded_session, [CHROME_2025]) == SyncResult(
        deactivated=1, unchanged=1
    )
    assert active_keys(seeded_session) == {("Bowman Chrome", 2025)}
    # Deactivated rows are kept, not deleted.
    assert len(seeded_session.scalars(select(TrackedSet)).all()) == 2

    assert sync_tracked_sets(seeded_session, [CHROME_2024, CHROME_2025]) == SyncResult(
        reactivated=1, unchanged=1
    )
    assert active_keys(seeded_session) == {("Bowman Chrome", 2024), ("Bowman Chrome", 2025)}


def test_updates_focus(seeded_session: Session) -> None:
    sync_tracked_sets(seeded_session, [YOUNG_GUNS])
    changed = TrackedSetSpec("hockey", "upper-deck", "Series 1", 2025, focus=None)
    assert sync_tracked_sets(seeded_session, [changed]) == SyncResult(updated=1)
    row = seeded_session.scalars(select(TrackedSet)).one()
    assert row.focus is None


def test_reactivation_with_focus_change_counts_once(seeded_session: Session) -> None:
    sync_tracked_sets(seeded_session, [YOUNG_GUNS])
    sync_tracked_sets(seeded_session, [])
    changed = TrackedSetSpec("hockey", "upper-deck", "Series 1", 2025, focus="Base")
    assert sync_tracked_sets(seeded_session, [changed]) == SyncResult(reactivated=1)


def test_empty_spec_deactivates_everything(seeded_session: Session) -> None:
    sync_tracked_sets(seeded_session, [CHROME_2024, YOUNG_GUNS])
    assert sync_tracked_sets(seeded_session, []) == SyncResult(deactivated=2)
    assert active_keys(seeded_session) == set()


def test_unknown_sport_or_brand_fails_before_any_write(seeded_session: Session) -> None:
    bad = [CHROME_2024, TrackedSetSpec("curling", "acme", "Stones", 2025)]
    with pytest.raises(InvalidInputError) as excinfo:
        sync_tracked_sets(seeded_session, bad)
    assert excinfo.value.extra == {"unknown_sports": ["curling"], "unknown_brands": ["acme"]}
    assert seeded_session.scalars(select(TrackedSet)).all() == []
