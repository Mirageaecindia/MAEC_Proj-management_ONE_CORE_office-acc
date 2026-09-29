"""The list endpoints run a fixed number of queries, however many rows they return.

A regression here means a per-row lookup crept back in (N+1)."""

from contextlib import contextmanager

import pytest
from sqlalchemy import event

from app.core.database import engine


@contextmanager
def counted():
    count = {"n": 0}

    def _count(*_args):
        count["n"] += 1

    event.listen(engine, "before_cursor_execute", _count)
    try:
        yield count
    finally:
        event.remove(engine, "before_cursor_execute", _count)


@pytest.fixture
def big_project(client, make, world):
    """40 tasks, each with 2 subtasks, spread over three engineers, plus bookings."""
    project_id = world.create_project()["id"]
    employees = [world.emp1, world.emp2, make.employee("Third Engineer")]
    for i in range(40):
        task = make.wbs_node(project_id, world.lead_e, engineer=employees[i % 3])
        for _ in range(2):
            make.wbs_node(project_id, world.lead_e, engineer=employees[i % 3], parent_id=task.id, estimated_hours=4)
    for employee in employees:
        response = client.post(
            f"/api/projects/{project_id}/resource-bookings",
            json={
                "employee_id": employee.id,
                "utilization_rate": 30,
                "start_date": "2026-10-01",
                "end_date": "2026-12-31",
            },
            headers=world.lead_h,
        )
        assert response.status_code == 200, response.text
    return project_id


def _get(client, headers, path):
    with counted() as count:
        response = client.get(path, headers=headers)
    assert response.status_code == 200, response.text
    return response.json(), count["n"]


def test_wbs_structure_is_a_handful_of_queries_for_120_nodes(client, world, big_project):
    rows, queries = _get(client, world.lead_h, f"/api/projects/{big_project}/wbs-structure")

    assert len(rows) == 120
    assert {row["level"] for row in rows} == {1, 2}
    assert all(row["assigned_engineer_name"] for row in rows)
    assert queries <= 10, queries


def test_bookings_and_timeline_do_not_query_per_row(client, world, big_project):
    bookings, booking_queries = _get(client, world.lead_h, f"/api/projects/{big_project}/resource-bookings")
    gantt, gantt_queries = _get(client, world.lead_h, f"/api/resource-bookings/gantt?project_id={big_project}")
    timeline, timeline_queries = _get(client, world.lead_h, f"/api/projects/{big_project}/timeline-logs")

    assert len(bookings) == 6  # three engineers and three leads
    assert all(b["total_allocation_pct"] >= 30 for b in bookings if b["role"] == "engineer")
    assert gantt["count"] == 6
    assert len(timeline["tasks"]) == 120
    assert (booking_queries, gantt_queries, timeline_queries) <= (10, 12, 14), (
        booking_queries,
        gantt_queries,
        timeline_queries,
    )
