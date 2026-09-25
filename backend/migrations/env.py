"""Alembic environment: migrates the app's database against the models' metadata."""

from alembic import context
from sqlalchemy import create_engine

import models  # noqa: F401  (registers every table on Base.metadata)
from app.core.config import get_settings
from app.core.database import Base


def _run(connection) -> None:
    # Batch mode lets SQLite alter columns (it rebuilds the table).
    context.configure(connection=connection, target_metadata=Base.metadata, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    context.configure(
        url=get_settings().database_url, target_metadata=Base.metadata, literal_binds=True, render_as_batch=True
    )
    with context.begin_transaction():
        context.run_migrations()
elif (connection := context.config.attributes.get("connection")) is not None:
    _run(connection)  # called from app.core.migrations.migrate with the app's connection
else:
    with create_engine(get_settings().database_url).begin() as connection:  # alembic CLI
        _run(connection)
