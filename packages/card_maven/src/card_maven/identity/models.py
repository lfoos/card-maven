from __future__ import annotations

from sqlalchemy import String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from card_maven.shared.db import Base, TimestampMixin, UUIDPrimaryKeyMixin


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A collector. Credentials live in the identity provider, never here.

    A user is identified by the (issuer, subject) pair from their OIDC token, so
    moving from Keycloak to Cognito can't collide two people onto one row.
    """

    __tablename__ = "app_user"  # "user" is a reserved word in Postgres

    idp_issuer: Mapped[str] = mapped_column(String(500))
    idp_subject: Mapped[str] = mapped_column(String(255))
    email: Mapped[str | None] = mapped_column(String(320))
    display_name: Mapped[str | None] = mapped_column(String(200))

    __table_args__ = (UniqueConstraint("idp_issuer", "idp_subject"),)
