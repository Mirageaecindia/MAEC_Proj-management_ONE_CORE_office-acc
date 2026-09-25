"""Additive schema upgrades for existing databases.

`Base.metadata.create_all()` creates missing tables but never adds columns to
existing ones, so new nullable columns on app-owned features are added here
(idempotent). To be replaced by Alembic migrations (roadmap).
"""

from sqlalchemy import inspect
from sqlalchemy.engine import Engine

# table -> {column: SQL type}
_ADDED_COLUMNS = {
    "projects": {
        "lock_reason": "VARCHAR(20)",
        "governance_alert_level": "VARCHAR(20)",
    },
}


def upgrade_schema(engine: Engine) -> None:
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    with engine.begin() as connection:
        for table, columns in _ADDED_COLUMNS.items():
            if table not in existing_tables:
                continue
            present = {column["name"] for column in inspector.get_columns(table)}
            for name, sql_type in columns.items():
                if name not in present:
                    connection.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {name} {sql_type}")
