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
from app.services import tracking
from app.services.tracking import BY_ENGINEER, LAPTOP_OFF, NO_VISIT, TrackingService, upsert_subtask_time_log

START, HEARTBEAT, LOGOUT = (f"/api/subtask-tracking/{step}" for step in ("start", "heartbeat", "logout"))
# The service's clock in these tests: noon UTC today, so "three hours ago" is the same
# calendar day whatever time the suite runs.
NOON = datetime.now(UTC).replace(hour=12, minute=0, second=0, microsecond=0)


@pytest.fixture(autouse=True)
def at_noon(monkeypatch):
    monkeypatch.setattr(tracking, "utcnow", lambda: NOON)


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
    now = NOON
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
    assert last_seen == NOON


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
        logged_in=timedelta(hours=2, minutes=40),  # the mark was passed 40 minutes ago
        last_seen=timedelta(0),
        last_visit=timedelta(minutes=31),
    )

    response = client.post(HEARTBEAT, headers=world.eng_h)

    assert response.json()["active_session"] is None
    logout = response.json()["system_logout"]
    assert (logout["subtask_id"], logout["day_hours"]) == (subtask.id, 6 + round(129 / 60, 2))  # 2 h 40 min - 31 min
    db.expire_all()
    closed = db.get(models.TimeSession, session_id)
    assert (closed.status, closed.ended_by) == ("ended", NO_VISIT)
    assert closed.logout_at == closed.last_active_at
    assert _banked_hours(db, subtask) == 6 + round(129 / 60, 2)
    again = client.post(HEARTBEAT, headers=world.eng_h)  # nothing resumes by itself
    assert again.json()["active_session"] is None and again.json()["system_logout"] == logout
    assert client.post(START, json={"subtask_id": subtask.id}, headers=world.eng_h).status_code == 201  # by hand
    assert client.post(HEARTBEAT, headers=world.eng_h).json().get("system_logout") is None


def test_visits_keep_a_ten_hour_day_alive(client, db, world, subtask):
    session_id = _login(client, world, subtask)
    _rewind(db, session_id, logged_in=timedelta(hours=10), last_seen=timedelta(0), last_visit=timedelta(minutes=40))

    response = client.post(HEARTBEAT, json={"last_active_at": NOON.isoformat()}, headers=world.eng_h)

    assert response.json()["active_session"]["id"] == session_id and response.json()["over_mark"] is True
    db.expire_all()
    session = db.get(models.TimeSession, session_id)
    assert session.last_active_at.replace(tzinfo=UTC) == NOON


def test_a_reported_visit_is_never_in_the_future_nor_before_the_last_one(client, db, world, subtask):
    session_id = _login(client, world, subtask)
    _rewind(db, session_id, logged_in=timedelta(hours=1), last_seen=timedelta(0), last_visit=timedelta(minutes=10))
    ahead = (NOON + timedelta(hours=1)).isoformat()
    client.post(HEARTBEAT, json={"last_active_at": ahead}, headers=world.eng_h)
    db.expire_all()
    clamped = db.get(models.TimeSession, session_id).last_active_at.replace(tzinfo=UTC)
    assert clamped == NOON

    behind = (NOON - timedelta(hours=3)).isoformat()
    client.post(HEARTBEAT, json={"last_active_at": behind}, headers=world.eng_h)
    db.expire_all()
    assert db.get(models.TimeSession, session_id).last_active_at.replace(tzinfo=UTC) == clamped


def test_past_the_mark_a_short_laptop_off_break_pauses_and_resumes(client, db, world, subtask):
    session_id = _login(client, world, subtask)
    _rewind(
        db, session_id, logged_in=timedelta(hours=9), last_seen=timedelta(minutes=10), last_visit=timedelta(minutes=20)
    )

    response = client.post(HEARTBEAT, headers=world.eng_h)  # back after ten minutes

    resumed = response.json()["active_session"]
    assert resumed and resumed["id"] != session_id
    db.expire_all()
    assert db.get(models.TimeSession, session_id).ended_by == LAPTOP_OFF
    assert _banked_hours(db, subtask) == round((9 * 60 - 10) / 60, 2)  # up to the last heartbeat


