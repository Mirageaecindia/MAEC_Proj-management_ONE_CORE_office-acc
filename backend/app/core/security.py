"""Who is asking, and role checks.

Nobody signs in to this app: MAEC One Core does. The gate (app/api/gate.py) asks Core about
every request and puts the answer on `request.state.maec`; app/core/identity.py maps it to
the local users row. Identity and role always come from there, never from a client-supplied
header, query parameter or storage. The role (bu_head | engineer) is this app's own, read
from users.role on every request; leading a project is a role on the project
(app/services/access.py).
"""

from datetime import UTC, datetime

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

import models
from app.core.database import get_db
from app.core.identity import CoreIdentity, local_user
from app.core.roles import ALL_ROLES, Role

FORBIDDEN_FOR_ROLE = "This action is not allowed for the current role."
NOT_THROUGH_THE_GATE = "MAEC One is unavailable"

# What users.password_hash holds for an account created after the move to MAEC One: no
# password matches it. The column is dropped by a later migration, after go-live.
NO_PASSWORD = "!"


def as_utc(value: datetime) -> datetime:
    """SQLite returns naive datetimes; stored timestamps are UTC."""
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def core_identity(request: Request) -> CoreIdentity:
    """Core's answer for this request. Every API request passes the gate first; a request that
    somehow did not is refused (503), never let through."""
    maec = getattr(request.state, "maec", None)
    if not maec:
        raise HTTPException(status_code=503, detail=NOT_THROUGH_THE_GATE)
    return CoreIdentity.from_gate(maec)


def get_session_user(request: Request, db: Session = Depends(get_db)) -> models.User:
    """The person MAEC One vouched for, as this app's users row; 403 when they have no
    profile here or theirs is deactivated (app/core/identity.py)."""
    return local_user(db, core_identity(request))


def get_current_user(user: models.User = Depends(get_session_user)) -> models.User:
    """FastAPI dependency returning the signed-in user. The same as get_session_user since
    MAEC One took over passwords; kept as the name every endpoint uses."""
    return user


def require_role(role: str | None, allowed: set[str]) -> None:
    """Imperative role check (used by legacy endpoints in main.py)."""
    if role not in allowed:
        raise HTTPException(status_code=403, detail=FORBIDDEN_FOR_ROLE)


def require_roles(*roles: Role):
    """Dependency factory: the authenticated user, or 403 if their role is not allowed."""
    allowed = {str(role) for role in roles}

    def dependency(user: models.User = Depends(get_current_user)) -> models.User:
        require_role(user.role, allowed)
        return user

    return dependency


# Named guards for routers: `user = Depends(require_bu_head)`.
require_bu_head = require_roles(Role.BU_HEAD)
require_staff = require_roles(Role.ENGINEER)  # everyone but the BU Head
require_any_role = require_roles(*ALL_ROLES)
