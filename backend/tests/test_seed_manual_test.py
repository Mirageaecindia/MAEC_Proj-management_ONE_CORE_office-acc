"""The manual-test seed only ever writes a scratch database (seed_manual_test.py).

These tests cover the guard; the seeding itself is exercised by running the script.
"""

import sqlite3

import pytest

from seed_manual_test import DEFAULT_DEV_DATABASE, MARKER_PROJECT_CODE, Refused, dev_database_paths, safe_target


def _database(path, project_codes):
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE projects (project_code TEXT)")
        connection.executemany("INSERT INTO projects VALUES (?)", [(code,) for code in project_codes])
    return path


def test_the_target_must_be_passed_and_be_a_db_file(tmp_path):
    with pytest.raises(Refused, match="explicitly"):
        safe_target(None, False, set())
    with pytest.raises(Refused, match="not a database URL"):
        safe_target("postgresql://user@host/maec", False, set())
    with pytest.raises(Refused, match="must be a .db file"):
        safe_target(str(tmp_path / "scratch.sqlite"), False, set())

    assert safe_target(str(tmp_path / "manual_test.db"), False, set()) == (tmp_path / "manual_test.db").resolve()


def test_the_development_database_is_refused_however_it_is_configured(tmp_path):
    from_env = tmp_path / "from_env.db"
    from_file = tmp_path / "from_file.db"
    env_file = tmp_path / ".env"
    env_file.write_text(
        f'AZURE_CLIENT_SECRET=not-read\nDATABASE_URL="sqlite:///{from_file.as_posix()}"\n', encoding="utf-8"
    )

    dev = dev_database_paths({"DATABASE_URL": f"sqlite:///{from_env.as_posix()}"}, env_file)

    assert dev == {DEFAULT_DEV_DATABASE.resolve(), from_env.resolve(), from_file.resolve()}
    for path in dev:
        with pytest.raises(Refused, match="development database"):
            safe_target(str(path), True, dev)  # even with --reset


def test_an_existing_file_is_rebuilt_only_if_this_script_made_it(tmp_path):
    real = _database(tmp_path / "real.db", ["PRJ-001", MARKER_PROJECT_CODE])
    scratch = _database(tmp_path / "scratch.db", [MARKER_PROJECT_CODE])
    not_a_database = tmp_path / "notes.db"
    not_a_database.write_text("hello", encoding="utf-8")

    with pytest.raises(Refused, match="already exists"):
        safe_target(str(scratch), False, set())
    with pytest.raises(Refused, match="was not made by this script"):
        safe_target(str(real), True, set())
    with pytest.raises(Refused, match="was not made by this script"):
        safe_target(str(not_a_database), True, set())

    assert safe_target(str(scratch), True, set()) == scratch.resolve()
