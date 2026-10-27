"""Just-in-time user provisioning from verified OIDC identities."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from card_maven.identity.models import User


@dataclass(frozen=True, slots=True)
class VerifiedIdentity:
    """Who the identity provider says the caller is (already verified upstream)."""

    issuer: str
    subject: str
    email: str | None = None
    display_name: str | None = None


def _find(session: Session, identity: VerifiedIdentity) -> User | None:
    return session.scalars(
        select(User).where(User.idp_issuer == identity.issuer, User.idp_subject == identity.subject)
    ).one_or_none()


def provision_user(session: Session, identity: VerifiedIdentity) -> User:
    """Return the user for ``identity``, creating them on first sight.

    Profile fields are refreshed from the token so a changed email or name in
    the identity provider is reflected here. Safe under concurrent first logins:
    the loser of the insert race re-reads the winner's row.
    """
    user = _find(session, identity)
    if user is None:
        try:
            with session.begin_nested():
                user = User(
                    idp_issuer=identity.issuer,
                    idp_subject=identity.subject,
                    email=identity.email,
                    display_name=identity.display_name,
                )
                session.add(user)
        except IntegrityError:
            user = _find(session, identity)
            if user is None:  # the row vanished mid-race: surface the real error
                raise
    if (user.email, user.display_name) != (identity.email, identity.display_name):
        user.email = identity.email
        user.display_name = identity.display_name
    session.flush()
    return user
