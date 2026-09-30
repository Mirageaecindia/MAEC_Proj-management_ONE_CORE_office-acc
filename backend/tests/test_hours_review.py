"""Hours are approved per day, by the task's lead, else the BU Head (app/services/hours_review.py).

Scenario: Arjun works on two tasks of one project, one under the Electrical
lead (Anita) and one under the Mechanical lead (Priya), 8 h each on one day
last week.
"""

from datetime import UTC, date, datetime, time, timedelta

import pytest
from test_project_roles import _approve_booking

import models
from app.domain.timesheets import today_utc
from app.repositories.work import WorkRepository
from factories import PASSWORD, WEEK

DAY = WEEK  # a Monday in the past
WEEK_BODY = {"week_start_date": WEEK.isoformat()}


@pytest.fixture
def split(client, db, make, world):
    project_id = world.create_project()["id"]
    _approve_booking(client, world, project_id, world.emp1, world.lead_h)
    task_e = make.wbs_node(project_id, world.lead_e, engineer=world.emp1)
    task_m = make.wbs_node(project_id, world.lead_m, engineer=world.emp1)
    row_e = make.time_entry(project_id, task_e, world.emp1, 8, day=DAY)
    row_m = make.time_entry(project_id, task_m, world.emp1, 8, day=DAY)
    return project_id, row_e, row_m


def _headers(client, username):
    token = client.post("/api/auth/login", json={"username": username, "password": PASSWORD}).json()["token"]
    return {"Authorization": f"Bearer {token}"}


def _bulk(client, headers, project_id, action="approved", employee_id=None):
    body = {**WEEK_BODY, "action": action, "employee_id": employee_id}
    return client.post(f"/api/projects/{project_id}/hours/review", json=body, headers=headers)


def _row(client, headers, row_id, action="approve", reason=None):
    return client.post(f"/api/time-log-entries/{row_id}/{action}", json={"reason": reason}, headers=headers)


def _status(db, row):
    db.expire_all()
    return db.get(models.TimeLogEntry, row.id).approval_status


def _timesheet(client, headers, project_id):
    return client.get(f"/api/projects/{project_id}/timesheet?week_start={WEEK}", headers=headers).json()


def test_each_lead_approves_the_days_on_their_own_tasks(client, db, world, split):
    project_id, row_e, row_m = split
    mine = {row["task_id"]: row["can_review"] for row in _timesheet(client, world.lead_h, project_id)}
    assert mine == {row_e.task_id: True}  # Anita sees only her task's rows, and may review them

    first = _bulk(client, world.lead_h, project_id, employee_id=world.emp1.id)

    assert first.status_code == 200, first.text
    assert first.json() == {"reviewed": 1, "skipped_over_mark": 0, "skipped_unattended": 0, "action": "approved"}
    assert (_status(db, row_e), _status(db, row_m)) == ("approved", "pending_review")
    assert WorkRepository(db).approved_hours(project_id) == 8.0  # usage counts each day as it is approved
    assert _bulk(client, world.lead_h, project_id).status_code == 409  # nothing of hers left
    assert _bulk(client, world.other_lead_h, project_id).status_code == 403  # not a lead of it

    assert _bulk(client, _headers(client, "lead.m"), project_id).status_code == 200  # all pending on my tasks
    assert WorkRepository(db).approved_hours(project_id) == 16.0


def test_a_single_day_is_approved_only_by_its_reviewer(client, db, world, split):
    project_id, row_e, row_m = split

    assert _row(client, world.bu_h, row_e.id).status_code == 403  # the task has an active lead
    assert _row(client, world.lead_h, row_m.id).status_code == 403  # Priya's task, not Anita's
    assert _row(client, world.lead_h, row_e.id).status_code == 200


def test_hours_without_an_active_lead_go_to_the_bu_head(client, db, make, world, split):
    project_id, row_e, _ = split
    orphan_task = make.wbs_node(
        project_id, world.lead_e, engineer=world.emp1, assigned_lead=None, assigned_lead_user_id=None
    )
    orphan = make.time_entry(project_id, orphan_task, world.emp1, 4, day=DAY + timedelta(days=1))

    assert _row(client, world.lead_h, orphan.id).status_code == 403
    assert _row(client, world.bu_h, orphan.id).status_code == 200
    # Anita's lead period ends: her task's hours fall back to the BU Head, so none are stranded.
    anita_booking = (
        db.query(models.ResourceBooking)
        .filter_by(project_id=project_id, employee_id=world.lead_e.employee_id, role="lead")
        .one()
    )
    anita_booking.end_date = date.today() - timedelta(days=1)
    db.commit()
    assert _row(client, world.lead_h, row_e.id).status_code == 403
    assert _row(client, world.bu_h, row_e.id).status_code == 200