def test_past_the_mark_a_long_laptop_off_gap_closes_at_the_last_visit_without_resuming(client, db, world, subtask):
    session_id = _login(client, world, subtask)
    _rewind(
        db,
        session_id,
        logged_in=timedelta(hours=11),  # nine hours counted by the time the laptop went off
        last_seen=timedelta(hours=2),
        last_visit=timedelta(hours=2, minutes=10),
    )

    response = client.post(HEARTBEAT, headers=world.eng_h)  # back after two hours

    assert response.json()["active_session"] is None
    assert response.json()["system_logout"]["subtask_id"] == subtask.id
    db.expire_all()
    closed = db.get(models.TimeSession, session_id)
    assert closed.ended_by == NO_VISIT and closed.logout_at == closed.last_active_at
    assert _banked_hours(db, subtask) == round((11 * 60 - 130) / 60, 2)  # up to the last visit


def _sweep(db):
    return TrackingService(db, TrackingRepository(db)).sweep()


def test_the_sweep_pauses_a_silent_session_before_the_mark_and_the_next_heartbeat_resumes_it(
    client, db, world, subtask
):
    session_id = _login(client, world, subtask)
    _rewind(db, session_id, logged_in=timedelta(hours=3), last_seen=timedelta(minutes=6))

    assert _sweep(db) == 1
    paused = db.get(models.TimeSession, session_id)
    assert (paused.status, paused.ended_by) == ("ended", LAPTOP_OFF)
    assert _banked_hours(db, subtask) == round((3 * 60 - 6) / 60, 2)

    resumed = client.post(HEARTBEAT, headers=world.eng_h).json()["active_session"]
    assert resumed and resumed["subtask_id"] == subtask.id and resumed["id"] != session_id


def test_the_sweep_closes_a_session_past_the_mark_whose_browser_never_came_back(client, db, world, subtask):
    session_id = _login(client, world, subtask)
    _rewind(
        db, session_id, logged_in=timedelta(hours=9), last_seen=timedelta(minutes=10), last_visit=timedelta(minutes=20)
    )
    assert _sweep(db) == 0  # a short break so far: nothing to do

    _rewind(
        db, session_id, logged_in=timedelta(hours=9), last_seen=timedelta(minutes=40), last_visit=timedelta(minutes=50)
    )
    assert _sweep(db) == 1

    closed = db.get(models.TimeSession, session_id)
    assert closed.ended_by == NO_VISIT and closed.logout_at == closed.last_active_at
    assert _banked_hours(db, subtask) == round((9 * 60 - 50) / 60, 2)
    assert client.post(HEARTBEAT, headers=world.eng_h).json()["active_session"] is None  # no resume
    row = db.query(models.TimeLogEntry).filter_by(task_id=subtask.id).one()
    assert row.approval_status == "pending_review"  # banked: the lead can review it once the day is over


def test_a_session_left_running_overnight_ends_at_the_mark(client, db, world, subtask):
    """Login 20:00, last visit 22:00, laptop on all night: idle time before 8 h counts (the
    presence model), so the session ends at the mark, 04:00, on the login day's row."""
    session_id = _login(client, world, subtask)
    login_at = _rewind(
        db, session_id, logged_in=timedelta(hours=13), last_seen=timedelta(0), last_visit=timedelta(hours=11)
    )

    response = client.post(HEARTBEAT, headers=world.eng_h)

    assert response.json()["active_session"] is None
    db.expire_all()
    closed = db.get(models.TimeSession, session_id)
    assert closed.ended_by == NO_VISIT and closed.logout_at == login_at + timedelta(hours=8)
    rows = db.query(models.TimeLogEntry).filter_by(task_id=subtask.id).all()
    assert [(r.work_date, r.hours) for r in rows] == [(login_at.date(), 8.0)]


def test_a_pause_with_nothing_to_come_back_to_is_final(client, db, make, world, subtask):
    session_id = _login(client, world, subtask)
    _rewind(db, session_id, logged_in=timedelta(hours=1), last_seen=timedelta(minutes=6))
    _sweep(db)
    node = db.get(models.WbsNode, subtask.id)
    node.assigned_engineer_id = world.emp2.id  # reassigned meanwhile
    db.commit()

    assert client.post(HEARTBEAT, headers=world.eng_h).json()["active_session"] is None
    db.expire_all()
    assert db.get(models.TimeSession, session_id).ended_by == BY_ENGINEER


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


