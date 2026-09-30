"""Corrections: hours logged on the wrong subtask (app/services/corrections.py, TODO H2).

The engineer proposes moving hours of one day between their own subtasks of a
project; the target task's reviewer decides; the day's total never changes.

Scenario: Arjun has three subtasks on one project. X and Z are under the
Electrical lead (Anita), Y under the Mechanical lead (Priya). He logged 8 h on
X last Monday, some of which belonged to Y.
"""

from datetime import timedelta
from types import SimpleNamespace

import pytest
from test_project_roles import _approve_booking

import models
from app.domain.timesheets import total_hours
from app.repositories.work import WorkRepository
from factories import PASSWORD, WEEK

DAY = WEEK  # a Monday in the past


def _headers(client, username):
    token = client.post("/api/auth/login", json={"username": username, "password": PASSWORD}).json()["token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def work(client, db, make, world):
    project_id = world.create_project()["id"]
    _approve_booking(client, world, project_id, world.emp1, world.lead_h)
    task_e = make.wbs_node(project_id, world.lead_e, engineer=world.emp1)
    task_m = make.wbs_node(project_id, world.lead_m, engineer=world.emp1)
    sub = lambda task, lead: make.wbs_node(  # noqa: E731
        project_id, lead, engineer=world.emp1, parent_id=task.id, estimated_hours=8
    )
    x, z, y = sub(task_e, world.lead_e), sub(task_e, world.lead_e), sub(task_m, world.lead_m)
    row_x = make.time_entry(project_id, x, world.emp1, 8, day=DAY)
    return SimpleNamespace(
        project_id=project_id,
        x=x,
        y=y,
        z=z,
        row_x=row_x,
        employee_id=world.emp1.id,
        anita=_headers(client, "lead.e"),
        priya=_headers(client, "lead.m"),
    )


def _propose(client, headers, work, *, hours=3, source=None, target=None, day=DAY, note=None):
    body = {
        "work_date": day.isoformat(),
        "from_task_id": (source or work.x).id,
        "to_task_id": (target or work.y).id,
        "hours": hours,
        "note": note,
    }
    return client.post(f"/api/projects/{work.project_id}/hours-corrections", json=body, headers=headers)


def _decide(client, headers, correction_id, action="approve", reason=None):
    return client.post(f"/api/hours-corrections/{correction_id}/{action}", json={"reason": reason}, headers=headers)


def _rows(db, work):
    db.expire_all()
    rows = db.query(models.TimeLogEntry).filter_by(project_id=work.project_id, employee_id=work.employee_id)
    return {row.task_id: (row.hours, row.approval_status) for row in rows}


def _day_total(db, work):
    db.expire_all()
    return total_hours(db.query(models.TimeLogEntry).filter_by(project_id=work.project_id, work_date=DAY))


def test_a_correction_moves_hours_and_never_changes_the_total(client, db, world, work):
    before = _day_total(db, work)

    proposed = _propose(client, world.eng_h, work, note="Switched to Y at 14:00, forgot to switch the session")
    assert proposed.status_code == 201, proposed.text
    correction = proposed.json()
    assert (correction["status"], correction["hours"], correction["can_cancel"]) == ("pending", 3, True)
    assert (correction["source_status"], correction["can_decide"]) == ("pending_review", False)
    assert _rows(db, work) == {work.x.id: (8, "pending_review")}  # nothing moves until it is decided

    decided = _decide(client, work.priya, correction["id"])  # the lead of the task the hours move to

    assert decided.status_code == 200, decided.text
    assert (decided.json()["status"], decided.json()["decided_by"]) == ("approved", "Priya Nair")
    assert _rows(db, work) == {work.x.id: (5, "pending_review"), work.y.id: (3, "pending_review")}
    assert _day_total(db, work) == before == 8


def test_only_the_target_tasks_reviewer_decides(client, db, world, work):
    correction_id = _propose(client, world.eng_h, work).json()["id"]

    assert _decide(client, work.anita, correction_id).status_code == 403  # leads the source task, not the target
    assert _decide(client, world.bu_h, correction_id).status_code == 403  # the target has an active lead
    assert _decide(client, world.eng_h, correction_id).status_code == 403
    listed = client.get(f"/api/projects/{work.project_id}/hours-corrections", headers=work.priya).json()
    assert [(c["id"], c["can_decide"]) for c in listed] == [(correction_id, True)]
    assert _decide(client, work.priya, correction_id, action="reject", reason="Both were X").status_code == 200
    assert _rows(db, work) == {work.x.id: (8, "pending_review")}  # a rejected correction moves nothing
    assert _decide(client, work.priya, correction_id).status_code == 409  # already decided


def test_a_lead_who_works_on_their_own_task_is_decided_by_the_bu_head(client, db, make, world):
    """Anita leads the project and does two subtasks herself: nobody approves their own correction."""
    project_id = world.create_project()["id"]
    anita_employee = db.get(models.Employee, world.lead_e.employee_id)
    task = make.wbs_node(project_id, world.lead_e, engineer=anita_employee)
    x = make.wbs_node(project_id, world.lead_e, engineer=anita_employee, parent_id=task.id, estimated_hours=8)
    y = make.wbs_node(project_id, world.lead_e, engineer=anita_employee, parent_id=task.id, estimated_hours=8)
    make.time_entry(project_id, x, anita_employee, 6, day=DAY)
    body = {"work_date": DAY.isoformat(), "from_task_id": x.id, "to_task_id": y.id, "hours": 2}

    proposed = client.post(f"/api/projects/{project_id}/hours-corrections", json=body, headers=world.lead_h)

    assert proposed.status_code == 201, proposed.text
    assert proposed.json()["can_decide"] is False  # she leads the target task, but these are her own hours
    correction_id = proposed.json()["id"]
    assert _decide(client, world.lead_h, correction_id).status_code == 403
    for_bu_head = client.get(f"/api/projects/{project_id}/hours-corrections", headers=world.bu_h).json()
    assert [(c["id"], c["can_decide"]) for c in for_bu_head] == [(correction_id, True)]
    assert _decide(client, world.bu_h, correction_id).status_code == 200
    db.expire_all()
    rows = db.query(models.TimeLogEntry).filter_by(project_id=project_id, employee_id=anita_employee.id)
    assert {row.task_id: row.hours for row in rows} == {x.id: 4, y.id: 2}


def test_only_pending_or_rejected_hours_move(client, db, world, work):
    assert client.post(f"/api/time-log-entries/{work.row_x.id}/approve", headers=work.anita).status_code == 200
    approved = _propose(client, world.eng_h, work)
    assert approved.status_code == 409 and "Approved hours can't be moved" in approved.json()["detail"]

    taken_back = client.post(
        f"/api/time-log-entries/{work.row_x.id}/reject", json={"reason": "Wrong subtask"}, headers=work.anita
    )
    assert taken_back.status_code == 200
    correction = _propose(client, world.eng_h, work, hours=8).json()  # rejected hours are corrected, all of them
    assert (correction["source_status"], correction["source_review_reason"]) == ("rejected", "Wrong subtask")

    assert _decide(client, work.priya, correction["id"]).status_code == 200
    assert _rows(db, work) == {work.y.id: (8, "pending_review")}  # the emptied source row is gone; 8 h stand on Y
    assert _day_total(db, work) == 8


def test_hours_moved_into_an_approved_day_count_at_once(client, db, make, world, work):
    row_y = make.time_entry(work.project_id, work.y, world.emp1, 2, day=DAY)
    assert client.post(f"/api/time-log-entries/{row_y.id}/approve", headers=work.priya).status_code == 200
    correction_id = _propose(client, world.eng_h, work).json()["id"]

    assert _decide(client, work.priya, correction_id).status_code == 200  # she accepts them into her approved day

    assert _rows(db, work) == {work.x.id: (5, "pending_review"), work.y.id: (5, "approved")}
    assert WorkRepository(db).approved_hours(work.project_id) == 5


def test_a_proposal_is_refused_when_it_cannot_be_right(client, db, make, world, work):
    other = make.wbs_node(work.project_id, world.lead_e, engineer=world.emp2, parent_id=work.x.parent_id)
    elsewhere = make.wbs_node(world.create_project()["id"], world.lead_e, engineer=world.emp1, parent_id=1)

    assert _propose(client, world.eng_h, work, hours=8.5).status_code == 400  # more than the row has
    assert _propose(client, world.eng_h, work, hours=0).status_code == 422
    assert _propose(client, world.eng_h, work, target=work.x).status_code == 400  # the same subtask
    assert _propose(client, world.eng_h, work, target=other).status_code == 403  # someone else's subtask
    assert _propose(client, world.eng_h, work, target=elsewhere).status_code == 403  # another project
    assert _propose(client, world.eng_h, work, source=work.z).status_code == 404  # no hours there that day
    assert _propose(client, world.eng_h, work, day=DAY + timedelta(days=1)).status_code == 404
    assert _propose(client, work.anita, work).status_code == 403  # not her subtasks, not her hours
    assert _propose(client, world.bu_h, work).status_code == 403

    assert _propose(client, world.eng_h, work).status_code == 201
    again = _propose(client, world.eng_h, work, target=work.z)
    assert again.status_code == 409 and "already waiting" in again.json()["detail"]


def test_a_day_with_a_pending_correction_is_not_approved_until_it_is_decided(client, db, world, work):
    correction_id = _propose(client, world.eng_h, work).json()["id"]
    week = {"week_start_date": WEEK.isoformat(), "action": "approved"}

    single = client.post(f"/api/time-log-entries/{work.row_x.id}/approve", headers=work.anita)
    assert single.status_code == 409 and "correction" in single.json()["detail"]
    assert (
        client.post(f"/api/projects/{work.project_id}/hours/review", json=week, headers=work.anita).status_code == 409
    )
    listed = client.get(f"/api/projects/{work.project_id}/timesheet?week_start={WEEK.isoformat()}", headers=world.eng_h)
    (row,) = listed.json()
    assert (row["correction_pending"], row["can_correct"]) == (True, False)

    assert _decide(client, work.priya, correction_id).status_code == 200
    assert client.post(f"/api/time-log-entries/{work.row_x.id}/approve", headers=work.anita).status_code == 200
    assert _rows(db, work) == {work.x.id: (5, "approved"), work.y.id: (3, "pending_review")}


def test_the_engineer_withdraws_their_own_correction(client, db, world, work):
    correction_id = _propose(client, world.eng_h, work).json()["id"]

    assert _decide(client, work.priya, correction_id, action="cancel").status_code == 403
    withdrawn = _decide(client, world.eng_h, correction_id, action="cancel")

    assert withdrawn.status_code == 200 and withdrawn.json()["status"] == "cancelled"
    assert _decide(client, work.priya, correction_id).status_code == 409
    assert _propose(client, world.eng_h, work).status_code == 201  # and may propose again


def test_a_correction_whose_hours_changed_is_not_applied(client, db, world, work):
    correction_id = _propose(client, world.eng_h, work, hours=6).json()["id"]
    row = db.get(models.TimeLogEntry, work.row_x.id)
    row.hours = 4  # e.g. another correction or a partial approval took hours off meanwhile
    db.commit()

    response = _decide(client, work.priya, correction_id)

    assert response.status_code == 409 and "changed since" in response.json()["detail"]
    assert _rows(db, work) == {work.x.id: (4, "pending_review")}


def test_approving_a_correction_is_blocked_while_timesheets_are_locked(client, db, world, work):
    correction_id = _propose(client, world.eng_h, work).json()["id"]
    project = db.get(models.Project, work.project_id)
    project.timesheets_soft_locked = True
    db.commit()

    assert _decide(client, work.priya, correction_id).status_code == 409
    assert _decide(client, work.priya, correction_id, action="reject").status_code == 200  # rejecting moves nothing
