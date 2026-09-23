"""Compatibility shim: the database layer now lives in `app.core.database`.

Kept so existing imports (`from database import Base, get_db`) in main.py,
models.py and scripts keep working. New code should import from app.core.
"""

from app.core.database import IS_SQLITE, SQLALCHEMY_DATABASE_URL, Base, SessionLocal, engine, get_db

__all__ = ["IS_SQLITE", "SQLALCHEMY_DATABASE_URL", "Base", "SessionLocal", "engine", "get_db"]