def test_a_pause_is_never_resumed_on_a_later_day(client, db, world, subtask):
    """Monday: 5 h worked, the laptop goes to sleep without a Logout. Tuesday: MAEC is opened.
    Monday closes at its last signal and Tuesday starts from nothing, with a fresh Login."""
    session_id = _login(client, world, subtask)
    login_at = _rewind(db, session_id, logged_in=timedelta(hours=30), last_seen=timedelta(hours=25))

    response = client.post(HEARTBEAT, headers=world.eng_h)

    assert response.json()["active_session"] is None  # yesterday's subtask does not carry on by itself
    db.expire_all()
    monday = db.get(models.TimeSession, session_id)
    assert (monday.status, monday.ended_by) == ("ended", LAPTOP_OFF)
    assert monday.logout_at == login_at + timedelta(hours=5)
    rows = db.query(models.TimeLogEntry).filter_by(task_id=subtask.id).all()
    assert [(r.work_date, r.hours) for r in rows] == [(login_at.date(), 5.0)]
    assert client.post(HEARTBEAT, headers=world.eng_h).json()["active_session"] is None  # nor on a later beat

    tuesday = client.post(START, json={"subtask_id": subtask.id}, headers=world.eng_h)
    assert tuesday.status_code == 201
    assert client.post(HEARTBEAT, headers=world.eng_h).json()["over_mark"] is False  # the day starts at 0


def test_the_sweep_closes_yesterdays_pause_for_good(client, db, world, subtask):
    session_id = _login(client, world, subtask)
    _rewind(db, session_id, logged_in=timedelta(hours=30), last_seen=timedelta(hours=25))

    assert _sweep(db) == 1
    assert client.post(HEARTBEAT, headers=world.eng_h).json()["active_session"] is None
    assert db.query(models.TimeSession).filter_by(status="active").count() == 0


def test_logout_is_a_visit(client, db, world, subtask):
    session_id = _login(client, world, subtask)
    _rewind(db, session_id, logged_in=timedelta(hours=5), last_seen=timedelta(0), last_visit=timedelta(hours=5))

    client.post(LOGOUT, headers=world.eng_h)

    db.expire_all()
    session = db.get(models.TimeSession, session_id)
    assert session.last_active_at == session.logout_at
    assert tracking.unattended_seconds(session) == 0


def test_a_reviewed_day_is_never_changed_by_a_late_session(db, world, governed, caplog):
    project_id, node_a, *_ = governed
    approved = db.query(models.TimeLogEntry).filter_by(task_id=node_a.id, approval_status="approved").one()

    banked = upsert_subtask_time_log(db, project_id, node_a.id, world.emp1.id, approved.work_date, 3600)
    db.commit()

    assert banked is None
    db.refresh(approved)
    assert (approved.hours, approved.approval_status) == (30, "approved")
    assert "Hours for a reviewed day were not banked" in caplog.text


def test_logging_in_to_another_subtask_is_a_switch_the_engineer_confirms(client, db, make, world, governed, subtask):
    project_id, node_a, *_ = governed
    other = make.wbs_node(project_id, world.lead_e, engineer=world.emp1, parent_id=node_a.id, estimated_hours=4)
    first = _login(client, world, subtask)
    _rewind(db, first, logged_in=timedelta(hours=2), last_seen=timedelta(0))

    refused = client.post(START, json={"subtask_id": other.id}, headers=world.eng_h)
    assert refused.status_code == 409 and subtask.task_name in refused.json()["detail"]  # names what is running
    assert client.post(HEARTBEAT, headers=world.eng_h).json()["active_session"]["id"] == first

    switched = client.post(START, json={"subtask_id": other.id, "switch": True}, headers=world.eng_h)

    assert switched.status_code == 201, switched.text
    active = switched.json()["active_session"]
    assert (active["subtask_id"], active["subtask_name"]) == (other.id, f"{other.wbs_code} {other.task_name}")
    db.expire_all()
    ended = db.get(models.TimeSession, first)
    assert (ended.status, ended.ended_by) == ("ended", BY_ENGINEER)
    assert ended.logout_at.replace(tzinfo=UTC) == NOON  # the same moment the new session starts
    assert _banked_hours(db, subtask) == 2.0  # the first subtask keeps exactly its two hours
    assert db.query(models.TimeSession).filter_by(status="active").count() == 1


