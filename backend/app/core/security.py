"""Password hashing, bearer-token authentication and role checks.

Passwords are hashed with PBKDF2-HMAC-SHA256 (stdlib). Sessions are opaque
bearer tokens stored in `login_sessions`. Identity and role always come from
the token, never from a client-supplied header, query parameter or storage.
"""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

import models
from app.core.config import get_settings
from app.core.database import get_db
from app.core.roles import ALL_ROLES, Role

PBKDF2_ITERATIONS = 100_000
_ALGO = "pbkdf2_sha256"

FORBIDDEN_FOR_ROLE = "This action is not allowed for the current role."
SESSION_ERROR = "Session expired or invalid — please log in again."


def hash_password(password: str) -> str:
    """Return a salted PBKDF2-HMAC-SHA256 hash string: algo$salt$hexdigest."""
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), PBKDF2_ITERATIONS)
    return f"{_ALGO}${salt}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, salt, expected = (stored or "").split("$", 2)
    except ValueError:
        return False
    if algo != _ALGO:
        return False
    try:
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), PBKDF2_ITERATIONS)
    except ValueError:
        return False
    return secrets.compare_digest(digest.hex(), expected)


def bearer_token(authorization: str | None) -> str | None:
    """Extract the token from an `Authorization: Bearer <token>` header value."""
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    return authorization.split(" ", 1)[1].strip() or None


def as_utc(value: datetime) -> datetime:
    """SQLite returns naive datetimes; stored timestamps are UTC."""
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def session_is_expired(created_at: datetime | None, ttl_hours: float, now: datetime | None = None) -> bool:
    """A session expires `ttl_hours` after login. A missing timestamp counts as expired."""
    if created_at is None:
        return True
    return (now or datetime.now(UTC)) - as_utc(created_at) > timedelta(hours=ttl_hours)


def get_current_user(
    authorization: str | None = Header(None),
    db: Session = Depends(get_db),
) -> models.User:
    """FastAPI dependency returning the authenticated user, or 401.

    Expired sessions are deleted on first use, so a stolen or forgotten token
    stops working after SESSION_TTL_HOURS.
    """
    token = bearer_token(authorization)
    if not token:
        raise HTTPException(status_code=401, detail=SESSION_ERROR)
    session = db.query(models.LoginSession).filter_by(token=token).first()
    if not session:
        raise HTTPException(status_code=401, detail=SESSION_ERROR)
    if session_is_expired(session.created_at, get_settings().session_ttl_hours):
        db.delete(session)
        db.commit()
        raise HTTPException(status_code=401, detail=SESSION_ERROR)
    user = db.get(models.User, session.user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail=SESSION_ERROR)
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
require_lead_or_bu_head = require_roles(Role.LEAD, Role.BU_HEAD)
require_any_role = require_roles(*ALL_ROLES)
