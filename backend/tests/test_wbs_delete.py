"""Deleting tasks and subtasks, one or many (app/services/wbs_delete.py).

Leads delete tasks and subtasks; engineers only subtasks under their own tasks.
Worked hours are never deleted: an open session is banked first and the day
rows keep the subtask's name.
"""

from datetime import UTC, date, datetime, timedelta

import models
from app.domain.timesheets import total_hours
from tests.test_query_counts import counted

BULK = "/api/projects/{}/wbs-nodes/delete"


def _tree(make, world, project_id, engineer=None, created_by=None):
    """A task with two subtasks, created by the lead unless `created_by` says otherwise."""
    creator = (created_by or world.lead_e).id
    task = make.wbs_node(project_id, world.lead_e, engineer=engineer or world.emp1, created_by_user_id=world.lead_e.id)
    subtasks = [
        make.wbs_node(
            project_id,
            world.lead_e,
            engineer=engineer or world.emp1,
            parent_id=task.id,
            estimated_hours=4,
            created_by_user_id=creator,
        )
        for _ in range(2)
    ]
    return task, subtasks


def _ids(db, project_id):
    return {n.id for n in db.query(models.WbsNode).filter_by(project_id=project_id)}


def test_engineer_deletes_own_subtasks_but_never_a_task(client, db, make, world, governed):
    project_id, *_ = governed
    task, (mine, _) = _tree(make, world, project_id, created_by=world.engineer)

    refused = client.delete(f"/api/wbs-nodes/{task.id}", headers=world.eng_h)
    assert refused.status_code == 403 and "only the project's lead deletes tasks" in refused.json()["detail"]

    deleted = client.delete(f"/api/wbs-nodes/{mine.id}", headers=world.eng_h)
    assert deleted.status_code == 200, deleted.text
    assert deleted.json() == {"tasks": 0, "subtasks": 1, "hours_kept": 0.0, "deleted_nodes": [mine.id]}
    assert mine.id not in _ids(db, project_id) and task.id in _ids(db, project_id)


def test_engineer_cannot_delete_a_subtask_the_lead_planned_for_them(client, db, make, world, governed):
    project_id, *_ = governed
    task, (planned, _) = _tree(make, world, project_id)  # assigned to the engineer, created by the lead

    response = client.delete(f"/api/wbs-nodes/{planned.id}", headers=world.eng_h)

    assert response.status_code == 403 and "subtasks you created yourself" in response.json()["detail"]
    assert planned.id in _ids(db, project_id)


def test_a_subtask_the_engineer_adds_through_the_app_is_theirs_to_delete(client, db, make, world, governed):
    project_id, *_ = governed
    task, _ = _tree(make, world, project_id)
    day = "2026-09-15"
    created = client.post(
        f"/api/wbs-nodes/{task.id}/subtasks",
        json={"task_name": "Check the riser drawing", "estimated_hours": 4, "start_date": day, "end_date": day},
        headers=world.eng_h,
    )
    assert created.status_code == 201, created.text
    listed = client.get(f"/api/projects/{project_id}/wbs-structure?include_ancestors=true", headers=world.eng_h).json()
    assert {n["id"]: n["created_by_user_id"] for n in listed}[created.json()["id"]] == world.engineer.id

    assert client.delete(f"/api/wbs-nodes/{created.json()['id']}", headers=world.eng_h).status_code == 200


def test_bu_head_and_other_leads_cannot_delete(client, make, world, governed):
    project_id, *_ = governed
    task, _ = _tree(make, world, project_id)

    assert client.delete(f"/api/wbs-nodes/{task.id}", headers=world.bu_h).status_code == 403
    assert client.delete(f"/api/wbs-nodes/{task.id}", headers=world.other_lead_h).status_code == 403


def test_lead_deletes_tasks_and_subtasks_together(client, db, make, world, governed):
    project_id, *_ = governed
    task_a, subs_a = _tree(make, world, project_id)
    task_b, (sub_b1, sub_b2) = _tree(make, world, project_id)
    keep, _ = _tree(make, world, project_id)
    expected = {task_a.id, *(s.id for s in subs_a), sub_b1.id}

    response = client.post(BULK.format(project_id), json={"node_ids": [task_a.id, sub_b1.id]}, headers=world.lead_h)

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["tasks"], body["subtasks"]) == (1, 3)  # task A with its two subtasks, plus one of B's
    assert set(body["deleted_nodes"]) == expected
    assert _ids(db, project_id) >= {task_b.id, sub_b2.id, keep.id}
    assert not _ids(db, project_id) & set(body["deleted_nodes"])


def test_a_selection_is_all_or_nothing(client, db, make, world, governed):
    project_id, *_ = governed
    task, (mine, _) = _tree(make, world, project_id, created_by=world.engineer)
    before = _ids(db, project_id)

    response = client.post(BULK.format(project_id), json={"node_ids": [mine.id, task.id]}, headers=world.eng_h)

    assert response.status_code == 403
    assert response.json()["detail"].startswith("Nothing was deleted. ")
    assert task.task_name in response.json()["detail"]
    assert _ids(db, project_id) == before


