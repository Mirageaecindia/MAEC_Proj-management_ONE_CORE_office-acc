"""Session expiry and brute-force protection on login."""

from datetime import UTC, datetime, timedelta

import pytest

import models
from app.core.errors import TooManyRequestsError
from app.core.security import session_is_expired
from app.services.auth import LoginThrottle
from factories import PASSWORD


def _login(client, username, password=PASSWORD):
    return client.post("/api/auth/login", json={"username": username, "password": password})


def _age_session(db, headers, hours):
    token = headers["Authorization"].split(" ", 1)[1]
    session = db.query(models.LoginSession).filter_by(token=token).one()
    session.created_at = (datetime.now(UTC) - timedelta(hours=hours)).replace(tzinfo=None)
    db.commit()
    return token


# --- Session expiry ------------------------------------------------------------------


def test_fresh_session_is_accepted(client, world):
    assert client.get("/api/auth/me", headers=world.bu_h).status_code == 200


def test_expired_session_is_rejected_and_deleted(client, db, world):
    token = _age_session(db, world.bu_h, hours=13)

    response = client.get("/api/auth/me", headers=world.bu_h)

    assert response.status_code == 401
    assert "Session expired or invalid" in response.json()["detail"]
    db.expire_all()
    assert db.query(models.LoginSession).filter_by(token=token).count() == 0


def test_login_purges_other_expired_sessions(client, db, world):
    stale = _age_session(db, world.lead_h, hours=24)

    assert _login(client, "buhead").status_code == 200

    db.expire_all()
    assert db.query(models.LoginSession).filter_by(token=stale).count() == 0


@pytest.mark.parametrize(
    ("age_hours", "expired"),
    [(0, False), (11.9, False), (12.1, True)],
)
def test_session_is_expired_boundary(age_hours, expired):
    now = datetime(2026, 9, 25, 12, 0, tzinfo=UTC)
    created_naive_utc = (now - timedelta(hours=age_hours)).replace(tzinfo=None)

    assert session_is_expired(created_naive_utc, 12, now=now) is expired
    assert session_is_expired(None, 12, now=now) is True


# --- Login throttle ------------------------------------------------------------------


def test_repeated_failures_lock_the_username(client, world):
    for _ in range(5):
        assert _login(client, "buhead", "wrong-password").status_code == 401

    locked = _login(client, "buhead")  # even the correct password is refused while locked

    assert locked.status_code == 429
    assert "Too many failed login attempts" in locked.json()["detail"]
    assert int(locked.headers["Retry-After"]) > 0
    assert _login(client, "lead.e").status_code == 200  # other users are unaffected


def test_successful_login_resets_the_failure_count(client, world):
    for _ in range(4):
        _login(client, "buhead", "wrong-password")
    assert _login(client, "buhead").status_code == 200

    for _ in range(4):
        _login(client, "buhead", "wrong-password")
    assert _login(client, "buhead").status_code == 200


def test_throttle_is_case_insensitive_and_expires_after_the_window():
    now = [datetime(2026, 9, 25, 9, 0, tzinfo=UTC)]
    throttle = LoginThrottle(max_failures=2, window=timedelta(minutes=15), clock=lambda: now[0])

    throttle.record_failure("BuHead")
    throttle.record_failure("buhead ")
    with pytest.raises(TooManyRequestsError):
        throttle.check("buhead")

    now[0] += timedelta(minutes=16)
    throttle.check("BUHEAD")  # window passed: allowed again
