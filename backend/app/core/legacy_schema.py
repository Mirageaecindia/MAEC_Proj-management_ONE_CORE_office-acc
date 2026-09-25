"""Brings a database created before Alembic up to the baseline schema.

Used once per database by `app.core.migrations.migrate`: the old startup code
patched schemas with ad-hoc ALTER TABLEs, so databases on different machines
may be at different points. This replays those patches (all idempotent), after
which the schema is compared with the models and stamped at the baseline.

Delete this module once every database has been adopted (docs/TODO.md E4).
New schema changes never go here: they are Alembic revisions in `migrations/`.
"""

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from app.core.database import Base

# Columns added over time by the old startup code: table -> {column: SQL definition}.
_LEGACY_COLUMNS = {
    "wbs_nodes": {
        "start_date": "DATE",
        "end_date": "DATE",
        "phase": "VARCHAR(50)",
        "assigned_lead_user_id": "INTEGER",
        "description": "TEXT",
        "severity": "VARCHAR(20)",
        "actual_start_datetime": "DATETIME",
        "actual_end_datetime": "DATETIME",
    },
    "projects": {
        "contract_value": "FLOAT DEFAULT 0",
        "contract_currency": "VARCHAR(10) DEFAULT 'USD'",
        "governance_threshold_pct": "FLOAT DEFAULT 80",
        "timesheets_soft_locked": "INTEGER DEFAULT 0",
        "extension_status": "VARCHAR(20)",
        "extension_approved_hours": "FLOAT",
        "project_lead_electrical": "VARCHAR(150)",
        "project_lead_mechanical": "VARCHAR(150)",
        "project_lead_bim": "VARCHAR(150)",
        "sharepoint_disciplines": "TEXT",
        "target_effort_hours": "FLOAT",
        "sharepoint_site_url": "VARCHAR(500)",
        "project_lead_electrical_user_id": "INTEGER",
        "project_lead_mechanical_user_id": "INTEGER",
        "project_lead_bim_user_id": "INTEGER",
        "lock_reason": "VARCHAR(20)",
        "governance_alert_level": "VARCHAR(20)",
    },
    "governance_actions": {
        "extension_request_id": "INTEGER",
        "requested_hours": "FLOAT",
    },
    "resource_bookings": {
        "start_date": "DATE",
        "end_date": "DATE",
        "approval_status": "VARCHAR(20) DEFAULT 'draft'",
        "submitted_at": "DATETIME",
        "approved_at": "DATETIME",
    },
    "users": {
        "discipline": "VARCHAR(100)",
        "is_active": "BOOLEAN NOT NULL DEFAULT TRUE",
    },
}

# Added as nullable by the old patches but NOT NULL in the models / baseline:
# table -> {column: model default used to fill existing NULLs}.
_NOT_NULL_COLUMNS = {
    "projects": {
        "contract_value": 0,
        "contract_currency": "USD",
        "governance_threshold_pct": 80,
        "timesheets_soft_locked": 0,
    },
    "resource_bookings": {"approval_status": "draft"},
}

_WBS_INDEXES = ("project_id", "parent_id", "wbs_code", "assigned_engineer_id")


def converge_legacy_schema(engine: Engine) -> None:
    import models  # noqa: F401  (registers every table on Base.metadata)

    Base.metadata.create_all(bind=engine)  # tables that didn't exist yet
    _add_missing_columns(engine)
    _make_wbs_code_and_hours_nullable(engine)
    _enforce_not_null(engine)
    for table in Base.metadata.sorted_tables:  # indexes the old patches never created
        for index in table.indexes:
            index.create(engine, checkfirst=True)
    with engine.begin() as connection:
        # Data fixes the old startup code applied.
        connection.exec_driver_sql("UPDATE wbs_nodes SET phase = 'Space Planning' WHERE phase IS NULL")
        connection.exec_driver_sql(
            "UPDATE wbs_nodes SET deliverable_status = 'Submitted for Approval' "
            "WHERE deliverable_status = 'Submitted for Review'"
        )


def _add_missing_columns(engine: Engine) -> None:
    inspector = inspect(engine)
    with engine.begin() as connection:
        for table, columns in _LEGACY_COLUMNS.items():
            present = {column["name"] for column in inspector.get_columns(table)}
            for name, definition in columns.items():
                if name not in present:
                    connection.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")


def _enforce_not_null(engine: Engine) -> None:
    """Fill NULLs with the model default, then make the column NOT NULL, so the
    lock logic never reads a NULL as "not locked" or "no threshold"."""
    inspector = inspect(engine)
    with engine.begin() as connection:
        operations = Operations(MigrationContext.configure(connection))
        for table, defaults in _NOT_NULL_COLUMNS.items():
            columns = {column["name"]: column for column in inspector.get_columns(table)}
            loose = [name for name in defaults if columns[name]["nullable"]]
            if not loose:
                continue
            for name in loose:
                connection.execute(
                    text(f"UPDATE {table} SET {name} = :value WHERE {name} IS NULL"), {"value": defaults[name]}
                )
            with operations.batch_alter_table(table) as batch:  # SQLite: rebuilds the table, keeps its indexes
                for name in loose:
                    batch.alter_column(name, existing_type=columns[name]["type"], nullable=False)


def _make_wbs_code_and_hours_nullable(engine: Engine) -> None:
    """Very old databases have NOT NULL wbs_code/estimated_hours. SQLite can't
    change nullability in place, so the table is rebuilt once."""
    columns = {column["name"]: column["nullable"] for column in inspect(engine).get_columns("wbs_nodes")}
    if columns.get("wbs_code") is not False and columns.get("estimated_hours") is not False:
        return
    with engine.begin() as connection:
        rows = connection.exec_driver_sql("PRAGMA table_info(wbs_nodes)").fetchall()
        definitions = []
        for _cid, name, sql_type, not_null, default, primary_key in rows:
            parts = [f'"{name}" {sql_type}']
            if not_null and name not in ("wbs_code", "estimated_hours"):
                parts.append("NOT NULL")
            if default is not None:
                parts.append(f"DEFAULT {default}")
            if primary_key:
                parts.append("PRIMARY KEY")
            definitions.append(" ".join(parts))
        names = ", ".join(f'"{row[1]}"' for row in rows)
        connection.exec_driver_sql(f"CREATE TABLE wbs_nodes_new ({', '.join(definitions)})")
        connection.exec_driver_sql(f"INSERT INTO wbs_nodes_new ({names}) SELECT {names} FROM wbs_nodes")
        connection.exec_driver_sql("DROP TABLE wbs_nodes")
        connection.exec_driver_sql("ALTER TABLE wbs_nodes_new RENAME TO wbs_nodes")
        for column in _WBS_INDEXES:
            connection.exec_driver_sql(f"CREATE INDEX ix_wbs_nodes_{column} ON wbs_nodes ({column})")
