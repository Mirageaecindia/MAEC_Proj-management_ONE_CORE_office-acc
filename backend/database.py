"""
Database configuration.

The connection URL comes from the DATABASE_URL environment variable (or
backend/.env). When unset it defaults to `backend/promanage.db`, resolved
relative to this file rather than the working directory, so the app always
opens the same database no matter where uvicorn is launched from.

To point this at Postgres, set e.g.:
    DATABASE_URL=postgresql://user:password@localhost:5432/promanage
Everything else (models, session handling) stays the same because
SQLAlchemy abstracts the driver.
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker

BACKEND_DIR = Path(__file__).resolve().parent
load_dotenv(BACKEND_DIR / ".env")

DEFAULT_DATABASE_URL = f"sqlite:///{(BACKEND_DIR / 'promanage.db').as_posix()}"
SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL") or DEFAULT_DATABASE_URL
IS_SQLITE = SQLALCHEMY_DATABASE_URL.startswith("sqlite")

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    # only needed for SQLite: allows the connection to be used across threads
    connect_args={"check_same_thread": False} if IS_SQLITE else {},
)

if IS_SQLITE:

    @event.listens_for(engine, "connect")
    def _configure_sqlite(dbapi_connection, _connection_record):
        # WAL lets readers proceed while a write is in progress, which matters
        # because every page polls the API while users are saving changes.
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """FastAPI dependency that yields a DB session and always closes it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
