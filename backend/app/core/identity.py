"""Who the person MAEC One vouched for is in this app.

The gate (app/api/gate.py) puts Core's answer on request.state.maec, including
`user: {id, email, name}`. This maps it to the local users row. It is the one place that
does: the session dependency (app/core/security.py) and the audit log (app/services/audit.py)
both call `local_user`.

- An account already linked is matched by users.core_user_id only, so a later email change
  in Core keeps the link.
- Otherwise the one account whose username is that email (letter case and surrounding
  spaces ignored), and that isn't linked to another Core person, is linked now: its
  core_user_id is stored.
- Otherwise the person has no profile here. They are not created automatically (decided
  2026-10-13): an employee record needs the HR employee code and the job role, and Core
  knows neither. A BU Head adds them under People instead (app/services/provisioning.py).

Nothing from Core changes users.id, employees.id, full_name or role. Older lead rows are
matched by full_name (app/services/access.py), and the role is this app's to decide.
"""

from dataclasses import dataclass

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import models
from app.core.errors import ForbiddenError

# X-Error-Code values the frontend shows as a page of their own.
PROFILE_NOT_SET_UP = "PROFILE_NOT_SET_UP"
PROFILE_INACTIVE = "PROFILE_INACTIVE"

NOT_SET_UP = "Your Project Management profile hasn't been set up yet. Ask a Business Head."
TWO_PROFILES = "More than one Project Management profile uses your email. Ask a Business Head."
LINKED_ELSEWHERE = (
    "The Project Management profile with your email belongs to another MAEC One account. Ask a Business Head."
)
DEACTIVATED = "Your Project Management profile is deactivated. Ask a Business Head."


@dataclass(frozen=True)
class CoreIdentity:
    """The person as Core describes them in the gate's answer."""

    core_user_id: str
    email: str
    name: str

    @classmethod
    def from_gate(cls, maec: dict) -> "CoreIdentity":
        user = maec["user"]
        return cls(
            core_user_id=str(user["id"]), email=str(user["email"]).strip().lower(), name=str(user.get("name") or "")
        )


def _refuse(message: str, code: str) -> ForbiddenError:
    return ForbiddenError(message, headers={"X-Error-Code": code})


def find_linked(db: Session, core_user_id: str) -> models.User | None:
    return db.query(models.User).filter(models.User.core_user_id == core_user_id).first()


def _by_email(db: Session, email: str) -> list[models.User]:
    return db.query(models.User).filter(func.lower(func.trim(models.User.username)) == email).limit(2).all()


def local_user(db: Session, identity: CoreIdentity) -> models.User:
    """The person's users row, linking it at their first visit. 403 (with an X-Error-Code)
    when they have no profile here, or theirs is deactivated."""
    user = find_linked(db, identity.core_user_id) or _link_by_email(db, identity)
    if not user.is_active:
        raise _refuse(DEACTIVATED, PROFILE_INACTIVE)
    return user


def _link_by_email(db: Session, identity: CoreIdentity) -> models.User:
    matches = _by_email(db, identity.email)
    if not matches:
        raise _refuse(NOT_SET_UP, PROFILE_NOT_SET_UP)
    if len(matches) > 1:
        raise _refuse(TWO_PROFILES, PROFILE_NOT_SET_UP)
    user = matches[0]
    if user.core_user_id is not None:  # linked to someone else: never taken over by email alone
        raise _refuse(LINKED_ELSEWHERE, PROFILE_NOT_SET_UP)
    user.core_user_id = identity.core_user_id
    try:
        db.commit()
    except IntegrityError:
        # Two first requests at once: the other one linked it. Read what it stored.
        db.rollback()
        linked = find_linked(db, identity.core_user_id)
        if linked is None:
            raise
        return linked
    return user
