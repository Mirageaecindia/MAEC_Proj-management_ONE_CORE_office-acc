"""What an engineer's WBS page lists: the project's whole WBS (decided 2026-10-14).

Every engineer and lead on the project sees every task and subtask and who has it, and opens
any of them to view it. Working on one stays theirs alone: a colleague's subtask takes no status
change, comment or Login from them, and another lead's task no lead action.
"""

from datetime import UTC, datetime

LIST = "/api/projects/{}/wbs-structure?include_ancestors=true"
START = "/api/subtask-tracking/start"


def test_an_engineer_sees_and_opens_the_whole_wbs(client, make, world, governed):
    project_id, *_ = governed
    node = lambda code, engineer, parent=None: make.wbs_node(  # noqa: E731
        project_id, world.lead_e, engineer=engineer, wbs_code=code, parent_id=parent.id if parent else None
    )
    mine = node("20", world.emp1)
    mine_a, colleague_a = node("20.1", world.emp1, mine), node("20.2", world.emp2, mine)
    theirs = node("21", world.emp2)  # the task is someone else's, one subtask is mine
    theirs_a, theirs_b = node("21.1", world.emp2, theirs), node("21.2", world.emp1, theirs)
    other = node("22", world.emp2)  # no part of it is mine
    other_a = node("22.1", world.emp2, other)
    unassigned = node("23", None)

    listed = client.get(LIST.format(project_id), headers=world.eng_h).json()

    codes = {n["wbs_code"]: n["assigned_engineer_name"] for n in listed}
    for item in (mine, mine_a, colleague_a, theirs, theirs_a, theirs_b, other, other_a, unassigned):
        assert item.wbs_code in codes
    assert codes["20.2"] == "Ravi Kumar"  # the colleague's name is shown
    assert codes["22.1"] == "Ravi Kumar"

    assert client.get(f"/api/wbs-nodes/{mine_a.id}", headers=world.eng_h).status_code == 200
    assert client.get(f"/api/wbs-nodes/{other_a.id}", headers=world.eng_h).status_code == 200  # to view it


def test_the_wbs_lists_when_work_really_started_and_finished(client, db, make, world, governed):
    project_id, *_ = governed
    task = make.wbs_node(project_id, world.lead_e, engineer=world.emp1, wbs_code="30")
    started = make.wbs_node(project_id, world.lead_e, engineer=world.emp1, wbs_code="30.1", parent_id=task.id)
    started.actual_start_datetime = datetime(2026, 9, 2, 4, 30, tzinfo=UTC)
    started.actual_end_datetime = datetime(2026, 9, 2, 12, 0, tzinfo=UTC)
    db.commit()

    for headers in (world.eng_h, world.lead_h):
        rows = {n["wbs_code"]: n for n in client.get(LIST.format(project_id), headers=headers).json()}
        assert datetime.fromisoformat(rows["30.1"]["actual_start_datetime"]) == datetime(2026, 9, 2, 4, 30, tzinfo=UTC)
        assert datetime.fromisoformat(rows["30.1"]["actual_end_datetime"]) == datetime(2026, 9, 2, 12, 0, tzinfo=UTC)
        assert rows["30"]["actual_start_datetime"] is None  # not started yet
        assert rows["30"]["actual_end_datetime"] is None


def test_everyone_views_every_node_but_works_only_on_their_own(client, make, world, governed):
    """The screenshot's case end to end: a lead opens another lead's task, and an engineer a
    colleague's subtask, to view them; neither can act on them. The actual dates the status
    changes record show in the list for every role."""
    project_id, *_ = governed
    anita_task = make.wbs_node(project_id, world.lead_e, engineer=world.emp1, wbs_code="40")
    anita_sub = make.wbs_node(
        project_id,
        world.lead_e,
        engineer=world.emp1,
        wbs_code="40.1",
        parent_id=anita_task.id,
        start_date=None,
        target_due_date=None,
    )
    priya_task = make.wbs_node(project_id, world.lead_m, engineer=world.emp2, wbs_code="41")
    priya_sub = make.wbs_node(project_id, world.lead_m, engineer=world.emp2, wbs_code="41.1", parent_id=priya_task.id)
    priya_h = make.headers(world.lead_m)

    for status in ("In-Progress", "Done"):  # the engineer works their subtask through the app
        moved = client.post(
            f"/api/wbs-nodes/{anita_sub.id}/advance-status", json={"new_status": status}, headers=world.eng_h
        )
        assert moved.status_code == 200, moved.text

    for headers in (world.eng_h, priya_h, world.lead_h, world.bu_h):
        rows = {n["wbs_code"]: n for n in client.get(LIST.format(project_id), headers=headers).json()}
        assert {"40", "40.1", "41", "41.1"} <= rows.keys()  # the whole WBS, whoever leads or works it
        assert rows["40.1"]["actual_start_datetime"] and rows["40.1"]["actual_end_datetime"]
        assert rows["41"]["actual_start_datetime"] is None
        for node in (anita_task, anita_sub, priya_task, priya_sub):  # and opens any of it to view
            viewed = client.get(f"/api/wbs-nodes/{node.id}", headers=headers)
            assert viewed.status_code == 200, viewed.text

    def detail(node, headers):
        return client.get(f"/api/wbs-nodes/{node.id}", headers=headers).json()

    assert detail(anita_task, world.lead_h)["leads_this"] is True
    assert detail(anita_task, priya_h)["leads_this"] is False  # viewed, not hers to act on
    assert detail(priya_task, priya_h)["leads_this"] is True
    assert detail(anita_task, world.eng_h)["leads_this"] is False

    # A colleague's subtask: no status change, comment or Login.
    advance = client.post(
        f"/api/wbs-nodes/{priya_sub.id}/advance-status", json={"new_status": "In-Progress"}, headers=world.eng_h
    )
    assert advance.status_code == 403
    comment = client.post(f"/api/wbs-nodes/{priya_sub.id}/comments", json={"comment": "hi"}, headers=world.eng_h)
    assert comment.status_code == 403
    assert client.post(START, json={"subtask_id": priya_sub.id}, headers=world.eng_h).status_code == 403
    # Another lead's subtask and task: no lead action either.
    advance = client.post(
        f"/api/wbs-nodes/{priya_sub.id}/advance-status", json={"new_status": "In-Progress"}, headers=world.lead_h
    )
    assert advance.status_code == 403
    approve = client.post(
        f"/api/wbs-nodes/{priya_task.id}/approve", json={"new_status": "Approved"}, headers=world.lead_h
    )
    assert approve.status_code == 403
    assert detail(priya_sub, world.lead_h)["deliverable_status"] == "To Do"  # nothing changed
