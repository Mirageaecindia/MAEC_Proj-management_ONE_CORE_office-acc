"""A second look at rejected hours (app/services/rejected_hours.py).

Any lead of the project, or the BU Head, may approve rejected hours again
within seven days, with a reason. After that the rejection is final.

Scenario: Arjun has 8 h on a task under the Electrical lead (Anita), who
rejects them. Priya and Mohan lead the same project.
"""

from datetime import UTC, datetime, time, timedelta
from types import SimpleNamespace

import pytest
from test_governance_workflow import _reach_baseline
from test_project_roles import _approve_booking

import models
from app.domain.governance import WARNING
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


def test_approving_rejected_hours_again_runs_the_governance_check(client, db, make, world, governed):
    """Usage is approved hours, so the second look must alert and lock like any other approval."""
    project_id, node_a, *_ = governed  # target 100 h, threshold 80%, 30 h approved
    priya = _headers(client, "lead.m")

    def rejected_row(hours, day):
        row = make.time_entry(project_id, node_a, world.emp1, hours, status="rejected", day=day)
        row.reviewed_by, row.reviewed_by_user_id, row.reviewed_at = "Anita Kumar", world.lead_e.id, datetime.now(UTC)
        db.commit()
        return row.id

    first, second = rejected_row(50, DAY + timedelta(days=1)), rejected_row(20, DAY + timedelta(days=2))

    assert _reapprove(client, priya, first).status_code == 200  # 80 of 100 h: the threshold
    db.expire_all()
    project = db.get(models.Project, project_id)
    assert (project.governance_alert_level, project.timesheets_soft_locked) == (WARNING, False)

    assert _reapprove(client, priya, second).status_code == 200  # 100 of 100 h: the baseline
    db.expire_all()
    project = db.get(models.Project, project_id)
    assert (project.timesheets_soft_locked, project.lock_reason) == (True, "auto")
    actions = [a.action for a in db.query(models.GovernanceAction).filter_by(project_id=project_id)]
    assert actions.count("hours_reapproved") == 2 and "auto_lock" in actions


def test_the_clock_stops_for_an_automatic_lock_and_restarts_when_an_extension_reopens_it(client, db, world, governed):
    """Reject, the project locks itself two days later, an extension reopens it three days
    after that: the hours are still approvable on day 9 and final on day 10. The lock and the
    reopening are the real ones the system records, not hand-written audit rows."""
    project_id, node_a, _, pending = governed
    rejected_id = pending.id
    assert client.post(f"/api/time-log-entries/{rejected_id}/reject", headers=world.lead_h).status_code == 200
    _reach_baseline(client, world, node_a)  # approved hours reach 100%: the automatic lock
    request = client.post(
        f"/api/projects/{project_id}/extension-requests",
        json={"requested_hours": 50, "justification": "Client added a floor"},
        headers=world.lead_h,
    )
    decided = client.post(
        f"/api/projects/{project_id}/extension-requests/{request.json()['id']}/decision",
        json={"decision": "approve", "comments": "Agreed"},
        headers=world.bu_h,
    )
    assert decided.status_code == 200
    db.expire_all()
    assert db.get(models.Project, project_id).timesheets_soft_locked is False
    recorded = {a.action: a for a in db.query(models.GovernanceAction).filter_by(project_id=project_id)}
    assert {"auto_lock", "resume_execution"} <= set(recorded)  # both written by the system itself

    def on_day(day):
        """Place the rejection `day` days ago, the lock two days after it and the reopening three later."""
        rejected_at = datetime.now(UTC) - timedelta(days=day)
        db.get(models.TimeLogEntry, rejected_id).reviewed_at = rejected_at
        recorded["auto_lock"].created_at = rejected_at + timedelta(days=2)
        recorded["resume_execution"].created_at = rejected_at + timedelta(days=5)
        db.commit()

    priya = _headers(client, "lead.m")
    on_day(10)  # seven open days are used up
    assert _listed(client, priya, project_id).json() == []
    assert _reapprove(client, priya, rejected_id).status_code == 409

    on_day(9)  # six open days used: one left
    (listed,) = _listed(client, priya, project_id).json()
    assert listed["hours_left"] == 24.0
    assert _reapprove(client, priya, rejected_id).status_code == 200


def test_a_row_is_approved_again_once_then_only_the_bu_head_decides_it(client, db, world, rejected):
    assert _reapprove(client, rejected.priya, rejected.row_id).status_code == 200

    took_back = client.post(
        f"/api/time-log-entries/{rejected.row_id}/reject", json={"reason": "Still idle time"}, headers=world.lead_h
    )
    assert took_back.status_code == 403 and "only the BU Head" in took_back.json()["detail"]  # no ping-pong
    week = client.get(
        f"/api/projects/{rejected.project_id}/timesheet?week_start={WEEK.isoformat()}", headers=world.lead_h
    ).json()
    assert [row["can_review"] for row in week if row["id"] == rejected.row_id] == [False]

    by_bu_head = client.post(
        f"/api/time-log-entries/{rejected.row_id}/reject", json={"reason": "Checked: idle"}, headers=world.bu_h
    )
    assert by_bu_head.status_code == 200
    again = _reapprove(client, rejected.priya, rejected.row_id)
    assert again.status_code == 403 and "only the BU Head" in again.json()["detail"]
    assert _reapprove(client, world.bu_h, rejected.row_id).status_code == 200
