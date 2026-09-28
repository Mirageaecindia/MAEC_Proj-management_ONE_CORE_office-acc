"""Hours are approved per day, by the task's lead, else the BU Head (app/services/hours_review.py).

Scenario: Arjun works on two tasks of one project, one under the Electrical
lead (Anita) and one under the Mechanical lead (Priya), 8 h each on one day
last week.
"""

from datetime import date, timedelta

import pytest
from test_project_roles import _approve_booking

import models
from app.repositories.work import WorkRepository
from app.services.tracking import upsert_subtask_time_log
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
    assert first.json() == {"reviewed": 1, "action": "approved"}
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
    today = make.time_entry(project_id, db.get(models.WbsNode, row_e.task_id), world.emp1, 3, day=date.today())

    refused = _row(client, world.lead_h, today.id)

    assert refused.status_code == 409 and "once it is over" in refused.json()["detail"]
    this_week = date.today() - timedelta(days=date.today().weekday())
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


def test_more_hours_on_a_reviewed_day_need_review_again(client, db, world, split):
    project_id, row_e, row_m = split
    assert _row(client, world.lead_h, row_e.id).status_code == 200

    db.expire_all()  # the approval happened through the API
    upsert_subtask_time_log(db, project_id, row_e.task_id, world.emp1.id, DAY, 3600)  # a session crossing midnight
    db.commit()

    assert _status(db, row_e) == "pending_review"  # never counted as approved without a review
    assert db.get(models.TimeLogEntry, row_e.id).hours == 9.0
    assert WorkRepository(db).approved_hours(project_id) == 0.0


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
