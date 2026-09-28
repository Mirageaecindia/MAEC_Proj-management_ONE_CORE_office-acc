"""Project leads are chosen with a period and a utilization % (TODO L1, stage 3).

Each lead slot becomes an approved booking with role "lead": it holds the
person's capacity like any booking, lists them for WBS assignment, and is
rebuilt whenever the BU Head saves the project. The BU Head approves a lead's
own hours; a lead can't be booked as an engineer on a project they lead.
"""

from datetime import date

from test_project_roles import _approve_booking

import models
from factories import WEEK


def _lead_bookings(db, project_id):
    return {b.employee_id: b for b in db.query(models.ResourceBooking).filter_by(project_id=project_id, role="lead")}


def _book(client, world, project_id, employee_id, pct, start, end, headers=None):
    return client.post(
        f"/api/projects/{project_id}/resource-bookings",
        json={"employee_id": employee_id, "utilization_rate": pct, "start_date": start, "end_date": end},
        headers=headers or world.lead_h,
    )


def test_each_lead_holds_capacity_as_an_approved_lead_booking(client, db, world):
    created = world.create_project(
        project_lead_electrical_start_date="2026-10-01",
        project_lead_electrical_end_date="2026-10-31",
        project_lead_electrical_utilization_pct=50,
    )
    project_id = created["id"]

    anita = _lead_bookings(db, project_id)[world.lead_e.employee_id]
    assert (anita.approval_status, anita.utilization_rate) == ("approved", 50)
    assert (anita.start_date, anita.end_date) == (date(2026, 10, 1), date(2026, 10, 31))
    assert anita.planned_hours == 88  # 22 weekdays x 8 h x 50%
    assert created["project_lead_electrical_utilization_pct"] == 50
    fetched = client.get(f"/api/projects/{project_id}", headers=world.bu_h).json()
    assert (fetched["project_lead_electrical_start_date"], fetched["project_lead_mechanical_utilization_pct"]) == (
        "2026-10-01",
        20,
    )
    # Leads can be given subtasks: they're among the project's people.
    people = {
        row["name"] for row in client.get(f"/api/projects/{project_id}/booked-engineers", headers=world.lead_h).json()
    }
    assert {"Anita Kumar", "Priya Nair", "Mohan Daniel"} <= people


def test_a_lead_assignment_respects_the_persons_capacity(client, world):
    elsewhere = world.create_project()["id"]
    assert _book(client, world, elsewhere, world.emp1.id, 90, "2026-10-01", "2026-12-31").status_code == 200
    arjun_leads = dict(
        project_lead_bim=None,
        project_lead_bim_user_id=world.engineer.id,
        project_lead_bim_utilization_pct=20,
    )

    overlapping = world.project_payload(
        **arjun_leads, project_lead_bim_start_date="2026-11-01", project_lead_bim_end_date="2027-01-31"
    )
    refused = client.post("/api/projects", json=overlapping, headers=world.bu_h)
    assert refused.status_code == 400
    assert "Arjun Mehta is already allocated 90%" in refused.json()["detail"]

    later = world.project_payload(
        **arjun_leads, project_lead_bim_start_date="2027-01-01", project_lead_bim_end_date="2027-03-31"
    )
    assert client.post("/api/projects", json=later, headers=world.bu_h).status_code == 201


def test_editing_the_leads_rebuilds_their_bookings(client, db, world):
    project_id = world.create_project()["id"]
    payload = {
        **world.project_payload(project_code=None),
        "project_lead_electrical": None,
        "project_lead_electrical_user_id": world.other_lead.id,  # replaces Anita
        "project_lead_mechanical_utilization_pct": 40,  # Priya: more time
        "confirm_currency_change": False,
    }
    payload["project_code"] = client.get(f"/api/projects/{project_id}", headers=world.bu_h).json()["project_code"]

    response = client.put(f"/api/projects/{project_id}", json=payload, headers=world.bu_h)

    assert response.status_code == 200, response.text
    bookings = _lead_bookings(db, project_id)
    assert set(bookings) == {world.other_lead.employee_id, world.lead_m.employee_id, world.lead_b.employee_id}
    assert bookings[world.lead_m.employee_id].utilization_rate == 40


