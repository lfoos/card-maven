"""Owner-scoped data access. All user-owned reads and writes go through here."""

from __future__ import annotations

import uuid

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from card_maven.shared.db import OwnedMixin
from card_maven.shared.errors import NotFoundError


class OwnedRepository[T: OwnedMixin]:
    """Scopes every query to one owner.

    Subclasses build queries from :meth:`_scoped` and never from ``select()``
    directly, so a missing owner filter can't slip in. Rows owned by someone
    else are indistinguishable from rows that don't exist (``NotFoundError``),
    so ids reveal nothing about other users' data.
    """

    model: type[T]
    not_found_message = "not found"

    def __init__(self, session: Session, owner_id: uuid.UUID) -> None:
        self.session = session
        self.owner_id = owner_id

    def _scoped(self) -> Select[T]:
        return select(self.model).where(self.model.owner_id == self.owner_id)

    def get(self, entity_id: uuid.UUID) -> T:
        row = self.session.scalars(
            self._scoped().where(self.model.id == entity_id)  # type: ignore[attr-defined]
        ).one_or_none()
        if row is None:
            raise NotFoundError(self.not_found_message)
        return row

    def add(self, entity: T) -> T:
        entity.owner_id = self.owner_id
        self.session.add(entity)
        self.session.flush()
        return entity

    def delete(self, entity: T) -> None:
        if entity.owner_id != self.owner_id:
            raise NotFoundError(self.not_found_message)
        self.session.delete(entity)
        self.session.flush()