def test_only_a_finished_day_is_reviewed(client, db, make, world, split):
    project_id, row_e, _ = split
    today = make.time_entry(project_id, db.get(models.WbsNode, row_e.task_id), world.emp1, 3, day=today_utc())

    refused = _row(client, world.lead_h, today.id)

    assert refused.status_code == 409 and "once it is over" in refused.json()["detail"]
    this_week = today_utc() - timedelta(days=today_utc().weekday())
    rows = client.get(f"/api/projects/{project_id}/timesheet?week_start={this_week}", headers=world.lead_h).json()
    assert next(r for r in rows if r["id"] == today.id)["can_review"] is False
    assert _bulk(client, world.lead_h, project_id, employee_id=world.emp1.id).json()["reviewed"] == 1  # today skipped


def test_review_transitions(client, db, world, split):
    project_id, row_e, row_m = split
    assert _row(client, world.lead_h, row_e.id).status_code == 200  # pending -> approved
    assert _row(client, world.lead_h, row_e.id).status_code == 409  # already approved

    taken_back = _row(client, world.lead_h, row_e.id, "reject")
    assert taken_back.status_code == 400  # approved -> rejected needs a reason
    taken_back = _row(client, world.lead_h, row_e.id, "reject", reason="Wrong subtask")
    assert taken_back.status_code == 200
    assert taken_back.json()["review_reason"] == "Wrong subtask"
    audit = db.query(models.GovernanceAction).filter_by(project_id=project_id, action="hours_unapproved").one()
    assert "8 h on" in audit.comments and "Wrong subtask" in audit.comments and audit.created_by == "Anita Kumar"
    dashboard = client.get(f"/api/projects/{project_id}/executive-dashboard", headers=world.bu_h).json()
    assert any(a["action"] == "hours_unapproved" for a in dashboard["governance_actions"])  # the BU Head sees it

    assert _row(client, world.lead_h, row_e.id).status_code == 409  # rejected -> approved: never
    assert WorkRepository(db).approved_hours(project_id) == 0.0


def test_the_bu_head_is_blocked_by_the_lock_like_the_leads(client, db, make, world):
    project_id = world.create_project()["id"]
    anita = db.get(models.Employee, world.lead_e.employee_id)
    own_row = make.time_entry(project_id, make.wbs_node(project_id, world.lead_e, engineer=anita), anita, 8, day=DAY)
    db.get(models.Project, project_id).timesheets_soft_locked = True
    db.commit()

    bulk = _bulk(client, world.bu_h, project_id, employee_id=anita.id)
    row = _row(client, world.bu_h, own_row.id)

    assert (bulk.status_code, row.status_code) == (409, 409)
    assert _status(db, own_row) == "pending_review"


def _session(make, row, *, login, logout=None, last_visit=None, ended_by=None):
    """A Login/Logout session behind a day's row (times are hours into the row's day, UTC)."""
    at = lambda hour: datetime.combine(row.work_date, time.min, tzinfo=UTC) + timedelta(hours=hour)  # noqa: E731
    return make._save(
        models.TimeSession(
            project_id=row.project_id,
            task_id=row.task_id,
            subtask_id=row.task_id,
            employee_id=row.employee_id,
            login_at=at(login),
            last_seen_at=at(logout if logout is not None else login),
            last_active_at=at(last_visit if last_visit is not None else login),
            logout_at=at(logout) if logout is not None else None,
            active_seconds=int((logout - login) * 3600) if logout is not None else 0,
            status="ended" if logout is not None else "active",
            ended_by=ended_by,
        )
    )


