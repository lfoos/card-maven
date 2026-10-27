"""Per-application dependencies, held on ``app.extensions`` instead of globals."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from flask import Flask
from sqlalchemy.orm import Session, sessionmaker

from card_maven.shared.config import Settings

if TYPE_CHECKING:
    from card_maven.shared.storage import ObjectStore
    from card_maven_api.auth.tokens import TokenVerifier

EXTENSION_KEY = "card_maven"


@dataclass(frozen=True, slots=True)
class ApiContext:
    settings: Settings
    session_factory: sessionmaker[Session]
    token_verifier: TokenVerifier
    object_store: ObjectStore


def api_context(app: Flask) -> ApiContext:
    context: ApiContext = app.extensions[EXTENSION_KEY]
    return context