def test_a_switch_that_cannot_happen_leaves_the_running_session_alone(client, db, make, world, governed, subtask):
    project_id, node_a, *_ = governed
    someone_elses = make.wbs_node(project_id, world.lead_e, engineer=world.emp2, parent_id=node_a.id)
    first = _login(client, world, subtask)

    refused = client.post(START, json={"subtask_id": someone_elses.id, "switch": True}, headers=world.eng_h)

    assert refused.status_code == 403
    assert client.post(HEARTBEAT, headers=world.eng_h).json()["active_session"]["id"] == first


def test_coming_back_after_a_long_gap_past_the_mark_is_not_a_visit_that_saves_the_session(client, db, world, subtask):
    """The browser reports "last visit: now" with the very heartbeat that brings the engineer
    back. That visit must not excuse the two hours before it."""
    session_id = _login(client, world, subtask)
    _rewind(
        db,
        session_id,
        logged_in=timedelta(hours=11),
        last_seen=timedelta(hours=2),
        last_visit=timedelta(hours=2, minutes=10),
    )

    response = client.post(HEARTBEAT, json={"last_active_at": NOON.isoformat()}, headers=world.eng_h)

    assert response.json()["active_session"] is None  # closed, and not resumed
    db.expire_all()
    closed = db.get(models.TimeSession, session_id)
    assert closed.ended_by == NO_VISIT and closed.logout_at == closed.last_active_at
    assert closed.last_active_at.replace(tzinfo=UTC) == NOON - timedelta(hours=2, minutes=10)


def test_login_reports_at_once_that_the_day_is_past_the_mark(client, db, world, subtask):
    earlier = _login(client, world, subtask)
    _rewind(db, earlier, logged_in=timedelta(hours=9), last_seen=timedelta(0))
    _banked_today(db, earlier, 8.5)

    response = client.post(START, json={"subtask_id": subtask.id}, headers=world.eng_h)

    assert response.status_code == 201 and response.json()["over_mark"] is True  # no waiting for a heartbeat


ADVANCE = "/api/wbs-nodes/{}/advance-status"


def _advance(client, headers, node, *statuses):
    for status in statuses:
        response = client.post(ADVANCE.format(node.id), json={"new_status": status}, headers=headers)
        assert response.status_code == 200, response.text


def test_setting_a_subtask_done_logs_the_engineer_out_and_banks_the_time(client, db, world, subtask):
    session_id = _login(client, world, subtask)
    _rewind(db, session_id, logged_in=timedelta(hours=2), last_seen=timedelta(minutes=1))

    _advance(client, world.eng_h, subtask, "Done")  # Login already moved it to In-Progress

    db.expire_all()
    session = db.get(models.TimeSession, session_id)
    assert (session.status, session.ended_by) == ("ended", tracking.SUBTASK_DONE)
    assert _banked_hours(db, subtask) == 2.0  # every minute until Done counts
    assert client.post(HEARTBEAT, headers=world.eng_h).json()["active_session"] is None


def test_a_done_subtask_refuses_login_until_a_lead_reopens_it(client, db, world, subtask):
    _advance(client, world.eng_h, subtask, "In-Progress", "Done")

    refused = client.post(START, json={"subtask_id": subtask.id}, headers=world.eng_h)

    assert refused.status_code == 409
    assert refused.json()["detail"] == tracking.SUBTASK_IS_DONE

    db.get(models.WbsNode, subtask.id).deliverable_status = "In-Progress"  # a lead moved it back
    db.commit()
    _login(client, world, subtask)


def test_a_lead_editing_a_subtask_to_done_logs_the_engineer_out(client, db, world, subtask):
    session_id = _login(client, world, subtask)
    edit = {
        "task_name": subtask.task_name,
        "parent_id": subtask.parent_id,
        "assigned_engineer_id": subtask.assigned_engineer_id,
        "estimated_hours": subtask.estimated_hours,
        "start_date": subtask.start_date.isoformat(),  # the plan unchanged: it is In-Progress
        "target_due_date": subtask.target_due_date.isoformat(),
        "deliverable_status": "Done",
    }

    response = client.put(f"/api/wbs-nodes/{subtask.id}", json=edit, headers=world.lead_h)

    assert response.status_code == 200, response.text
    db.expire_all()
    assert db.get(models.TimeSession, session_id).ended_by == tracking.SUBTASK_DONE


# -- starting work is one step (decided 2026-10-08) --------------------------------------------


def _status(db, node):
    db.expire_all()
    return db.get(models.WbsNode, node.id).deliverable_status


