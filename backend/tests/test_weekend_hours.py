"""Hours on Saturday and Sunday count like any other day (TODO N2): offices
work different weeks, and the Lead's approval decides which hours stand."""

from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import models
from app.domain.timesheets import entry_total
from app.repositories.work import WorkRepository


def test_entry_total_counts_all_seven_days():
    row = SimpleNamespace(mon_hours=1, tue_hours=1, wed_hours=1, thu_hours=1, fri_hours=1, sat_hours=2, sun_hours=3)

    assert entry_total(row) == 10


def test_approved_weekend_hours_count_toward_usage(client, db, make, world, governed):
    project_id, node_a, *_ = governed
    logged = make.time_entry(project_id, node_a, world.emp1, week=date(2026, 9, 14), sat_hours=6, sun_hours=4)
    approved = client.post(f"/api/time-log-entries/{logged.id}/approve", headers=world.lead_h)
    assert approved.status_code == 200, approved.text
    assert approved.json()["total_hours"] == 10

    summary = client.get(f"/api/projects/{project_id}/executive-dashboard", headers=world.bu_h).json()["summary"]

    assert summary["approved_hours"] == 40.0  # 30 already approved + 10 weekend hours
    assert WorkRepository(db).approved_hours(project_id) == 40.0


def test_tracked_session_on_a_saturday_is_kept(client, db, make, world, governed):
    project_id, node_a, *_ = governed
    subtask = make.wbs_node(project_id, world.lead_e, engineer=world.emp1, parent_id=node_a.id, estimated_hours=4)
    session_id = client.post(
        "/api/subtask-tracking/start", json={"subtask_id": subtask.id}, headers=world.eng_h
    ).json()["active_session"]["id"]
    today = datetime.now(UTC)
    last_saturday = (today - timedelta(days=(today.weekday() - 5) % 7 or 7)).replace(hour=9, minute=0)
    session = db.get(models.TimeSession, session_id)
    session.login_at, session.last_seen_at = last_saturday, last_saturday + timedelta(hours=1)
    db.commit()

    ended = client.post("/api/subtask-tracking/logout", headers=world.eng_h)

    assert ended.status_code == 200, ended.text
    entry = db.query(models.TimeLogEntry).filter_by(task_id=subtask.id).one()
    assert entry.sat_hours == 1.0
    assert entry_total(entry) == 1.0
