"""Tracked time can't exceed the wall-clock time since the session started (TODO S4)."""

from datetime import UTC, datetime, timedelta

import pytest

import models


@pytest.fixture
def session_id(client, make, world, governed):
    project_id, node_a, *_ = governed
    subtask = make.wbs_node(project_id, world.lead_e, engineer=world.emp1, parent_id=node_a.id, estimated_hours=4)
    started = client.post("/api/subtask-tracking/start", json={"subtask_id": subtask.id}, headers=world.eng_h)
    assert started.status_code == 201, started.text
    return started.json()["id"]


def _started_ago(db, session_id, minutes):
    session = db.get(models.TimeSession, session_id)
    session.login_at = datetime.now(UTC) - timedelta(minutes=minutes)
    db.commit()


def test_sync_caps_inflated_active_time(client, db, world, session_id):
    response = client.post(
        f"/api/subtask-tracking/{session_id}/sync", json={"active_seconds": 3600}, headers=world.eng_h
    )

    assert response.status_code == 200, response.text
    assert response.json()["active_seconds"] < 60  # the session started a moment ago


def test_end_caps_inflated_active_time(client, db, world, session_id):
    _started_ago(db, session_id, minutes=10)

    response = client.post(
        f"/api/subtask-tracking/{session_id}/end", json={"active_seconds": 8 * 3600}, headers=world.eng_h
    )

    assert response.status_code == 200, response.text
    assert 600 <= response.json()["session"]["active_seconds"] < 660


def test_genuinely_elapsed_time_is_kept(client, db, world, session_id):
    _started_ago(db, session_id, minutes=90)

    synced = client.post(f"/api/subtask-tracking/{session_id}/sync", json={"active_seconds": 3600}, headers=world.eng_h)
    ended = client.post(f"/api/subtask-tracking/{session_id}/end", json={"active_seconds": 3700}, headers=world.eng_h)

    assert synced.json()["active_seconds"] == 3600
    assert ended.json()["session"]["active_seconds"] == 3700
