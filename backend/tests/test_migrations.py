"""Alembic migrations (TODO E4).

The test database itself is built by `migrate` when `main` is imported, so the
whole suite runs on a migrated schema.
"""

import pytest
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text

import models  # noqa: F401  (registers every table on Base.metadata)
from app.core.database import Base, engine
from app.core.migrations import BACKEND_DIR, migrate

HEAD = ScriptDirectory.from_config(Config(str(BACKEND_DIR / "alembic.ini"))).get_current_head()


def _revision(db_engine):
    with db_engine.connect() as connection:
        return MigrationContext.configure(connection).get_current_revision()


def _differences(db_engine):
    with db_engine.connect() as connection:
        return compare_metadata(MigrationContext.configure(connection), Base.metadata)


def test_migrations_produce_exactly_the_models_schema():
    # Fails when a model changes without a migration: run
    # `alembic revision --autogenerate -m "..."`, review it, commit it.
    assert _revision(engine) == HEAD
    assert _differences(engine) == []


def test_fresh_database_is_built_by_the_migrations(tmp_path):
    fresh = create_engine(f"sqlite:///{tmp_path / 'fresh.db'}")

    migrate(fresh)
    migrate(fresh)  # idempotent

    assert _revision(fresh) == HEAD
    assert _differences(fresh) == []


@pytest.fixture
def pre_alembic(tmp_path):
    """A database as the old startup code left it: no alembic_version and
    some columns from later ALTER TABLE patches still missing."""
    old = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    Base.metadata.create_all(bind=old)
    with old.begin() as connection:
        connection.exec_driver_sql("DROP INDEX ix_wbs_nodes_phase")
        for table, column in (("users", "is_active"), ("projects", "lock_reason"), ("wbs_nodes", "phase")):
            connection.exec_driver_sql(f"ALTER TABLE {table} DROP COLUMN {column}")
        connection.exec_driver_sql(
            "INSERT INTO users (username, password_hash, role) VALUES ('old.user', 'x', 'bu_head')"
        )
        # The old patches added these two lock-critical columns as nullable.
        for column, legacy_definition in (
            ("timesheets_soft_locked", "INTEGER DEFAULT 0"),
            ("governance_threshold_pct", "FLOAT DEFAULT 80"),
        ):
            connection.exec_driver_sql(f"ALTER TABLE projects DROP COLUMN {column}")
            connection.exec_driver_sql(f"ALTER TABLE projects ADD COLUMN {column} {legacy_definition}")
        connection.exec_driver_sql(
            "INSERT INTO projects (project_name, project_code, client_organization, project_lead, "
            "contract_value, contract_currency, governance_threshold_pct) "
            "VALUES ('Old', 'OLD-1', 'Client', 'Lead', 0, 'USD', NULL)"
        )
    return old


def test_pre_alembic_database_is_adopted_with_its_data(pre_alembic):
    migrate(pre_alembic)

    assert _revision(pre_alembic) == HEAD
    assert not [d for d in _differences(pre_alembic) if isinstance(d, tuple) and d[0] in ("add_table", "add_column")]
    assert "ix_wbs_nodes_phase" in {index["name"] for index in inspect(pre_alembic).get_indexes("wbs_nodes")}
    with pre_alembic.connect() as connection:
        assert connection.execute(text("SELECT username, is_active FROM users")).one() == ("old.user", 1)
        # A NULL threshold would silently mean "no threshold": filled with the model default, now NOT NULL.
        row = connection.execute(text("SELECT governance_threshold_pct, timesheets_soft_locked FROM projects")).one()
        assert row == (80.0, 0)
    nullability = [
        op
        for d in _differences(pre_alembic)
        for op in (d if isinstance(d, list) else [d])
        if op[0] == "modify_nullable"
    ]
    assert nullability == []


def test_database_that_cannot_be_adopted_stops_startup(pre_alembic):
    # full_name was never added by the old patches, so it can't be repaired automatically.
    with pre_alembic.begin() as connection:
        connection.exec_driver_sql("ALTER TABLE users DROP COLUMN full_name")

    with pytest.raises(RuntimeError, match="can't be adopted automatically"):
        migrate(pre_alembic)

    assert "alembic_version" not in inspect(pre_alembic).get_table_names()  # not stamped