def test_ids_from_another_project_or_gone_are_refused(client, db, make, world, governed):
    project_id, *_ = governed
    other_id = world.create_project()["id"]
    foreign = make.wbs_node(other_id, world.lead_e)
    task, _ = _tree(make, world, project_id)

    response = client.post(BULK.format(project_id), json={"node_ids": [task.id, foreign.id]}, headers=world.lead_h)
    assert response.status_code == 404
    gone = client.post(BULK.format(project_id), json={"node_ids": [task.id, 999999]}, headers=world.lead_h)
    assert gone.status_code == 404
    assert client.post(BULK.format(project_id), json={"node_ids": []}, headers=world.lead_h).status_code == 422
    assert task.id in _ids(db, project_id) and foreign.id in _ids(db, other_id)


def test_worked_hours_survive_the_subtask_and_keep_counting(client, db, make, world, governed):
    project_id, node_a, node_b, pending = governed
    task, (sub, _) = _tree(make, world, project_id)
    make.time_entry(project_id, sub, world.emp1, 5, status="approved", day=date(2026, 9, 21))
    make.time_entry(project_id, sub, world.emp1, 2.5, day=date(2026, 9, 22))
    sub_id, sub_name = sub.id, sub.task_name
    engineer_hours = lambda: [  # noqa: E731
        (e["logged_hours"], e["approved_hours"], e["pending_hours"])
        for e in client.get(f"/api/projects/{project_id}/work-summary", headers=world.bu_h).json()["engineers"]
        if e["employee_id"] == world.emp1.id
    ]
    hours_before = engineer_hours()

    response = client.delete(f"/api/wbs-nodes/{task.id}", headers=world.lead_h)

    assert response.status_code == 200, response.text
    assert response.json()["hours_kept"] == 7.5
    rows = db.query(models.TimeLogEntry).filter_by(task_id=sub_id).all()
    assert [(r.hours, r.approval_status, r.task_name) for r in rows] == [
        (5, "approved", sub_name),
        (2.5, "pending_review", sub_name),
    ]
    assert engineer_hours() == hours_before == [(50 + 7.5, 30 + 5, 20 + 2.5)]  # the engineer's working time stands

    # The rows remember the task's lead: a routine cleanup does not move approvals to the BU Head.
    timesheet = client.get(f"/api/projects/{project_id}/timesheet?week_start=2026-09-21", headers=world.lead_h).json()
    assert [(row["task_name"], row["hours"], row["can_review"]) for row in timesheet] == [
        (sub_name, 5, True),
        (sub_name, 2.5, True),
    ]
    for_bu_head = client.get(f"/api/projects/{project_id}/timesheet?week_start=2026-09-21", headers=world.bu_h).json()
    assert [row["can_review"] for row in for_bu_head] == [False, False]  # the BU Head does not need to act
    assert client.post(f"/api/time-log-entries/{timesheet[1]['id']}/approve", headers=world.bu_h).status_code == 403
    approve = client.post(f"/api/time-log-entries/{timesheet[1]['id']}/approve", headers=world.lead_h)
    assert approve.status_code == 200, approve.text
    db.expire_all()
    assert total_hours(db.query(models.TimeLogEntry).filter_by(employee_id=world.emp1.id), "approved") == 30 + 7.5


def test_an_open_session_on_a_deleted_subtask_is_banked_first(client, db, make, world, governed):
    project_id, *_ = governed
    task, (sub, _) = _tree(make, world, project_id, created_by=world.engineer)
    now = datetime.now(UTC)
    make._save(
        models.TimeSession(
            project_id=project_id,
            task_id=task.id,
            subtask_id=sub.id,
            employee_id=world.emp1.id,
            login_at=now - timedelta(hours=2),
            last_seen_at=now,
        )
    )

    response = client.delete(f"/api/wbs-nodes/{sub.id}", headers=world.eng_h)

    assert response.status_code == 200, response.text
    assert response.json()["hours_kept"] == 2.0
    assert db.query(models.TimeSession).filter_by(subtask_id=sub.id).count() == 0
    banked = db.query(models.TimeLogEntry).filter_by(task_id=sub.id).one()
    assert (banked.hours, banked.approval_status, banked.task_name) == (2.0, "pending_review", sub.task_name)


def test_deleting_many_costs_a_fixed_number_of_queries(client, make, world, governed):
    project_id, *_ = governed
    few = [_tree(make, world, project_id)[0].id for _ in range(2)]
    many = [_tree(make, world, project_id)[0].id for _ in range(20)]

    with counted() as count:
        assert client.post(BULK.format(project_id), json={"node_ids": few}, headers=world.lead_h).status_code == 200
    few_queries = count["n"]
    with counted() as count:
        assert client.post(BULK.format(project_id), json={"node_ids": many}, headers=world.lead_h).status_code == 200

    # One query per level of the tree (task, subtask, sub-subtask), never per item.
    assert count["n"] == few_queries <= 15, (few_queries, count["n"])
