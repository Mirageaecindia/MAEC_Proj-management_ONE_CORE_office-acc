"""A second look at rejected hours (app/services/rejected_hours.py).

Any lead of the project, or the BU Head, may approve rejected hours again
within seven days, with a reason. After that the rejection is final.

Scenario: Arjun has 8 h on a task under the Electrical lead (Anita), who
rejects them. Priya and Mohan lead the same project.
"""

from datetime import UTC, datetime, time, timedelta
from types import SimpleNamespace

import pytest
from test_project_roles import _approve_booking

import models
from app.domain.timesheets import open_time
from app.repositories.work import WorkRepository
from factories import PASSWORD, WEEK

DAY = WEEK  # a Monday in the past
T0 = datetime(2026, 9, 1, tzinfo=UTC)


def _headers(client, username):
    token = client.post("/api/auth/login", json={"username": username, "password": PASSWORD}).json()["token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def rejected(client, db, make, world):
    """Anita has just rejected Arjun's 8 h as idle time."""
    project_id = world.create_project()["id"]
    _approve_booking(client, world, project_id, world.emp1, world.lead_h)
    task = make.wbs_node(project_id, world.lead_e, engineer=world.emp1)
    row = make.time_entry(project_id, task, world.emp1, 8, day=DAY)
    response = client.post(f"/api/time-log-entries/{row.id}/reject", json={"reason": "Idle time"}, headers=world.lead_h)
    assert response.status_code == 200, response.text
    return SimpleNamespace(project_id=project_id, task=task, row_id=row.id, priya=_headers(client, "lead.m"))


def _listed(client, headers, project_id):
    return client.get(f"/api/projects/{project_id}/rejected-hours", headers=headers)


def _reapprove(client, headers, row_id, reason="He was on the site survey that day", **body):
    return client.post(f"/api/time-log-entries/{row_id}/reapprove", json={"reason": reason, **body}, headers=headers)


def _rejected_ago(db, row_id, **ago):
    """Move the rejection back in time."""
    row = db.get(models.TimeLogEntry, row_id)
    row.reviewed_at = datetime.now(UTC) - timedelta(**ago)
    db.commit()


def _audit(db, project_id, action, days_ago):
    db.add(
        models.GovernanceAction(
            project_id=project_id, action=action, created_at=datetime.now(UTC) - timedelta(days=days_ago)
        )
    )
    db.commit()


def test_another_lead_of_the_project_approves_rejected_hours_with_a_reason(client, db, world, rejected):
    (listed,) = _listed(client, rejected.priya, rejected.project_id).json()
    assert (listed["employee_name"], listed["hours"], listed["rejected_by"], listed["reason"]) == (
        "Arjun Mehta",
        8,
        "Anita Kumar",
        "Idle time",
    )
    assert (listed["can_reapprove"], listed["rejected_by_bu_head"], listed["hours_left"]) == (True, False, 168.0)

    assert _reapprove(client, rejected.priya, rejected.row_id, reason="  ").status_code == 400  # a reason is required
    plain = client.post(f"/api/time-log-entries/{rejected.row_id}/approve", headers=rejected.priya)
    assert plain.status_code in (403, 409)  # the ordinary approval never re-approves
    response = _reapprove(client, rejected.priya, rejected.row_id)

    assert response.status_code == 200, response.text
    assert response.json()["approval_status"] == "approved" and response.json()["reviewed_by"] == "Priya Nair"
    assert WorkRepository(db).approved_hours(rejected.project_id) == 8
    audit = db.query(models.GovernanceAction).filter_by(project_id=rejected.project_id, action="hours_reapproved").one()
    assert audit.created_by == "Priya Nair"  # both names are on record
    assert "rejected by Anita Kumar: Idle time" in audit.comments and "site survey" in audit.comments
    assert _listed(client, rejected.priya, rejected.project_id).json() == []
    assert _reapprove(client, rejected.priya, rejected.row_id).status_code == 409  # no longer rejected


def test_the_lead_who_rejected_may_change_their_mind_and_so_may_the_bu_head(client, db, world, rejected):
    assert _reapprove(client, world.lead_h, rejected.row_id).status_code == 200
    db.expire_all()
    assert db.get(models.TimeLogEntry, rejected.row_id).approval_status == "approved"


def test_after_seven_days_the_rejection_is_final_for_everyone(client, db, world, rejected):
    _rejected_ago(db, rejected.row_id, days=6, hours=23)
    assert _listed(client, rejected.priya, rejected.project_id).json()[0]["hours_left"] == 1.0

    _rejected_ago(db, rejected.row_id, days=7, minutes=1)

    assert _listed(client, rejected.priya, rejected.project_id).json() == []
    for headers in (rejected.priya, world.lead_h, world.bu_h):
        late = _reapprove(client, headers, rejected.row_id)
        assert late.status_code == 409 and "final" in late.json()["detail"]


def test_hours_the_bu_head_rejected_are_approved_again_only_by_the_bu_head(client, db, make, world, rejected):
    row = make.time_entry(rejected.project_id, rejected.task, world.emp1, 4, day=DAY + timedelta(days=1))
    assert client.post(f"/api/time-log-entries/{row.id}/approve", headers=world.lead_h).status_code == 200
    took_back = client.post(f"/api/time-log-entries/{row.id}/reject", json={"reason": "Audit"}, headers=world.bu_h)
    assert took_back.status_code == 403  # the task has an active lead: not the BU Head's row to decide
    entry = db.get(models.TimeLogEntry, row.id)  # so: rejected by the BU Head, as for a lead's own hours
    entry.approval_status, entry.reviewed_by, entry.reviewed_by_user_id = "rejected", "Test BU Head", world.bu.id
    entry.reviewed_at = datetime.now(UTC)
    db.commit()

    by_id = {r["id"]: r for r in _listed(client, rejected.priya, rejected.project_id).json()}
    assert (by_id[row.id]["rejected_by_bu_head"], by_id[row.id]["can_reapprove"]) == (True, False)
    refused = _reapprove(client, rejected.priya, row.id)
    assert refused.status_code == 403 and "only the BU Head" in refused.json()["detail"]
    assert _reapprove(client, world.bu_h, row.id).status_code == 200


def test_nobody_approves_their_own_rejected_hours(client, db, make, world, rejected):
    priya_employee = db.get(models.Employee, world.lead_m.employee_id)
    own = make.time_entry(rejected.project_id, rejected.task, priya_employee, 3, status="rejected", day=DAY)
    own.reviewed_by, own.reviewed_by_user_id, own.reviewed_at = "Anita Kumar", world.lead_e.id, datetime.now(UTC)
    db.commit()

    response = _reapprove(client, rejected.priya, own.id)

    assert response.status_code == 403 and "their own hours" in response.json()["detail"]
    assert _reapprove(client, world.lead_h, own.id).status_code == 200  # another lead may


def test_only_the_projects_leads_and_the_bu_head_see_and_decide(client, world, rejected):
    assert _listed(client, world.eng_h, rejected.project_id).status_code == 403  # an engineer on the project
    assert _reapprove(client, world.eng_h, rejected.row_id).status_code == 403
    assert _listed(client, world.other_lead_h, rejected.project_id).status_code == 403  # leads another project
    assert _reapprove(client, world.other_lead_h, rejected.row_id).status_code == 403
    assert len(_listed(client, world.bu_h, rejected.project_id).json()) == 1


def test_the_seven_days_do_not_run_while_the_project_is_locked(client, db, world, rejected):
    _rejected_ago(db, rejected.row_id, days=10)
    _audit(db, rejected.project_id, "stop_execution", days_ago=9)  # locked for four of the ten days
    _audit(db, rejected.project_id, "resume_execution", days_ago=5)

    (listed,) = _listed(client, rejected.priya, rejected.project_id).json()
    assert listed["hours_left"] == 24.0  # six open days used, one left
    assert _reapprove(client, rejected.priya, rejected.row_id).status_code == 200


def test_nothing_is_approved_while_the_project_is_locked(client, db, world, rejected):
    project = db.get(models.Project, rejected.project_id)
    project.timesheets_soft_locked = True
    db.commit()

    (listed,) = _listed(client, rejected.priya, rejected.project_id).json()
    assert (listed["can_reapprove"], listed["clock_paused"]) == (False, True)
    locked = _reapprove(client, rejected.priya, rejected.row_id)
    assert locked.status_code == 409 and "locked" in locked.json()["detail"]


def test_an_unattended_rejected_day_can_be_approved_up_to_the_last_visit(client, db, make, world, rejected):
    start = datetime.combine(DAY, time.min, tzinfo=UTC)
    make._save(
        models.TimeSession(
            project_id=rejected.project_id,
            task_id=rejected.task.id,
            subtask_id=rejected.task.id,
            employee_id=world.emp1.id,
            login_at=start + timedelta(hours=9),
            last_seen_at=start + timedelta(hours=17),
            last_active_at=start + timedelta(hours=11),
            logout_at=start + timedelta(hours=17),
            active_seconds=8 * 3600,
            status="ended",
            ended_by="laptop_off",
        )
    )
    (listed,) = _listed(client, rejected.priya, rejected.project_id).json()
    assert (listed["unattended"], listed["attended_hours"]) == (True, 2.0)

    response = _reapprove(client, rejected.priya, rejected.row_id, attended_only=True)

    assert response.status_code == 200, response.text
    assert (response.json()["hours"], response.json()["trimmed_hours"]) == (2.0, 6.0)
    assert WorkRepository(db).approved_hours(rejected.project_id) == 2.0
    audit = db.query(models.GovernanceAction).filter_by(project_id=rejected.project_id, action="hours_reapproved").one()
    assert audit.comments.startswith("2 of 8 h on ")


@pytest.mark.parametrize(
    ("events", "expected_days"),
    [
        ([], 10),
        ([(T0 + timedelta(days=2), "lock", True), (T0 + timedelta(days=5), "lock", False)], 7),
        ([(T0 + timedelta(days=8), "lock", True)], 8),  # still locked at the end
        ([(T0 - timedelta(days=3), "lock", True), (T0 + timedelta(days=1), "lock", False)], 9),  # locked at the start
        (  # locked and archived at once: open only when neither holds
            [
                (T0 + timedelta(days=1), "lock", True),
                (T0 + timedelta(days=2), "archive", True),
                (T0 + timedelta(days=3), "lock", False),
                (T0 + timedelta(days=6), "archive", False),
            ],
            5,
        ),
    ],
)
def test_open_time_leaves_out_the_time_a_project_was_closed(events, expected_days):
    assert open_time(T0, T0 + timedelta(days=10), events) == timedelta(days=expected_days)
