"""WBS statuses are normalized to the current flow names (TODO N8)."""

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

import models
from app.core.migrations import BACKEND_DIR, migrate
from app.domain.wbs import APPROVED, DONE, IN_PROGRESS, SUBMITTED, TO_DO, is_finished, normalize_status


@pytest.mark.parametrize(
    ("status", "is_subtask", "expected"),
    [
        ("Not Started", False, TO_DO),
        ("Blocked", True, TO_DO),
        ("In Progress", False, IN_PROGRESS),
        ("Submitted for Review", False, SUBMITTED),
        ("Completed", False, APPROVED),
        ("Completed", True, DONE),
        (None, False, TO_DO),
        ("In-Progress", True, IN_PROGRESS),  # current names pass through
    ],
)
def test_normalize_status(status, is_subtask, expected):
    assert normalize_status(status, is_subtask=is_subtask) == expected


def test_is_finished():
    assert is_finished(APPROVED) and is_finished(DONE) and is_finished("Completed")
    assert not is_finished(SUBMITTED) and not is_finished(IN_PROGRESS) and not is_finished(TO_DO)


def test_every_write_stores_a_canonical_status(client, db, make, world):
    project_id = world.create_project()["id"]
    created = client.post(
        f"/api/projects/{project_id}/wbs-nodes",
        json={"task_name": "Chiller plant", "phase": "Space Planning", "deliverable_status": "Not Started"},
        headers=world.lead_h,
    )
    assert created.status_code == 201, created.text
    assert created.json()["deliverable_status"] == TO_DO

    edited = client.put(
        f"/api/wbs-nodes/{created.json()['id']}",
        json={"task_name": "Chiller plant", "phase": "Space Planning", "deliverable_status": "In Progress"},
        headers=world.lead_h,
    )
    assert edited.json()["deliverable_status"] == IN_PROGRESS

    subtask = make.wbs_node(project_id, world.lead_e, parent_id=created.json()["id"])
    subtask.deliverable_status = "Completed"
    db.commit()
    assert db.get(models.WbsNode, subtask.id).deliverable_status == DONE


def test_migration_0002_converts_existing_rows(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    migrate(engine)
    with engine.begin() as connection:
        config = Config(str(BACKEND_DIR / "alembic.ini"))
        config.attributes["connection"] = connection
        command.downgrade(config, "0001")
        for node_id, parent_id, status in (
            (1, None, "Not Started"),
            (2, None, "Completed"),
            (3, 2, "Completed"),
            (4, None, "In Progress"),
            (5, None, "Submitted for Review"),
            (6, 2, "Blocked"),
        ):
            connection.execute(
                text(
                    "INSERT INTO wbs_nodes (id, project_id, parent_id, task_name, deliverable_status) "
                    "VALUES (:id, 1, :parent, 'Node', :status)"
                ),
                {"id": node_id, "parent": parent_id, "status": status},
            )

    migrate(engine)  # applies 0002

    with engine.connect() as connection:
        statuses = dict(connection.execute(text("SELECT id, deliverable_status FROM wbs_nodes")).all())
    assert statuses == {1: TO_DO, 2: APPROVED, 3: DONE, 4: IN_PROGRESS, 5: SUBMITTED, 6: TO_DO}
