"""Subtask working-time rules: manual planned hours (1-4 only) and a
single-day Start/End pair. The Add WBS Subtask popup and the backend share
these rules; hours are never derived from dates for subtasks."""

import pytest


@pytest.fixture
def subtask_parent(make, world):
    project_id = world.create_project()["id"]
    node = make.wbs_node(project_id, world.lead_e)
    return project_id, node


def _create_subtask(client, headers, node_id, **overrides):
    payload = {
        "task_name": "Subtask",
        "estimated_hours": 2,
        "start_date": "2026-09-10",
        "end_date": "2026-09-10",
        "phase": "Space Planning",
    }
    payload.update(overrides)
    return client.post(f"/api/wbs-nodes/{node_id}/subtasks", json=payload, headers=headers)


@pytest.mark.parametrize("hours", [1, 2, 3, 4])
def test_subtask_accepts_manual_hours(client, world, subtask_parent, hours):
    _, node = subtask_parent

    response = _create_subtask(client, world.lead_h, node.id, estimated_hours=hours)

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["estimated_hours"] == hours
    assert body["parent_id"] == node.id


def test_engineer_can_create_subtask_with_manual_hours(client, make, world):
    project_id = world.create_project()["id"]
    booking = client.post(
        f"/api/projects/{project_id}/resource-bookings",
        json={
            "employee_id": world.emp1.id,
            "planned_hours": 40,
            "utilization_rate": 50,
            "start_date": "2026-09-01",
            "end_date": "2026-09-30",
        },
        headers=world.lead_h,
    )
    assert booking.status_code == 200, booking.text
    assert client.post(f"/api/projects/{project_id}/resource-bookings/submit", headers=world.lead_h).status_code == 200
    assert client.post(f"/api/projects/{project_id}/resource-bookings/approve", headers=world.bu_h).status_code == 200
    node = make.wbs_node(project_id, world.lead_e, engineer=world.emp1)

    response = _create_subtask(client, world.eng_h, node.id, estimated_hours=3)

    assert response.status_code == 201, response.text
    assert response.json()["estimated_hours"] == 3


def test_subtask_hours_are_manual_not_derived_from_dates(client, world, subtask_parent):
    # A single-day range would normally derive 8 hrs (1 working day x 8); the
    # manually entered value must be stored instead of recalculating.
    _, node = subtask_parent

    response = _create_subtask(
        client,
        world.lead_h,
        node.id,
        estimated_hours=4,
        start_date="2026-09-10",
        end_date="2026-09-10",
    )

    assert response.status_code == 201, response.text
    assert response.json()["estimated_hours"] == 4


def test_subtask_same_start_and_end_date_accepted(client, world, subtask_parent):
    _, node = subtask_parent

    response = _create_subtask(
        client,
        world.lead_h,
        node.id,
        estimated_hours=2,
        start_date="2026-09-15",
        end_date="2026-09-15",
    )

    assert response.status_code == 201, response.text
    assert response.json()["start_date"] == "2026-09-15"
    assert response.json()["end_date"] == "2026-09-15"


def test_subtask_different_start_and_end_rejected(client, world, subtask_parent):
    _, node = subtask_parent

    response = _create_subtask(
        client,
        world.lead_h,
        node.id,
        estimated_hours=2,
        start_date="2026-09-10",
        end_date="2026-09-11",
    )

    assert response.status_code == 400, response.text
    assert "single working day" in response.json()["detail"]


def test_subtask_rejects_zero_hours(client, world, subtask_parent):
    _, node = subtask_parent

    response = _create_subtask(client, world.lead_h, node.id, estimated_hours=0)

    assert response.status_code == 400, response.text
    assert "Subtask planned hours must be between 1 and 4 hours." in response.json()["detail"]


def test_subtask_rejects_hours_over_four(client, world, subtask_parent):
    _, node = subtask_parent

    response = _create_subtask(client, world.lead_h, node.id, estimated_hours=5)

    assert response.status_code == 400, response.text
    assert response.json()["detail"] == "Subtask planned hours must be between 1 and 4 hours."


def test_subtask_rejects_negative_hours(client, world, subtask_parent):
    _, node = subtask_parent

    response = _create_subtask(client, world.lead_h, node.id, estimated_hours=-1)

    assert response.status_code == 400, response.text
    assert "Subtask planned hours must be between 1 and 4 hours." in response.json()["detail"]


def test_subtask_rejects_missing_hours(client, world, subtask_parent):
    _, node = subtask_parent

    response = _create_subtask(client, world.lead_h, node.id, estimated_hours=None)

    assert response.status_code == 400, response.text
    assert "Subtask planned hours must be between 1 and 4 hours." in response.json()["detail"]


def test_subtask_rejects_fractional_hours(client, world, subtask_parent):
    _, node = subtask_parent

    response = _create_subtask(client, world.lead_h, node.id, estimated_hours=2.5)

    assert response.status_code == 422, response.text


def test_main_task_estimated_hours_are_still_derived_from_dates(client, world):
    # The 8-hrs-per-working-day derivation stays for MAIN tasks only.
    project = world.create_project()
    payload = {
        "task_name": "Main task",
        "start_date": "2026-09-01",
        "end_date": "2026-09-30",
        "phase": "Space Planning",
    }

    response = client.post(f"/api/projects/{project['id']}/wbs-nodes", json=payload, headers=world.lead_h)

    assert response.status_code == 201, response.text
    assert response.json()["estimated_hours"] == 176  # 22 weekdays x 8
