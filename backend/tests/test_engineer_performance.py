"""Tests for GET /api/engineer-performance-dashboard (the Engineer's own dashboard).

The Total Hours figure and the monthly chart must both be derived live from real
approved time entries, grouped into the real month each logged day actually falls
in. Nothing is cached, hardcoded, or carried over from a fixed month list.
"""

from datetime import date

import pytest

import models

DASH = "/api/engineer-performance-dashboard"


@pytest.fixture
def dash(make, world):
    """A project this engineer is genuinely approved for, with one assigned task."""
    project_id = world.create_project()["id"]
    make.db.add(
        models.ResourceBooking(
            project_id=project_id,
            employee_id=world.emp1.id,
            planned_hours=200,
            utilization_rate=50,
            approval_status="approved",
        )
    )
    make.db.commit()
    node = make.wbs_node(project_id, world.lead_e, engineer=world.emp1, estimated_hours=40)
    return project_id, node


def add_entry(make, project_id, node, employee, week, status="pending_review", **days):
    values = {
        "mon_hours": 0.0,
        "tue_hours": 0.0,
        "wed_hours": 0.0,
        "thu_hours": 0.0,
        "fri_hours": 0.0,
        "sat_hours": 0.0,
        "sun_hours": 0.0,
    }
    values.update(days)
    entry = models.TimeLogEntry(
        project_id=project_id,
        task_id=node.id,
        employee_id=employee.id,
        week_start_date=week,
        approval_status=status,
        **values,
    )
    make.db.add(entry)
    make.db.commit()
    return entry


def dashboard(client, world, project_id):
    response = client.get(f"{DASH}?project_id={project_id}", headers=world.eng_h)
    assert response.status_code == 200, response.text
    return response.json()


def consumed(body, month):
    """Total approved consumption shown for a month, or None if it has no bar."""
    for row in body["monthly_breakdown"]:
        if row["month"] == month:
            return round(row["normal_consumption"] + row["exceeded_threshold"], 2)
    return None


def bar_months(body):
    return [row["month"] for row in body["monthly_breakdown"]]


def test_approved_hours_in_two_months_are_separate_independent_bars(client, world, make, dash):
    project_id, node = dash

    add_entry(make, project_id, node, world.emp1, date(2026, 8, 3), status="approved", mon_hours=4.0)
    add_entry(make, project_id, node, world.emp1, date(2026, 9, 7), status="approved", mon_hours=6.0)

    body = dashboard(client, world, project_id)

    assert consumed(body, "2026-08") == 4.0
    assert consumed(body, "2026-09") == 6.0
    assert body["summary"]["total_hours_consumption"] == 10.0
    assert body["summary"]["total_hours_approved"] == 10.0


def test_week_straddling_month_boundary_uses_the_real_work_month(client, world, make, dash):
    project_id, node = dash

    add_entry(make, project_id, node, world.emp1, date(2026, 8, 31), status="approved", thu_hours=5.0, fri_hours=5.0)

    body = dashboard(client, world, project_id)

    assert consumed(body, "2026-09") == 10.0
    assert consumed(body, "2026-08") in (None, 0.0)
    assert body["summary"]["total_hours_consumption"] == 10.0


def test_new_approved_hours_update_total_and_add_a_new_month_bar(client, world, make, dash):
    project_id, node = dash
    add_entry(make, project_id, node, world.emp1, date(2026, 7, 6), status="approved", mon_hours=5.0)

    before = dashboard(client, world, project_id)
    assert before["summary"]["total_hours_consumption"] == 5.0
    assert consumed(before, "2026-07") == 5.0
    assert "2026-08" not in bar_months(before)

    add_entry(make, project_id, node, world.emp1, date(2026, 8, 3), status="approved", mon_hours=4.0)

    after = dashboard(client, world, project_id)
    assert after["summary"]["total_hours_consumption"] == 9.0
    assert consumed(after, "2026-07") == 5.0
    assert consumed(after, "2026-08") == 4.0
    assert "2026-08" in bar_months(after)


def test_more_hours_in_an_existing_month_only_move_that_month(client, world, make, dash):
    project_id, node = dash
    add_entry(make, project_id, node, world.emp1, date(2026, 7, 6), status="approved", mon_hours=5.0)
    add_entry(make, project_id, node, world.emp1, date(2026, 8, 3), status="approved", mon_hours=4.0)

    add_entry(make, project_id, node, world.emp1, date(2026, 7, 13), status="approved", tue_hours=3.0)

    body = dashboard(client, world, project_id)
    assert consumed(body, "2026-07") == 8.0
    assert consumed(body, "2026-08") == 4.0
    assert body["summary"]["total_hours_consumption"] == 12.0


