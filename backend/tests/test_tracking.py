"""Subtask Login/Logout: worked time = Logout - Login (app/services/tracking.py).

Idle time counts; a silent browser (laptop off) pauses the time and the
session resumes on its own when the app is open again. Past 8 h in a day the
engineer must visit the app every 30 minutes or is logged out at the last visit.
"""

from datetime import UTC, datetime, timedelta

import pytest

import models
from app.core.database import SessionLocal
from app.domain.timesheets import total_hours
from app.repositories.tracking import TrackingRepository
from app.services.tracking import LAPTOP_OFF, NO_VISIT, TrackingService, upsert_subtask_time_log

START, HEARTBEAT, LOGOUT = (f"/api/subtask-tracking/{step}" for step in ("start", "heartbeat", "logout"))


@pytest.fixture
def subtask(make, world, governed):
    project_id, node_a, *_ = governed
    return make.wbs_node(project_id, world.lead_e, engineer=world.emp1, parent_id=node_a.id, estimated_hours=4)


def _login(client, world, subtask):
    response = client.post(START, json={"subtask_id": subtask.id}, headers=world.eng_h)
    assert response.status_code == 201, response.text
    return response.json()["active_session"]["id"]


def _rewind(db, session_id, *, logged_in, last_seen, last_visit=None):
    """Move a session back in time: logged in `logged_in` ago, last heartbeat `last_seen` ago,
    last visit to the app `last_visit` ago (the login itself by default)."""
    now = datetime.now(UTC)
    session = db.get(models.TimeSession, session_id)
    session.login_at, session.last_seen_at = now - logged_in, now - last_seen
    session.last_active_at = now - (logged_in if last_visit is None else last_visit)
    db.commit()
    return session.login_at


def _banked_today(db, session_id, hours):
    """An earlier session of the same day, already ended with `hours` banked."""
    ended = db.get(models.TimeSession, session_id)
    ended.status, ended.active_seconds, ended.logout_at = "ended", int(hours * 3600), ended.login_at
    upsert_subtask_time_log(
        db, ended.project_id, ended.subtask_id, ended.employee_id, ended.login_at.date(), ended.active_seconds
    )
    db.commit()


def _banked_hours(db, subtask):
    return total_hours(db.query(models.TimeLogEntry).filter_by(task_id=subtask.id))


def test_worked_time_is_logout_minus_login_idle_included(client, db, world, subtask):
    session_id = _login(client, world, subtask)
    _rewind(db, session_id, logged_in=timedelta(minutes=90), last_seen=timedelta(minutes=1))

    response = client.post(LOGOUT, headers=world.eng_h)

    assert response.status_code == 200, response.text
    assert response.json() == {"active_session": None, "over_mark": False}
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
    assert (closed.status, closed.ended_by) == ("ended", LAPTOP_OFF)
    assert closed.logout_at == login_at + timedelta(hours=1)  # at the last heartbeat
    assert _banked_hours(db, subtask) == 1.0  # the two hours off are not counted


def test_logout_after_the_laptop_was_off_ends_at_the_last_heartbeat(client, db, world, subtask):
    session_id = _login(client, world, subtask)
    _rewind(db, session_id, logged_in=timedelta(hours=3), last_seen=timedelta(hours=1))

    client.post(LOGOUT, headers=world.eng_h)

    assert _banked_hours(db, subtask) == 2.0
    assert db.query(models.TimeSession).filter_by(status="active").count() == 0


def test_hours_over_eight_are_banked_and_login_stays_allowed(client, db, world, subtask):
    earlier = _login(client, world, subtask)
    _rewind(db, earlier, logged_in=timedelta(hours=7), last_seen=timedelta(0))
    _banked_today(db, earlier, 6)  # 6 h on the first subtask
    _rewind(db, _login(client, world, subtask), logged_in=timedelta(hours=4), last_seen=timedelta(0))

    response = client.post(LOGOUT, headers=world.eng_h)

    assert response.json() == {"active_session": None, "over_mark": True}
    assert _banked_hours(db, subtask) == 10.0  # 6 + 4, nothing cut at 8
    assert client.post(START, json={"subtask_id": subtask.id}, headers=world.eng_h).status_code == 201


def test_before_the_daily_mark_only_the_engineer_logs_out(client, db, world, subtask):
    session_id = _login(client, world, subtask)
    _rewind(db, session_id, logged_in=timedelta(hours=7), last_seen=timedelta(0), last_visit=timedelta(hours=7))

    response = client.post(HEARTBEAT, headers=world.eng_h)  # seven hours without a visit

    assert response.json() == {"active_session": response.json()["active_session"], "over_mark": False}
    assert response.json()["active_session"]["id"] == session_id


