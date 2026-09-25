"""backup_db.py: consistent SQLite snapshots with retention (TODO S7)."""

import sqlite3
from contextlib import closing

import pytest

from backup_db import backup


@pytest.fixture
def db_path(tmp_path):
    path = tmp_path / "promanage.db"
    with closing(sqlite3.connect(path)) as connection:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("CREATE TABLE projects (name TEXT)")
        connection.execute("INSERT INTO projects VALUES ('Hotel Tower')")
        connection.commit()
    return path


def test_backup_is_a_readable_copy(db_path, tmp_path):
    target = backup(db_path, tmp_path / "backups", keep=3)

    with closing(sqlite3.connect(target)) as copy:
        assert copy.execute("SELECT name FROM projects").fetchall() == [("Hotel Tower",)]


def test_only_the_newest_backups_are_kept(db_path, tmp_path):
    backups = tmp_path / "backups"
    made = [backup(db_path, backups, keep=2) for _ in range(4)]

    assert sorted(backups.glob("*.db")) == made[-2:]


def test_missing_database_is_reported(tmp_path):
    with pytest.raises(SystemExit, match="Database not found"):
        backup(tmp_path / "missing.db", tmp_path / "backups", keep=1)
