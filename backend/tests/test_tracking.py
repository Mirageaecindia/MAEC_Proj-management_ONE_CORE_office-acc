"""Subtask Login/Logout: worked time = Logout - Login (app/services/tracking.py).

Idle time counts; a silent browser (laptop off) pauses the time and the
session resumes on its own when the app is open again.
"""

from datetime import UTC, datetime, timedelta

import pytest

import models
from app.core.database import SessionLocal
from app.domain.timesheets import total_hours
from app.repositories.tracking import TrackingRepository
from app.services.tracking import TrackingService

START, HEARTBEAT, LOGOUT = (f"/api/subtask-tracking/{step}" for step in ("start", "heartbeat", "logout"))


@pytest.fixture
def subtask(make, world, governed):
    project_id, node_a, *_ = governed
    return make.wbs_node(project_id, world.lead_e, engineer=world.emp1, parent_id=node_a.id, estimated_hours=4)


def _login(client, world, subtask):
    response = client.post(START, json={"subtask_id": subtask.id}, headers=world.eng_h)
    assert response.status_code == 201, response.text
    return response.json()["active_session"]["id"]


def _rewind(db, session_id, *, logged_in, last_seen):
    """Move a session back in time: logged in `logged_in` ago, last heartbeat `last_seen` ago."""
    now = datetime.now(UTC)
    session = db.get(models.TimeSession, session_id)
    session.login_at, session.last_seen_at = now - logged_in, now - last_seen
    db.commit()
    return session.login_at


def _banked_hours(db, subtask):
    return total_hours(db.query(models.TimeLogEntry).filter_by(task_id=subtask.id))


def test_worked_time_is_logout_minus_login_idle_included(client, db, world, subtask):
    session_id = _login(client, world, subtask)
    _rewind(db, session_id, logged_in=timedelta(minutes=90), last_seen=timedelta(minutes=1))

    response = client.post(LOGOUT, headers=world.eng_h)

    assert response.status_code == 200, response.text
    assert response.json() == {"active_session": None, "limit_reached": False}
    assert _banked_hours(db, subtask) == 1.5  # no activity was measured; the whole period counts


def test_heartbeat_keeps_the_session_and_reports_it(client, db, world, subtask):
    session_id = _login(client, world, subtask)
    _rewind(db, session_id, logged_in=timedelta(minutes=30), last_seen=timedelta(minutes=3))

    response = client.post(HEARTBEAT, headers=world.eng_h)

    assert response.json()["active_session"]["id"] == session_id
    db.expire_all()
    last_seen = db.get(models.TimeSession, session_id).last_seen_at.replace(tzinfo=UTC)
    assert datetime.now(UTC) - last_seen < timedelta(seconds=5)


def test_laptop_off_pauses_the_time_and_the_session_resumes_by_itself(client, db, world, subtask):
    session_id = _login(client, world, subtask)
    login_at = _rewind(db, session_id, logged_in=timedelta(hours=3), last_seen=timedelta(hours=2))

    response = client.post(HEARTBEAT, headers=world.eng_h)  # the laptop is back on

    resumed = response.json()["active_session"]
    assert resumed["subtask_id"] == subtask.id and resumed["id"] != session_id
    db.expire_all()
    closed = db.get(models.TimeSession, session_id)
    assert closed.status == "ended"
    assert closed.logout_at == login_at + timedelta(hours=1)  # at the last heartbeat
    assert _banked_hours(db, subtask) == 1.0  # the two hours off are not counted


def test_logout_after_the_laptop_was_off_ends_at_the_last_heartbeat(client, db, world, subtask):
    session_id = _login(client, world, subtask)
    _rewind(db, session_id, logged_in=timedelta(hours=3), last_seen=timedelta(hours=1))

    client.post(LOGOUT, headers=world.eng_h)

    assert _banked_hours(db, subtask) == 2.0
    assert db.query(models.TimeSession).filter_by(status="active").count() == 0


def test_daily_limit_caps_the_banked_time(client, db, world, subtask):
    earlier = _login(client, world, subtask)
    login_at = _rewind(db, earlier, logged_in=timedelta(hours=1), last_seen=timedelta(0))
    ended = db.get(models.TimeSession, earlier)
    ended.status, ended.active_seconds = "ended", int(7.5 * 3600)  # 7.5 h already banked that day
    db.commit()
    session_id = _login(client, world, subtask)
    session = db.get(models.TimeSession, session_id)
    session.login_at = login_at  # same day as the banked session
    db.commit()

    response = client.post(LOGOUT, headers=world.eng_h)

    assert response.json()["limit_reached"] is True
    assert _banked_hours(db, subtask) == 0.5
    refused = client.post(START, json={"subtask_id": subtask.id}, headers=world.eng_h)
    assert refused.status_code == 409 and "daily limit" in refused.json()["detail"]


def test_login_is_refused_where_it_does_not_apply(client, make, world, governed, subtask):
    project_id, node_a, *_ = governed
    someone_elses = make.wbs_node(project_id, world.lead_e, engineer=world.emp2, parent_id=node_a.id)

    assert client.post(START, json={"subtask_id": node_a.id}, headers=world.eng_h).status_code == 400  # a main task
    assert client.post(START, json={"subtask_id": someone_elses.id}, headers=world.eng_h).status_code == 403
    assert client.post(START, json={"subtask_id": 99999}, headers=world.eng_h).status_code == 404
    _login(client, world, subtask)
    again = client.post(START, json={"subtask_id": subtask.id}, headers=world.eng_h)
    assert again.status_code == 409  # one session at a time
    assert client.post(HEARTBEAT, headers=world.bu_h).status_code == 403  # staff only


def test_two_tabs_resuming_at_once_bank_the_time_once(client, db, world, subtask):
    session_id = _login(client, world, subtask)
    _rewind(db, session_id, logged_in=timedelta(hours=3), last_seen=timedelta(hours=2))
    tab_a, tab_b = SessionLocal(), SessionLocal()
    service_a = TrackingService(tab_a, TrackingRepository(tab_a))
    service_b = TrackingService(tab_b, TrackingRepository(tab_b))
    stale = service_b.sessions.active_session(world.emp1.id)  # tab B read the session before tab A wrote
    fresh = service_b.sessions.active_session
    reads = iter([stale])
    service_b.sessions.active_session = lambda employee_id: next(reads, None) or fresh(employee_id)
    try:
        resumed_a = service_a.heartbeat(world.engineer)["active_session"]
        resumed_b = service_b.heartbeat(world.engineer)["active_session"]
    finally:
        tab_a.close()
        tab_b.close()

    assert resumed_a["id"] == resumed_b["id"]  # tab B sees tab A's result
    assert db.query(models.TimeSession).filter_by(status="active").count() == 1
    assert _banked_hours(db, subtask) == 1.0  # banked once
