"""Schema migrations (Alembic), applied at server start by `migrate`.

- New or already-migrated database: `alembic upgrade head`.
- Database created before Alembic (no `alembic_version` table): the old
  startup patches are replayed (app/core/legacy_schema.py), the result is
  compared with the models, and the database is stamped at the baseline.
  A missing table or column stops startup with a clear error instead of
  stamping a schema that doesn't match.
"""

import logging
from pathlib import Path

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import inspect
from sqlalchemy.engine import Connection, Engine

from app.core.database import Base
from app.core.legacy_schema import converge_legacy_schema

logger = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).resolve().parents[2]
BASELINE_REVISION = "0001"


def migrate(engine: Engine) -> None:
    """Bring the database schema up to the latest migration."""
    if _created_before_alembic(engine):
        converge_legacy_schema(engine)
        _require_matching_schema(engine)
        _run(engine, command.stamp, BASELINE_REVISION)
        logger.info("Pre-Alembic database adopted at revision %s.", BASELINE_REVISION)
    _run(engine, command.upgrade, "head")


def _created_before_alembic(engine: Engine) -> bool:
    tables = set(inspect(engine).get_table_names())
    return bool(tables) and "alembic_version" not in tables


def _require_matching_schema(engine: Engine) -> None:
    import models  # noqa: F401  (registers every table on Base.metadata)

    with engine.connect() as connection:
        differences = compare_metadata(MigrationContext.configure(connection), Base.metadata)
    missing = [d for d in differences if isinstance(d, tuple) and d[0] in ("add_table", "add_column")]
    if missing:
        raise RuntimeError(
            "This database can't be adopted automatically; the models need tables/columns it lacks: "
            f"{missing}. Back it up and fix the schema by hand (docs/TODO.md E4)."
        )
    for difference in differences:
        logger.warning("Pre-Alembic schema differs from the models (tolerated): %s", difference)


def _run(engine: Engine, alembic_command, revision: str) -> None:
    with engine.begin() as connection:
        alembic_command(_config(connection), revision)


def _config(connection: Connection) -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.attributes["connection"] = connection
    return config