def test_pending_hours_are_excluded_from_total_and_chart(client, world, make, dash):
    project_id, node = dash
    add_entry(make, project_id, node, world.emp1, date(2026, 7, 6), status="approved", mon_hours=3.0)
    add_entry(make, project_id, node, world.emp1, date(2026, 8, 3), status="pending_review", mon_hours=8.0)

    body = dashboard(client, world, project_id)

    assert body["summary"]["total_hours_consumption"] == 3.0
    assert consumed(body, "2026-07") == 3.0
    assert consumed(body, "2026-08") in (None, 0.0)
    assert body["summary"]["total_hours_pending"] == 8.0


def test_rejected_hours_are_excluded_from_total_and_chart(client, world, make, dash):
    project_id, node = dash
    add_entry(make, project_id, node, world.emp1, date(2026, 7, 6), status="rejected", mon_hours=9.0)

    body = dashboard(client, world, project_id)

    assert body["summary"]["total_hours_consumption"] == 0.0
    assert consumed(body, "2026-07") in (None, 0.0)


def test_real_weekly_lead_approval_counts_the_engineers_hours(client, world, make, dash):
    project_id, node = dash
    add_entry(make, project_id, node, world.emp1, date(2026, 7, 6), status="pending_review", mon_hours=6.0)

    pending = dashboard(client, world, project_id)
    assert pending["summary"]["total_hours_consumption"] == 0.0

    make.db.add(
        models.WeeklyHoursSubmission(
            project_id=project_id,
            employee_id=world.emp1.id,
            week_start_date=date(2026, 7, 6),
            status="approved",
        )
    )
    make.db.commit()

    approved = dashboard(client, world, project_id)
    assert approved["summary"]["total_hours_consumption"] == 6.0
    assert consumed(approved, "2026-07") == 6.0


def test_rejected_week_excludes_its_hours(client, world, make, dash):
    project_id, node = dash
    add_entry(make, project_id, node, world.emp1, date(2026, 7, 6), status="pending_review", mon_hours=6.0)
    make.db.add(
        models.WeeklyHoursSubmission(
            project_id=project_id,
            employee_id=world.emp1.id,
            week_start_date=date(2026, 7, 6),
            status="rejected",
        )
    )
    make.db.commit()

    body = dashboard(client, world, project_id)

    assert body["summary"]["total_hours_consumption"] == 0.0
    assert consumed(body, "2026-07") in (None, 0.0)


def test_total_always_equals_the_sum_of_the_monthly_bars(client, world, make, dash):
    project_id, node = dash
    add_entry(make, project_id, node, world.emp1, date(2026, 8, 3), status="approved", mon_hours=4.0)
    add_entry(make, project_id, node, world.emp1, date(2026, 8, 31), status="approved", thu_hours=5.0, fri_hours=5.0)
    add_entry(make, project_id, node, world.emp1, date(2026, 9, 7), status="approved", mon_hours=2.0)

    body = dashboard(client, world, project_id)

    bar_sum = round(sum(consumed(body, m) or 0.0 for m in bar_months(body)), 2)
    assert body["summary"]["total_hours_consumption"] == bar_sum


def test_hours_from_a_project_the_engineer_is_not_approved_for_are_hidden(client, world, make, dash):
    project_id, node = dash
    add_entry(make, project_id, node, world.emp1, date(2026, 7, 6), status="approved", mon_hours=4.0)

    make.db.query(models.ResourceBooking).filter_by(project_id=project_id).delete()
    make.db.commit()

    body = client.get(DASH, headers=world.eng_h)
    assert body.status_code == 200, body.text
    assert body.json()["summary"]["total_hours_consumption"] == 0.0
    assert body.json()["monthly_breakdown"] == []


def test_dashboard_needs_an_employee_record(client, world, dash):
    project_id, _ = dash

    assert client.get(DASH, headers=world.lead_h).status_code == 200  # a lead is staff with an employee record
    assert client.get(DASH, headers=world.bu_h).status_code == 403
    assert client.get(DASH).status_code == 401
