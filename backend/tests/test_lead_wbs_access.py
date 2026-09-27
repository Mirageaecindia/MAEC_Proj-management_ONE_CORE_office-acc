"""Lead WBS writes are limited to projects the Lead is allocated to (TODO S3),
and deleting a node removes its tracking sessions (TODO C10)."""

from datetime import UTC, datetime

import pytest

import models


@pytest.fixture
def project_id(world):
    return world.create_project()["id"]


def _create(client, headers, project_id, **fields):
    return client.post(
        f"/api/projects/{project_id}/wbs-nodes",
        json={"task_name": "Chilled water layout", "phase": "Space Planning", **fields},
        headers=headers,
    )


def test_unallocated_lead_cannot_create_update_or_delete_nodes(client, db, make, world, project_id):
    node = make.wbs_node(project_id, world.lead_e)

    assert _create(client, world.other_lead_h, project_id).status_code == 403
    update = client.put(
        f"/api/wbs-nodes/{node.id}",
        json={"task_name": "Renamed", "phase": "Space Planning"},
        headers=world.other_lead_h,
    )
    assert update.status_code == 403
    assert client.delete(f"/api/wbs-nodes/{node.id}", headers=world.other_lead_h).status_code == 403

    db.expire_all()
    assert db.get(models.WbsNode, node.id).task_name == node.task_name


def test_allocated_lead_can_create_update_and_delete_nodes(client, world, project_id):
    created = _create(client, world.lead_h, project_id)
    assert created.status_code == 201, created.text
    node_id = created.json()["id"]

    update = client.put(
        f"/api/wbs-nodes/{node_id}", json={"task_name": "Renamed", "phase": "Space Planning"}, headers=world.lead_h
    )
    assert update.status_code == 200, update.text
    assert client.delete(f"/api/wbs-nodes/{node_id}", headers=world.lead_h).status_code == 200


def test_missing_project_is_404(client, world):
    assert _create(client, world.lead_h, 999999).status_code == 404


def test_deleting_a_node_removes_its_tracking_sessions(client, db, make, world, project_id):
    task = make.wbs_node(project_id, world.lead_e, engineer=world.emp1)
    subtask = make.wbs_node(project_id, world.lead_e, engineer=world.emp1, parent_id=task.id)
    make._save(
        models.TimeSession(
            project_id=project_id,
            task_id=task.id,
            subtask_id=subtask.id,
            employee_id=world.emp1.id,
            login_at=datetime.now(UTC),
            last_seen_at=datetime.now(UTC),
        )
    )

    assert client.delete(f"/api/wbs-nodes/{task.id}", headers=world.lead_h).status_code == 200

    assert db.query(models.TimeSession).filter_by(project_id=project_id).count() == 0


def test_legacy_gantt_task_endpoints_are_gone(client, world, project_id):
    assert client.get(f"/api/projects/{project_id}/wbs-tasks", headers=world.bu_h).status_code == 404
    assert client.put("/api/wbs-tasks/1", json={}, headers=world.lead_h).status_code == 404