def test_login_on_a_to_do_subtask_moves_it_to_in_progress(client, db, world, subtask):
    _login(client, world, subtask)

    assert _status(db, subtask) == "In-Progress"
    history = db.query(models.WbsNodeHistory).filter_by(node_id=subtask.id).all()
    assert [(h.old_status, h.new_status, h.comment) for h in history] == [
        ("To Do", "In-Progress", tracking.STARTED_WITH_LOGIN)
    ]
    assert db.get(models.WbsNode, subtask.id).actual_start_datetime is not None


def test_login_leaves_a_started_subtask_as_it_is(client, db, world, subtask):
    db.get(models.WbsNode, subtask.id).deliverable_status = "In-Progress"
    db.commit()

    _login(client, world, subtask)

    assert _status(db, subtask) == "In-Progress"
    assert db.query(models.WbsNodeHistory).filter_by(node_id=subtask.id).count() == 0


def test_moving_your_to_do_subtask_to_in_progress_logs_you_in(client, db, world, subtask):
    response = client.post(ADVANCE.format(subtask.id), json={"new_status": "In-Progress"}, headers=world.eng_h)

    assert response.status_code == 200 and response.json()["tracking_started"] is True
    running = client.post(HEARTBEAT, headers=world.eng_h).json()["active_session"]
    assert running["subtask_id"] == subtask.id


def test_in_progress_never_logs_in_someone_else_or_switches_a_running_session(
    client, db, make, world, governed, subtask
):
    project_id, node_a, *_ = governed
    other = make.wbs_node(project_id, world.lead_e, engineer=world.emp1, parent_id=node_a.id, estimated_hours=4)
    _login(client, world, subtask)  # logged in elsewhere already

    mine = client.post(ADVANCE.format(other.id), json={"new_status": "In-Progress"}, headers=world.eng_h).json()
    assert mine["tracking_started"] is False  # switching stays the engineer's confirmed choice
    assert client.post(HEARTBEAT, headers=world.eng_h).json()["active_session"]["subtask_id"] == subtask.id

    by_lead = make.wbs_node(project_id, world.lead_e, engineer=world.emp1, parent_id=node_a.id, estimated_hours=4)
    moved = client.post(ADVANCE.format(by_lead.id), json={"new_status": "In-Progress"}, headers=world.lead_h).json()
    assert moved["tracking_started"] is False  # a lead moving the engineer's subtask logs nobody in


# -- started work keeps its plan (decided 2026-10-08) ------------------------------------------


def _edit(subtask, **changes):
    return {
        "task_name": subtask.task_name,
        "parent_id": subtask.parent_id,
        "assigned_engineer_id": subtask.assigned_engineer_id,
        "estimated_hours": subtask.estimated_hours,
        "start_date": subtask.start_date.isoformat(),
        "target_due_date": subtask.target_due_date.isoformat(),
        "deliverable_status": subtask.deliverable_status,
        **changes,
    }


def test_a_started_subtask_keeps_its_engineer_hours_and_dates(client, db, world, subtask):
    _login(client, world, subtask)  # now In-Progress
    db.refresh(subtask)

    for change in ({"assigned_engineer_id": world.emp2.id}, {"estimated_hours": 6}, {"start_date": "2026-09-02"}):
        refused = client.put(f"/api/wbs-nodes/{subtask.id}", json=_edit(subtask, **change), headers=world.lead_h)
        assert refused.status_code == 409, change
        assert "Move it back to To Do first" in refused.json()["detail"]

    renamed = client.put(
        f"/api/wbs-nodes/{subtask.id}", json=_edit(subtask, task_name="Risers, level 2"), headers=world.lead_h
    )
    assert renamed.status_code == 200, renamed.text  # the name is not the plan


def test_moving_it_back_to_to_do_frees_the_plan(client, db, world, subtask):
    db.get(models.WbsNode, subtask.id).deliverable_status = "In-Progress"
    db.commit()
    db.refresh(subtask)

    back = client.put(
        f"/api/wbs-nodes/{subtask.id}", json=_edit(subtask, deliverable_status="To Do"), headers=world.lead_h
    )
    assert back.status_code == 200, back.text
    db.refresh(subtask)
    changed = client.put(f"/api/wbs-nodes/{subtask.id}", json=_edit(subtask, estimated_hours=6), headers=world.lead_h)
    assert changed.status_code == 200, changed.text
