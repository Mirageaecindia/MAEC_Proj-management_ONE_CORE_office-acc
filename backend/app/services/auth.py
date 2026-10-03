"""Login, logout and brute-force protection."""

import math
import secrets
import threading
from collections import defaultdict
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from functools import lru_cache

from sqlalchemy import func
from sqlalchemy.orm import Session

import models
import schemas
from app.core.config import Settings, get_settings
from app.core.errors import BadRequestError, TooManyRequestsError, UnauthorizedError
from app.core.roles import Role
from app.services.access import leads_any_project
from app.core.security import hash_password, verify_password

INVALID_CREDENTIALS = "Invalid username or password."
MIN_PASSWORD_LENGTH = 8
WRONG_CURRENT_PASSWORD = "The current password is not correct."
PASSWORD_TOO_SHORT = f"Use at least {MIN_PASSWORD_LENGTH} characters."
SAME_PASSWORD = "Choose a password different from the current one."


def _utc_now() -> datetime:
    return datetime.now(UTC)


class LoginThrottle:
    """Locks a username after too many failed logins within a time window.

    Keyed by username (case-insensitive) so one account cannot be brute-forced
    from many addresses. State is in-memory: it is per process and resets on
    restart, which is enough for a single-server deployment.
    """

    def __init__(self, max_failures: int, window: timedelta, clock: Callable[[], datetime] = _utc_now):
        self._max_failures = max_failures
        self._window = window
        self._clock = clock
        self._failures: dict[str, list[datetime]] = defaultdict(list)
        self._lock = threading.Lock()

    def check(self, username: str) -> None:
        """Raise 429 if the username is currently locked out."""
        key = username.strip().lower()
        with self._lock:
            now = self._clock()
            recent = [moment for moment in self._failures[key] if now - moment < self._window]
            self._failures[key] = recent
            if len(recent) >= self._max_failures:
                retry_after = self._window - (now - recent[0])
                minutes = max(1, math.ceil(retry_after.total_seconds() / 60))
                raise TooManyRequestsError(
                    f"Too many failed login attempts. Try again in {minutes} minute(s).",
                    headers={"Retry-After": str(math.ceil(retry_after.total_seconds()))},
                )

    def record_failure(self, username: str) -> None:
        with self._lock:
            self._failures[username.strip().lower()].append(self._clock())

    def reset(self, username: str) -> None:
        with self._lock:
            self._failures.pop(username.strip().lower(), None)


@lru_cache
def get_login_throttle() -> LoginThrottle:
    """Process-wide throttle (a FastAPI dependency, overridable in tests)."""
    settings = get_settings()
    return LoginThrottle(settings.login_max_failed_attempts, timedelta(minutes=settings.login_lockout_minutes))


class AuthService:
    def __init__(self, db: Session, throttle: LoginThrottle, settings: Settings):
        self.db = db
        self.throttle = throttle
        self.settings = settings

    def login(self, username: str, password: str) -> schemas.LoginResponse:
        username = username.strip()
        self.throttle.check(username)
        # Usernames are work emails: matched without regard to case.
        user = self.db.query(models.User).filter(func.lower(models.User.username) == username.lower()).first()
        if not user or not verify_password(password, user.password_hash) or not user.is_active:
            self.throttle.record_failure(username)
            raise UnauthorizedError(INVALID_CREDENTIALS)
        self.throttle.reset(username)

        self._purge_expired_sessions()
        token = secrets.token_hex(32)
        self.db.add(models.LoginSession(token=token, user_id=user.id))
        self.db.commit()
        return schemas.LoginResponse(
            token=token,
            id=user.id,
            role=user.role,
            username=user.username,
            full_name=user.full_name,
            engineer_id=user.employee_id if user.role == Role.ENGINEER else None,
            leads_projects=leads_any_project(self.db, user),
            must_change_password=user.must_change_password,
        )

    def change_password(self, user: models.User, token: str | None, current: str, new: str) -> None:
        """The person sets their own password. Every other session of theirs ends."""
        if not verify_password(current, user.password_hash):
            raise BadRequestError(WRONG_CURRENT_PASSWORD)
        if len(new) < MIN_PASSWORD_LENGTH:
            raise BadRequestError(PASSWORD_TOO_SHORT)
        if new == current:
            raise BadRequestError(SAME_PASSWORD)
        user.password_hash, user.must_change_password = hash_password(new), False
        others = models.LoginSession.user_id == user.id
        if token:
            others &= models.LoginSession.token != token
        self.db.query(models.LoginSession).filter(others).delete(synchronize_session=False)
        self.db.commit()

    def logout(self, token: str | None) -> None:
        """Idempotent: a missing or already-deleted token is fine."""
        if token:
            self.db.query(models.LoginSession).filter_by(token=token).delete()
            self.db.commit()

    def _purge_expired_sessions(self) -> None:
        # Stored timestamps are naive UTC in SQLite, so compare with a naive UTC cutoff.
        cutoff = (_utc_now() - timedelta(hours=self.settings.session_ttl_hours)).replace(tzinfo=None)
        self.db.query(models.LoginSession).filter(models.LoginSession.created_at < cutoff).delete(
            synchronize_session=False
        )
