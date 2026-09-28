"""Who approves which hours: the task's lead, else the BU Head (app/services/hours_review.py).

Scenario: Arjun works on two tasks of one project, one under the Electrical
lead (Anita) and one under the Mechanical lead (Priya), 8 h each that week.
"""

from datetime import date, timedelta

import pytest
from alembic import command
from sqlalchemy import create_engine, text
from test_project_roles import _approve_booking

import models
from app.core.migrations import _config
from app.repositories.work import WorkRepository
from app.services.tracking import upsert_subtask_time_log
from factories import PASSWORD, WEEK

WEEK_BODY = {"week_start_date": WEEK.isoformat()}


@pytest.fixture
def split(client, db, make, world):
    project_id = world.create_project()["id"]
    _approve_booking(client, world, project_id, world.emp1, world.lead_h)
    task_e = make.wbs_node(project_id, world.lead_e, engineer=world.emp1)
    task_m = make.wbs_node(project_id, world.lead_m, engineer=world.emp1)
    row_e = make.time_entry(project_id, task_e, world.emp1, 8)
    row_m = make.time_entry(project_id, task_m, world.emp1, 8)
    return project_id, row_e, row_m


def _week(client, headers, project_id, action, employee_id):
    body = {**WEEK_BODY, "employee_id": employee_id}
    return client.post(f"/api/projects/{project_id}/weekly-hours/{action}", json=body, headers=headers)


def _headers(client, username):
    token = client.post("/api/auth/login", json={"username": username, "password": PASSWORD}).json()["token"]
    return {"Authorization": f"Bearer {token}"}


def _row(client, headers, row_id, action="approve"):
    return client.post(f"/api/time-log-entries/{row_id}/{action}", headers=headers)


def _status(db, row):
    db.expire_all()
    return db.get(models.TimeLogEntry, row.id).approval_status


def _summary(client, headers, project_id):
    rows = client.get(f"/api/projects/{project_id}/weekly-hours-submissions?week_start={WEEK}", headers=headers).json()
    return next(row for row in rows if row["employee_name"] == "Arjun Mehta")


def test_each_lead_approves_the_hours_on_their_own_tasks(client, db, world, split):
    project_id, row_e, row_m = split
    lead_m_h = _headers(client, "lead.m")
    assert (
        client.post(f"/api/projects/{project_id}/weekly-hours/submit", json=WEEK_BODY, headers=world.eng_h).status_code
        == 200
    )
    assert _summary(client, world.bu_h, project_id)["waiting_on"] == ["Anita Kumar", "Priya Nair"]

    first = _week(client, world.lead_h, project_id, "approve", world.emp1.id)

    assert first.status_code == 200, first.text
    assert (first.json()["status"], first.json()["reviewers_done"], first.json()["reviewers_total"]) == (
        "submitted",
        1,
        2,
    )
    assert first.json()["waiting_on"] == ["Priya Nair"]  # "1 of 2 approved"
    assert (_status(db, row_e), _status(db, row_m)) == ("approved", "pending_review")
    assert WorkRepository(db).approved_hours(project_id) == 8.0  # usage counts each row as it's approved
    assert _week(client, world.lead_h, project_id, "approve", world.emp1.id).status_code == 409  # nothing of hers left
    assert (
        _week(client, world.other_lead_h, project_id, "approve", world.emp1.id).status_code == 403
    )  # not a lead of it

    second = _week(client, lead_m_h, project_id, "approve", world.emp1.id)

    assert (second.json()["status"], second.json()["waiting_on"]) == ("approved", [])
    assert WorkRepository(db).approved_hours(project_id) == 16.0


def test_a_single_row_is_approved_only_by_its_reviewer(client, db, world, split):
    project_id, row_e, row_m = split

    assert _row(client, world.bu_h, row_e.id).status_code == 403  # the task has an active lead
    assert _row(client, world.lead_h, row_m.id).status_code == 403  # Priya's task, not Anita's
    assert _row(client, world.lead_h, row_e.id).status_code == 200


