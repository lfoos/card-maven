"""Request-scoped units of work."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from flask import current_app
from sqlalchemy.orm import Session

from card_maven.shared.db import session_scope
from card_maven_api.extensions import api_context


@contextmanager
def transaction() -> Iterator[Session]:
    """Commit on success, roll back on error. Side effects that must only happen
    after a successful commit (e.g. deleting stored files) go after the block."""
    with session_scope(api_context(current_app).session_factory) as session:
        yield session