def test_a_day_is_not_reviewed_while_a_session_started_on_it_is_open(client, db, make, world, split):
    project_id, row_e, _ = split
    running = _session(make, row_e, login=20)  # still running overnight
    anita = _headers(client, "lead.e")

    refused = _row(client, anita, row_e.id)
    assert refused.status_code == 409 and "still logged in" in refused.json()["detail"]
    assert _bulk(client, anita, project_id).status_code == 409
    listed = client.get(f"/api/projects/{project_id}/timesheet?week_start={WEEK.isoformat()}", headers=anita).json()
    assert {row["id"]: (row["finished"], row["can_review"]) for row in listed}[row_e.id] == (False, False)

    running.status, running.logout_at = "ended", running.login_at + timedelta(hours=2)
    db.commit()
    assert _row(client, anita, row_e.id).status_code == 200


def test_the_row_shows_its_sessions_and_flags_an_unattended_one(client, db, make, world, split):
    project_id, row_e, row_m = split
    _session(make, row_e, login=9, logout=17, last_visit=17, ended_by="engineer")  # logged out by hand
    _session(make, row_m, login=9, logout=17, last_visit=11, ended_by="laptop_off")  # six hours after the last visit

    listed = client.get(f"/api/projects/{project_id}/timesheet?week_start={WEEK.isoformat()}", headers=world.bu_h)
    rows = {row["id"]: row for row in listed.json()}

    attended, unattended = rows[row_e.id], rows[row_m.id]
    assert (attended["unattended"], attended["attended_hours"]) == (False, None)
    assert (unattended["unattended"], unattended["attended_hours"]) == (True, 2.0)
    (session,) = unattended["sessions"]
    assert session["ended_by"] == "laptop_off" and session["unattended"] is True
    assert [session[key][11:16] for key in ("login_at", "logout_at", "last_visit_at")] == ["09:00", "17:00", "11:00"]


def test_approve_up_to_the_last_visit_keeps_the_rest_as_trimmed_hours(client, db, make, world, split):
    project_id, row_e, row_m = split
    _session(make, row_m, login=9, logout=17, last_visit=11, ended_by="laptop_off")
    priya = _headers(client, "lead.m")

    assert client.post(f"/api/time-log-entries/{row_m.id}/approve-attended", headers=world.lead_h).status_code == 403
    response = client.post(f"/api/time-log-entries/{row_m.id}/approve-attended", headers=priya)

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["hours"], body["trimmed_hours"], body["approval_status"]) == (2.0, 6.0, "approved")
    assert (body["unattended"], body["attended_hours"]) == (False, None)  # decided: no longer flagged
    assert "2 of 8 h; 6 h unattended not approved" in body["review_reason"]
    assert WorkRepository(db).approved_hours(project_id) == 2.0  # only the attended hours count
    audit = db.query(models.GovernanceAction).filter_by(project_id=project_id, action="hours_partly_approved").one()
    assert "6 h unattended not approved" in audit.comments and audit.created_by == "Priya Nair"

    # A day with nothing unattended is approved or rejected as a whole.
    whole = client.post(f"/api/time-log-entries/{row_e.id}/approve-attended", headers=_headers(client, "lead.e"))
    assert whole.status_code == 400 and "as a whole" in whole.json()["detail"]


def test_a_day_with_no_attended_time_is_rejected_not_partly_approved(client, db, make, world, split):
    _, _, row_m = split
    _session(make, row_m, login=9, logout=17, last_visit=9, ended_by="laptop_off")

    response = client.post(f"/api/time-log-entries/{row_m.id}/approve-attended", headers=_headers(client, "lead.m"))

    assert response.status_code == 400 and "reject it instead" in response.json()["detail"]
    assert _status(db, row_m) == "pending_review"


def test_the_bu_head_approves_a_task_its_lead_worked_on(client, db, make, world):
    project_id = world.create_project()["id"]
    anita = db.get(models.Employee, world.lead_e.employee_id)
    task = make.wbs_node(project_id, world.lead_e, engineer=world.emp1, deliverable_status="Submitted for Approval")
    make.wbs_node(project_id, world.lead_e, engineer=world.emp1, parent_id=task.id, deliverable_status="Done")
    make.wbs_node(project_id, world.lead_e, engineer=anita, parent_id=task.id, deliverable_status="Done")  # one of them
    url = f"/api/wbs-nodes/{task.id}/approve"

    assert client.post(url, json={"new_status": "Approved"}, headers=world.lead_h).status_code == 403
    assert client.post(url, json={"new_status": "Approved"}, headers=world.bu_h).status_code == 200

    untouched = make.wbs_node(
        project_id, world.lead_e, engineer=world.emp1, deliverable_status="Submitted for Approval"
    )
    url = f"/api/wbs-nodes/{untouched.id}/approve"
    assert client.post(url, json={"new_status": "Approved"}, headers=world.bu_h).status_code == 403
    assert client.post(url, json={"new_status": "Approved"}, headers=world.lead_h).status_code == 200


