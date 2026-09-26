"""Alembic migrations (TODO E4).

The test database itself is built by `migrate` when `main` is imported, so the
whole suite runs on a migrated schema.
"""

import pytest
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect

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


def test_database_created_before_alembic_is_refused(tmp_path):
    old = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with old.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE users (id INTEGER PRIMARY KEY, username VARCHAR(100))")

    with pytest.raises(RuntimeError, match="created before schema migrations"):
        migrate(old)

    assert "alembic_version" not in inspect(old).get_table_names()  # untouched
