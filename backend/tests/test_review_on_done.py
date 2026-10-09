"""A subtask's hours are reviewed as soon as it is Done (decided 2026-10-09), and its reviewer is told.

The day's total still waits for the day to end: "Approve week" takes finished days only.
"""

from datetime import timedelta

import pytest
from test_project_roles import _approve_booking

import models
from app.domain.timesheets import today_utc
from app.services.hours_review import SUBTASK_DONE
from app.services.tracking import ALREADY_REVIEWED_TODAY

ADVANCE = "/api/wbs-nodes/{}/advance-status"


@pytest.fixture
def todays_work(client, make, world):
    """Arjun's subtask under Anita's task, with 3 h logged today."""
    project_id = world.create_project()["id"]
    _approve_booking(client, world, project_id, world.emp1, world.lead_h)
    task = make.wbs_node(project_id, world.lead_e, engineer=world.emp1, wbs_code="1.")
    subtask = make.wbs_node(
        project_id, world.lead_e, engineer=world.emp1, parent_id=task.id, wbs_code="1.1", estimated_hours=4
    )
    row = make.time_entry(project_id, subtask, world.emp1, 3, day=today_utc())
    return project_id, subtask, row


def _done(client, headers, subtask):
    for status in ("In-Progress", "Done"):
        response = client.post(ADVANCE.format(subtask.id), json={"new_status": status}, headers=headers)
        assert response.status_code == 200, response.text


def _notifications(client, headers):
    return [
        n for n in client.get("/api/notifications", headers=headers).json() if n["notification_type"] == SUBTASK_DONE
    ]


def test_todays_hours_are_reviewed_as_soon_as_the_subtask_is_done(client, db, world, todays_work):
    project_id, subtask, row = todays_work

    early = client.post(f"/api/time-log-entries/{row.id}/approve", json={}, headers=world.lead_h)
    assert early.status_code == 409 and "once the subtask is Done" in early.json()["detail"]

    _done(client, world.eng_h, subtask)

    week = today_utc() - timedelta(days=today_utc().weekday())
    listed = client.get(f"/api/projects/{project_id}/timesheet?week_start={week}", headers=world.lead_h).json()
    assert next(r for r in listed if r["id"] == row.id)["can_review"] is True
    approved = client.post(f"/api/time-log-entries/{row.id}/approve", json={}, headers=world.lead_h)
    assert approved.status_code == 200, approved.text


def test_done_tells_the_reviewer_with_a_link_to_that_day(client, world, todays_work):
    project_id, subtask, _ = todays_work

    _done(client, world.eng_h, subtask)

    [note] = _notifications(client, world.lead_h)
    assert note["title"] == f"Subtask done: 1.1 {subtask.task_name}"
    assert "Arjun Mehta finished" in note["message"] and "h waiting for your review" in note["message"]
    week = today_utc() - timedelta(days=today_utc().weekday())
    assert note["link"] == f"/weekly-logs?projectId={project_id}&employeeId={world.emp1.id}&weekStart={week}"
    assert _notifications(client, world.bu_h) == []  # not the BU Head's to review


def test_a_leads_own_subtask_done_tells_the_bu_head(client, db, make, world):
    project_id = world.create_project()["id"]
    anita = db.get(models.Employee, world.lead_e.employee_id)
    task = make.wbs_node(project_id, world.lead_e, engineer=anita, wbs_code="2.")
    subtask = make.wbs_node(project_id, world.lead_e, engineer=anita, parent_id=task.id, wbs_code="2.1")

    _done(client, world.lead_h, subtask)

    assert [n["title"] for n in _notifications(client, world.bu_h)] == [f"Subtask done: 2.1 {subtask.task_name}"]
    assert _notifications(client, world.lead_h) == []


def test_nobody_is_told_of_their_own_action(client, world, todays_work):
    _, subtask, _ = todays_work

    _done(client, world.lead_h, subtask)  # the lead finishes Arjun's subtask: the lead reviews it anyway

    assert _notifications(client, world.lead_h) == []


def test_after_a_same_day_review_the_reopened_subtask_takes_no_more_time_today(client, db, world, todays_work):
    _, subtask, row = todays_work
    _done(client, world.eng_h, subtask)
    assert client.post(f"/api/time-log-entries/{row.id}/approve", json={}, headers=world.lead_h).status_code == 200
    db.refresh(subtask)
    reopen = {
        "task_name": subtask.task_name,
        "parent_id": subtask.parent_id,
        "assigned_engineer_id": subtask.assigned_engineer_id,
        "estimated_hours": subtask.estimated_hours,
        "start_date": subtask.start_date.isoformat(),
        "target_due_date": subtask.target_due_date.isoformat(),
        "deliverable_status": "In-Progress",
    }
    assert client.put(f"/api/wbs-nodes/{subtask.id}", json=reopen, headers=world.lead_h).status_code == 200

    login = client.post("/api/subtask-tracking/start", json={"subtask_id": subtask.id}, headers=world.eng_h)

    assert login.status_code == 409 and login.json()["detail"] == ALREADY_REVIEWED_TODAY
    db.expire_all()
    assert db.get(models.TimeLogEntry, row.id).approval_status == "approved"  # the reviewed row never changes


def test_the_notification_counts_the_time_of_the_session_done_just_ended(client, db, world, todays_work, monkeypatch):
    from datetime import UTC, datetime

    from app.services import tracking

    _, subtask, row = todays_work
    db.delete(row)  # only the running session's time
    db.commit()
    start = datetime.now(UTC).replace(hour=9, minute=0, second=0, microsecond=0)
    monkeypatch.setattr(tracking, "utcnow", lambda: start)
    client.post(ADVANCE.format(subtask.id), json={"new_status": "In-Progress"}, headers=world.eng_h)  # logs in
    monkeypatch.setattr(tracking, "utcnow", lambda: start + timedelta(hours=2))
    session = db.query(models.TimeSession).filter_by(subtask_id=subtask.id).one()
    session.last_seen_at = start + timedelta(hours=2)
    db.commit()

    done = client.post(ADVANCE.format(subtask.id), json={"new_status": "Done"}, headers=world.eng_h)
    assert done.status_code == 200, done.text

    [note] = _notifications(client, world.lead_h)
    assert "2 h waiting for your review" in note["message"]
