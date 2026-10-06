"""What an engineer's WBS page lists: each task they work on, whole.

They see every subtask of those tasks and who has it, so they know whose subtask is
still open before the task can close; tasks they have no part in stay hidden.
"""

LIST = "/api/projects/{}/wbs-structure?include_ancestors=true"


def test_an_engineer_sees_their_tasks_whole_and_nothing_else(client, make, world, governed):
    project_id, *_ = governed
    node = lambda code, engineer, parent=None: make.wbs_node(  # noqa: E731
        project_id, world.lead_e, engineer=engineer, wbs_code=code, parent_id=parent.id if parent else None
    )
    mine = node("20", world.emp1)
    mine_a, colleague_a = node("20.1", world.emp1, mine), node("20.2", world.emp2, mine)
    theirs = node("21", world.emp2)  # the task is someone else's, one subtask is mine
    theirs_a, theirs_b = node("21.1", world.emp2, theirs), node("21.2", world.emp1, theirs)
    other = node("22", world.emp2)
    other_a = node("22.1", world.emp2, other)

    listed = client.get(LIST.format(project_id), headers=world.eng_h).json()

    codes = {n["wbs_code"]: n["assigned_engineer_name"] for n in listed}
    for item in (mine, mine_a, colleague_a, theirs, theirs_a, theirs_b):
        assert item.wbs_code in codes
    assert codes["20.2"] == "Ravi Kumar"  # the colleague's name is shown
    assert other.wbs_code not in codes and other_a.wbs_code not in codes
