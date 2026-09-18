"""Authentication helpers for MAEC.

Passwords are hashed with PBKDF2-HMAC-SHA256 (stdio, no external deps) and
sessions are opaque bearer tokens stored in `login_sessions`. `get_current_user`
resolves the logged-in user's identity from the `Authorization: Bearer <token>`
header on every protected request — role is never derived from a client-supplied
header, query parameter, or localStorage value.
"""
import hashlib
import secrets
from typing import Optional

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

import models
from database import get_db

_PBKDF2_ITERATIONS = 100_000
_ALGO = "pbkdf2_sha256"


def hash_password(password: str) -> str:
    """Return a salted PBKDF2-HMAC-SHA256 hash string: algo$salt$hexdigest."""
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), _PBKDF2_ITERATIONS
    )
    return f"{_ALGO}${salt}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, salt, expected = (stored or "").split("$", 2)
    except ValueError:
        return False
    if algo != _ALGO:
        return False
    try:
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt), _PBKDF2_ITERATIONS
        )
    except ValueError:
        return False
    return secrets.compare_digest(digest.hex(), expected)


def get_current_user(
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
) -> "models.User":
    """FastAPI dependency returning the authenticated user, or 401."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Authentication required.")
    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required.")
    session = db.query(models.LoginSession).filter_by(token=token).first()
    if not session:
        raise HTTPException(status_code=401, detail="Session expired or invalid.")
    user = db.query(models.User).filter_by(id=session.user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found.")
    return user