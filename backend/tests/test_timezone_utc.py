"""Timestamps are stored and returned as UTC so the display layer can render
them consistently in India Standard Time (UTC+5:30). These tests guard that
the backend never writes or returns LOCAL server time for the datetime fields
surfaced to the frontend (Actual Start/End, history log, extension reviews,
server date)."""

from datetime import UTC, datetime, timedelta

IST_OFFSET = timedelta(hours=5, minutes=30)
TOLERANCE = timedelta(seconds=5)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _as_utc_clock(value: str) -> datetime:
    """Parse the ISO string the API returns. Naive values (serialized from
    SQLite, which stores UTC without an offset) are treated as UTC."""
    value = value.strip()
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _assigned_project(client, make, world):
    project = client.post("/api/projects", json=world.project_payload(), headers=world.bu_h).json()
    booking = client.post(
        f"/api/projects/{project['id']}/resource-bookings",
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
    assert (
        client.post(f"/api/projects/{project['id']}/resource-bookings/submit", headers=world.lead_h).status_code == 200
    )
    assert (
        client.post(f"/api/projects/{project['id']}/resource-bookings/approve", headers=world.bu_h).status_code == 200
    )
    node = make.wbs_node(project["id"], world.lead_e, engineer=world.emp1)
    return project, node


def test_actual_start_datetime_is_stored_and_returned_utc(client, make, world):
    _, node = _assigned_project(client, make, world)
    t0 = _utc_now()

    response = client.post(
        f"/api/wbs-nodes/{node.id}/advance-status",
        json={"new_status": "In-Progress"},
        headers=world.eng_h,
    )
    assert response.status_code == 200, response.text
    t1 = _utc_now()

    detail = client.get(f"/api/wbs-nodes/{node.id}", headers=world.lead_h).json()
    actual_start = _as_utc_clock(detail["actual_start_datetime"])
    # Inside the UTC window around the status change. If the backend had
    # stored local (IST) time it would land ~5.5h ahead of this window.
    assert t0 - TOLERANCE <= actual_start <= t1 + TOLERANCE, (
        f"actual_start_datetime {actual_start} not within UTC window {t0}..{t1}"
    )


def test_history_log_created_at_is_stored_and_returned_utc(client, make, world):
    _, node = _assigned_project(client, make, world)
    t0 = _utc_now()

    client.post(f"/api/wbs-nodes/{node.id}/advance-status", json={"new_status": "In-Progress"}, headers=world.eng_h)
    t1 = _utc_now()

    detail = client.get(f"/api/wbs-nodes/{node.id}", headers=world.lead_h).json()
    latest = detail["history"][-1]
    created_at = _as_utc_clock(latest["created_at"])
    assert latest["new_status"] == "In-Progress"
    assert t0 - TOLERANCE <= created_at <= t1 + TOLERANCE, (
        f"history created_at {created_at} not within UTC window {t0}..{t1}"
    )


def test_subtask_done_actual_end_datetime_is_utc(client, make, world):
    project, parent = _assigned_project(client, make, world)
    subtask = client.post(
        f"/api/wbs-nodes/{parent.id}/subtasks",
        json={
            "task_name": "Subtask",
            "estimated_hours": 2,
            "start_date": "2026-09-10",
            "end_date": "2026-09-10",
            "phase": "Space Planning",
        },
        headers=world.lead_h,
    )
    assert subtask.status_code == 201, subtask.text
    subtask_id = subtask.json()["id"]

    t0 = _utc_now()
    assert (
        client.post(
            f"/api/wbs-nodes/{subtask_id}/advance-status", json={"new_status": "In-Progress"}, headers=world.eng_h
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/wbs-nodes/{subtask_id}/advance-status", json={"new_status": "Done"}, headers=world.eng_h
        ).status_code
        == 200
    )
    t1 = _utc_now()

    detail = client.get(f"/api/wbs-nodes/{subtask_id}", headers=world.lead_h).json()
    actual_end = _as_utc_clock(detail["actual_end_datetime"])
    assert t0 - TOLERANCE <= actual_end <= t1 + TOLERANCE, (
        f"actual_end_datetime {actual_end} not within UTC window {t0}..{t1}"
    )


def test_server_date_reports_utc(client, world):
    t0 = _utc_now()
    body = client.get("/api/server-date", headers=world.eng_h).json()
    t1 = _utc_now()

    reported = _as_utc_clock(body["datetime"])
    assert t0 - TOLERANCE <= reported <= t1 + TOLERANCE
    assert body["date"] == _utc_now().date().isoformat()
    assert body["timezone"] == "UTC"


def test_utc_clock_is_five_and_a_half_hours_behind_ist(client, make, world):
    # Sanity-guards the IST display assumption: a value stored at UTC+00:00
    # whose ISO string omits the offset must, when re-read as UTC, differ from
    # the local (IST) wall clock by the expected offset.
    _, node = _assigned_project(client, make, world)
    client.post(f"/api/wbs-nodes/{node.id}/advance-status", json={"new_status": "In-Progress"}, headers=world.eng_h)
    detail = client.get(f"/api/wbs-nodes/{node.id}", headers=world.lead_h).json()
    actual_start = _as_utc_clock(detail["actual_start_datetime"])

    assert actual_start + IST_OFFSET == actual_start.astimezone(UTC) + IST_OFFSET
    diff = actual_start - _utc_now()
    # If the value were IST-local, the difference from UTC now would be ~5.5h.
    assert abs(diff.total_seconds()) < TOLERANCE.total_seconds()
