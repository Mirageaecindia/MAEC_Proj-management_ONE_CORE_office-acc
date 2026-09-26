"""Schema migrations (Alembic), applied at server start by `migrate`.

Every database is created and upgraded by the revisions in `migrations/`.
A database created before Alembic (tables but no `alembic_version`) is
refused: the one-off adoption of those development databases is done, and
there is no production data yet (docs/TODO.md E4).
"""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect
from sqlalchemy.engine import Connection, Engine

BACKEND_DIR = Path(__file__).resolve().parents[2]
PRE_ALEMBIC = (
    "This database was created before schema migrations and can't be upgraded. "
    "Back it up with backup_db.py, then start with a fresh database (delete the file or point DATABASE_URL elsewhere)."
)


def migrate(engine: Engine) -> None:
    """Bring the database schema up to the latest migration."""
    tables = set(inspect(engine).get_table_names())
    if tables and "alembic_version" not in tables:
        raise RuntimeError(PRE_ALEMBIC)
    with engine.begin() as connection:
        command.upgrade(_config(connection), "head")


def _config(connection: Connection) -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.attributes["connection"] = connection
    return config