def test_past_the_mark_a_visit_within_thirty_minutes_keeps_the_session(client, db, world, subtask):
    earlier = _login(client, world, subtask)
    _rewind(db, earlier, logged_in=timedelta(hours=9), last_seen=timedelta(0))
    _banked_today(db, earlier, 6)
    session_id = _login(client, world, subtask)
    _rewind(
        db,
        session_id,
        logged_in=timedelta(hours=2, minutes=10),
        last_seen=timedelta(0),
        last_visit=timedelta(minutes=29),
    )

    response = client.post(HEARTBEAT, headers=world.eng_h)

    assert response.json()["active_session"]["id"] == session_id
    assert response.json()["over_mark"] is True  # 6 h banked + 2 h 10 min running


def test_past_the_mark_thirty_minutes_without_a_visit_logs_out_at_the_last_visit(client, db, world, subtask):
    earlier = _login(client, world, subtask)
    _rewind(db, earlier, logged_in=timedelta(hours=9), last_seen=timedelta(0))
    _banked_today(db, earlier, 6)
    session_id = _login(client, world, subtask)
    _rewind(
        db,
        session_id,
        logged_in=timedelta(hours=2, minutes=10),
        last_seen=timedelta(0),
        last_visit=timedelta(minutes=31),
    )

    response = client.post(HEARTBEAT, headers=world.eng_h)

    assert response.json()["active_session"] is None
    logout = response.json()["system_logout"]
    assert (logout["subtask_id"], logout["day_hours"]) == (subtask.id, 6 + round(99 / 60, 2))  # 2 h 10 min - 31 min
    db.expire_all()
    closed = db.get(models.TimeSession, session_id)
    assert (closed.status, closed.ended_by) == ("ended", NO_VISIT)
    assert closed.logout_at == closed.last_active_at
    assert _banked_hours(db, subtask) == 6 + round(99 / 60, 2)
    again = client.post(HEARTBEAT, headers=world.eng_h)  # nothing resumes by itself
    assert again.json()["active_session"] is None and again.json()["system_logout"] == logout
    assert client.post(START, json={"subtask_id": subtask.id}, headers=world.eng_h).status_code == 201  # by hand
    assert client.post(HEARTBEAT, headers=world.eng_h).json().get("system_logout") is None


def test_visits_keep_a_ten_hour_day_alive(client, db, world, subtask):
    session_id = _login(client, world, subtask)
    _rewind(db, session_id, logged_in=timedelta(hours=10), last_seen=timedelta(0), last_visit=timedelta(minutes=40))

    response = client.post(HEARTBEAT, json={"last_active_at": datetime.now(UTC).isoformat()}, headers=world.eng_h)

    assert response.json()["active_session"]["id"] == session_id and response.json()["over_mark"] is True
    db.expire_all()
    session = db.get(models.TimeSession, session_id)
    assert datetime.now(UTC) - session.last_active_at.replace(tzinfo=UTC) < timedelta(seconds=5)


def test_a_reported_visit_is_never_in_the_future_nor_before_the_last_one(client, db, world, subtask):
    session_id = _login(client, world, subtask)
    _rewind(db, session_id, logged_in=timedelta(hours=1), last_seen=timedelta(0), last_visit=timedelta(minutes=10))
    ahead = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    client.post(HEARTBEAT, json={"last_active_at": ahead}, headers=world.eng_h)
    db.expire_all()
    clamped = db.get(models.TimeSession, session_id).last_active_at.replace(tzinfo=UTC)
    assert datetime.now(UTC) - clamped < timedelta(seconds=5)

    behind = (datetime.now(UTC) - timedelta(hours=3)).isoformat()
    client.post(HEARTBEAT, json={"last_active_at": behind}, headers=world.eng_h)
    db.expire_all()
    assert db.get(models.TimeSession, session_id).last_active_at.replace(tzinfo=UTC) == clamped


def test_laptop_off_past_the_mark_still_pauses_and_resumes(client, db, world, subtask):
    session_id = _login(client, world, subtask)
    _rewind(db, session_id, logged_in=timedelta(hours=9), last_seen=timedelta(hours=1), last_visit=timedelta(hours=2))

    response = client.post(HEARTBEAT, headers=world.eng_h)

    resumed = response.json()["active_session"]
    assert resumed and resumed["id"] != session_id
    assert _banked_hours(db, subtask) == 8.0  # nine hours minus the hour off; nothing cut at 8


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