def test_hours_without_an_active_lead_go_to_the_bu_head(client, db, make, world, split):
    project_id, row_e, _ = split
    orphan_task = make.wbs_node(
        project_id, world.lead_e, engineer=world.emp1, assigned_lead=None, assigned_lead_user_id=None
    )
    orphan = make.time_entry(project_id, orphan_task, world.emp1, 4, week=WEEK + timedelta(days=7))

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


def test_the_bu_head_is_blocked_by_the_lock_like_the_leads(client, db, make, world):
    project_id = world.create_project()["id"]
    anita = db.get(models.Employee, world.lead_e.employee_id)
    own_row = make.time_entry(project_id, make.wbs_node(project_id, world.lead_e, engineer=anita), anita, 8)
    assert (
        client.post(f"/api/projects/{project_id}/weekly-hours/submit", json=WEEK_BODY, headers=world.lead_h).status_code
        == 200
    )
    db.get(models.Project, project_id).timesheets_soft_locked = True
    db.commit()

    week = client.post(
        f"/api/projects/{project_id}/weekly-hours/approve",
        json={**WEEK_BODY, "employee_id": anita.id},
        headers=world.bu_h,
    )
    row = _row(client, world.bu_h, own_row.id)

    assert (week.status_code, row.status_code) == (409, 409)
    assert _status(db, own_row) == "pending_review"


def test_new_hours_on_an_approved_row_need_review_again(client, db, world, split):
    project_id, row_e, row_m = split
    client.post(f"/api/projects/{project_id}/weekly-hours/submit", json=WEEK_BODY, headers=world.eng_h)
    _week(client, world.lead_h, project_id, "approve", world.emp1.id)
    _week(client, _headers(client, "lead.m"), project_id, "approve", world.emp1.id)
    assert _summary(client, world.bu_h, project_id)["status"] == "approved"

    upsert_subtask_time_log(db, project_id, row_e.task_id, world.emp1.id, WEEK + timedelta(days=2), 3600)
    db.commit()

    assert _status(db, row_e) == "pending_review"  # never counted as approved without a review
    assert _summary(client, world.bu_h, project_id)["status"] == "submitted"
    assert WorkRepository(db).approved_hours(project_id) == 8.0  # only Priya's row still counts


def test_resubmitting_a_week_asks_again_for_rejected_hours(client, db, world, split):
    project_id, row_e, _ = split
    client.post(f"/api/projects/{project_id}/weekly-hours/submit", json=WEEK_BODY, headers=world.eng_h)
    assert _week(client, world.lead_h, project_id, "reject", world.emp1.id).status_code == 200
    assert _status(db, row_e) == "rejected"

    client.post(f"/api/projects/{project_id}/weekly-hours/submit", json=WEEK_BODY, headers=world.eng_h)

    assert _status(db, row_e) == "pending_review"


def test_migration_0007_copies_old_week_decisions_onto_their_rows(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with engine.begin() as connection:
        command.upgrade(_config(connection), "0006")
        connection.execute(
            text(
                "INSERT INTO weekly_hours_submissions (project_id, employee_id, week_start_date, status, reviewed_by) "
                "VALUES (1, 1, '2026-09-07', 'approved', 'Anita Kumar'), "
                "(1, 2, '2026-09-07', 'rejected', 'Anita Kumar')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO time_log_entries (id, project_id, task_id, employee_id, week_start_date, approval_status, "
                "mon_hours, tue_hours, wed_hours, thu_hours, fri_hours, sat_hours, sun_hours) VALUES "
                "(1, 1, 1, 1, '2026-09-07', 'pending_review', 8, 0, 0, 0, 0, 0, 0), "
                "(2, 1, 1, 2, '2026-09-07', 'pending_review', 8, 0, 0, 0, 0, 0, 0), "
                "(3, 1, 1, 3, '2026-09-07', 'pending_review', 8, 0, 0, 0, 0, 0, 0)"
            )
        )
        command.upgrade(_config(connection), "head")

    with engine.connect() as connection:
        rows = connection.execute(
            text("SELECT id, approval_status, reviewed_by FROM time_log_entries ORDER BY id")
        ).all()
    assert [tuple(row) for row in rows] == [
        (1, "approved", "Anita Kumar"),
        (2, "rejected", "Anita Kumar"),
        (3, "pending_review", None),  # no decided week: untouched
    ]