def test_bulk_approval_skips_days_over_eight_hours(client, db, make, world, split):
    project_id, row_e, _ = split
    row_e.hours = 9.5  # overtime: pay-relevant, decided one day at a time
    db.commit()
    anita = _headers(client, "lead.e")

    response = _bulk(client, anita, project_id)

    assert response.status_code == 409 and "day by day" in response.json()["detail"]
    db.refresh(row_e)
    assert row_e.approval_status == "pending_review"
    assert client.post(f"/api/time-log-entries/{row_e.id}/approve", headers=anita).status_code == 200


def test_bulk_approval_reports_the_over_eight_days_it_left_alone(client, db, make, world, split):
    project_id, row_e, _ = split
    task = db.get(models.WbsNode, row_e.task_id)
    normal = make.time_entry(project_id, task, world.emp1, 6, day=DAY + timedelta(days=1))
    row_e.hours = 9.5
    db.commit()

    response = _bulk(client, _headers(client, "lead.e"), project_id)

    assert response.status_code == 200, response.text
    assert response.json() == {"reviewed": 1, "skipped_over_mark": 1, "skipped_unattended": 0, "action": "approved"}
    db.refresh(normal)
    db.refresh(row_e)
    assert (normal.approval_status, row_e.approval_status) == ("approved", "pending_review")


def test_bulk_approval_skips_unattended_days_and_reports_them(client, db, make, world, split):
    project_id, row_e, _ = split
    task = db.get(models.WbsNode, row_e.task_id)
    normal = make.time_entry(project_id, task, world.emp1, 6, day=DAY + timedelta(days=1))
    _session(make, row_e, login=9, logout=17, last_visit=11, ended_by="laptop_off")  # flagged: someone must look
    anita = _headers(client, "lead.e")

    response = _bulk(client, anita, project_id)

    assert response.status_code == 200, response.text
    assert response.json() == {"reviewed": 1, "skipped_over_mark": 0, "skipped_unattended": 1, "action": "approved"}
    assert (_status(db, normal), _status(db, row_e)) == ("approved", "pending_review")
    again = _bulk(client, anita, project_id)  # only the flagged day is left
    assert again.status_code == 409 and "day by day" in again.json()["detail"]


def test_every_rejection_needs_a_reason(client, db, world, split):
    project_id, row_e, _ = split
    anita = _headers(client, "lead.e")

    assert _row(client, anita, row_e.id, "reject").status_code == 400  # a pending day too
    assert _row(client, anita, row_e.id, "reject", reason="   ").status_code == 400
    assert _bulk(client, anita, project_id, action="rejected").status_code == 400
    assert _status(db, row_e) == "pending_review"

    rejected = _row(client, anita, row_e.id, "reject", reason="No drawings issued that day")
    assert rejected.status_code == 200 and rejected.json()["review_reason"] == "No drawings issued that day"


def test_sessions_under_a_minute_are_not_listed_and_times_carry_their_utc_offset(client, db, make, world, split):
    project_id, row_e, _ = split
    _session(make, row_e, login=9, logout=17, last_visit=17, ended_by="engineer")
    _session(make, row_e, login=17, logout=17.005, last_visit=17, ended_by="engineer")  # 18 seconds: a mis-click

    listed = client.get(f"/api/projects/{project_id}/timesheet?week_start={WEEK.isoformat()}", headers=world.bu_h)
    (row,) = [r for r in listed.json() if r["id"] == row_e.id]

    assert len(row["sessions"]) == 1
    for key in ("login_at", "logout_at", "last_visit_at"):
        assert row["sessions"][0][key].endswith(("+00:00", "Z")), row["sessions"][0][key]  # never read as local time