def test_lead_rows_are_not_bookings_the_lead_can_touch(client, db, world):
    project_id = world.create_project()["id"]
    anita = _lead_bookings(db, project_id)[world.lead_e.employee_id]
    url = f"/api/projects/{project_id}/resource-bookings"

    # A lead can't be booked as an engineer on the project they lead.
    refused = _book(client, world, project_id, world.lead_e.employee_id, 30, "2026-10-01", "2026-10-31")
    assert refused.status_code == 400 and "leads this project" in refused.json()["detail"]
    # Lead rows are the BU Head's: no edit, no delete, and nothing to submit.
    assert client.put(f"{url}/{anita.id}", json={"utilization_rate": 5}, headers=world.lead_h).status_code == 400
    assert client.delete(f"{url}/{anita.id}", headers=world.lead_h).status_code == 400
    submit = client.post(f"{url}/submit", headers=world.lead_h)
    assert submit.status_code == 400 and "at least one engineer" in submit.json()["detail"]
    # A person booked as an engineer can't then be made a lead of the same project.
    assert _book(client, world, project_id, world.emp1.id, 30, "2026-10-01", "2026-10-31").status_code == 200
    made_lead = world.project_payload(project_lead_bim=None, project_lead_bim_user_id=world.engineer.id)
    made_lead["project_code"] = client.get(f"/api/projects/{project_id}", headers=world.bu_h).json()["project_code"]
    assert client.put(f"/api/projects/{project_id}", json=made_lead, headers=world.bu_h).status_code == 409


def test_a_chosen_lead_needs_a_period_and_a_percentage(client, world):
    cases = [
        {"project_lead_bim_start_date": None},
        {"project_lead_bim_end_date": "2026-08-01"},  # before the start
        {"project_lead_bim_utilization_pct": 0},
        {"project_lead_electrical_user_id": world.lead_m.id, "project_lead_electrical": None},  # Priya twice
    ]
    for case in cases[:3]:
        assert client.post("/api/projects", json=world.project_payload(**case), headers=world.bu_h).status_code == 422
    twice = client.post("/api/projects", json=world.project_payload(**cases[3]), headers=world.bu_h)
    assert twice.status_code == 400 and "two lead roles" in twice.json()["detail"]


def test_the_bu_head_approves_a_leads_own_hours(client, db, make, world):
    project_id = world.create_project()["id"]
    anita = db.get(models.Employee, world.lead_e.employee_id)
    task = make.wbs_node(project_id, world.lead_e, engineer=anita)
    own_row = make.time_entry(project_id, task, anita, 8)
    engineer_row = make.time_entry(
        project_id, make.wbs_node(project_id, world.lead_e, engineer=world.emp1), world.emp1, 8
    )
    week = {"week_start_date": WEEK.isoformat()}

    # Rows: the lead can't approve their own; the BU Head can, but not an engineer's.
    assert client.post(f"/api/time-log-entries/{own_row.id}/approve", headers=world.lead_h).status_code == 403
    assert client.post(f"/api/time-log-entries/{own_row.id}/approve", headers=world.bu_h).status_code == 200
    assert client.post(f"/api/time-log-entries/{engineer_row.id}/approve", headers=world.bu_h).status_code == 403
    assert client.post(f"/api/time-log-entries/{engineer_row.id}/approve", headers=world.lead_h).status_code == 200
    # Weeks: the lead submits their own week; only the BU Head can approve it.
    assert (
        client.post(f"/api/projects/{project_id}/weekly-hours/submit", json=week, headers=world.lead_h).status_code
        == 200
    )
    review = {**week, "employee_id": anita.id}
    assert (
        client.post(f"/api/projects/{project_id}/weekly-hours/approve", json=review, headers=world.lead_h).status_code
        == 403
    )
    assert (
        client.post(f"/api/projects/{project_id}/weekly-hours/approve", json=review, headers=world.bu_h).status_code
        == 200
    )


def test_weekly_submissions_say_whose_hours_the_bu_head_reviews(client, db, make, world):
    project_id = world.create_project()["id"]
    anita = db.get(models.Employee, world.lead_e.employee_id)
    make.time_entry(project_id, make.wbs_node(project_id, world.lead_e, engineer=anita), anita, 8)
    make.time_entry(project_id, make.wbs_node(project_id, world.lead_e, engineer=world.emp1), world.emp1, 8)
    _approve_booking(client, world, project_id, world.emp1, world.lead_h)  # Arjun works on it as an engineer
    week = {"week_start_date": WEEK.isoformat()}
    for headers in (world.lead_h, world.eng_h):
        submitted = client.post(f"/api/projects/{project_id}/weekly-hours/submit", json=week, headers=headers)
        assert submitted.status_code == 200, submitted.text

    rows = client.get(
        f"/api/projects/{project_id}/weekly-hours-submissions?week_start={WEEK}", headers=world.bu_h
    ).json()

    assert {row["employee_name"]: row["lead_hours"] for row in rows} == {"Anita Kumar": True, "Arjun Mehta": False}
