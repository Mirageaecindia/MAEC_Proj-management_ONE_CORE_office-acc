"""A task's engineer carries down to its subtasks (main.cascade_engineer, decided 2026-10-09)."""

import models


def _task_edit(task, engineer_id):
    return {
        "task_name": task.task_name,
        "wbs_code": task.wbs_code,
        "assigned_engineer_id": engineer_id,
        "start_date": task.start_date.isoformat(),
        "target_due_date": task.target_due_date.isoformat(),
        "deliverable_status": task.deliverable_status,
    }


def test_the_task_engineer_carries_down_to_the_subtasks_that_follow_it(client, db, make, world):
    project_id = world.create_project()["id"]
    ravi, meera = world.emp2, make.employee("Meera Iyer")
    task = make.wbs_node(project_id, world.lead_e, engineer=world.emp1, wbs_code="1.")
    sub = lambda code, engineer=None, **extra: make.wbs_node(  # noqa: E731
        project_id, world.lead_e, engineer=engineer, parent_id=task.id, wbs_code=code, estimated_hours=4, **extra
    )
    unassigned = sub("1.1")
    following = sub("1.2", world.emp1)  # had the task's engineer
    chosen = sub("1.3", ravi)  # given to someone else on purpose
    started = sub("1.4", deliverable_status="In-Progress")
    step = make.wbs_node(project_id, world.lead_e, parent_id=unassigned.id, wbs_code="1.1.1")
    ids = {
        "unassigned": unassigned.id,
        "following": following.id,
        "chosen": chosen.id,
        "started": started.id,
        "step": step.id,
    }

    response = client.put(f"/api/wbs-nodes/{task.id}", json=_task_edit(task, meera.id), headers=world.lead_h)

    assert response.status_code == 200, response.text
    db.expire_all()
    engineer = {name: db.get(models.WbsNode, node_id).assigned_engineer_id for name, node_id in ids.items()}
    assert engineer == {
        "unassigned": meera.id,
        "following": meera.id,
        "chosen": ravi.id,  # kept: a deliberate choice
        "started": None,  # kept: started work keeps its plan
        "step": meera.id,  # the sub-subtask follows too
    }


def test_a_subtask_can_still_be_given_to_someone_else_afterwards(client, db, make, world):
    project_id = world.create_project()["id"]
    task = make.wbs_node(project_id, world.lead_e, wbs_code="2.")
    subtask = make.wbs_node(project_id, world.lead_e, parent_id=task.id, wbs_code="2.1", estimated_hours=4)
    client.put(f"/api/wbs-nodes/{task.id}", json=_task_edit(task, world.emp1.id), headers=world.lead_h)
    db.refresh(subtask)
    assert subtask.assigned_engineer_id == world.emp1.id

    edit = {
        "task_name": subtask.task_name,
        "parent_id": task.id,
        "assigned_engineer_id": world.emp2.id,
        "estimated_hours": 4,
        "start_date": subtask.start_date.isoformat(),
        "target_due_date": subtask.target_due_date.isoformat(),
    }
    assert client.put(f"/api/wbs-nodes/{subtask.id}", json=edit, headers=world.lead_h).status_code == 200
    db.expire_all()
    assert db.get(models.WbsNode, subtask.id).assigned_engineer_id == world.emp2.id
