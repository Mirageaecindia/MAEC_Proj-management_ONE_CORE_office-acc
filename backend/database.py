"""
Database configuration.

Uses SQLite for local development (zero setup). To point this at Postgres
for production, just change SQLALCHEMY_DATABASE_URL, e.g.:
    postgresql://user:password@localhost:5432/promanage
Everything else (models, session handling) stays the same because
SQLAlchemy abstracts the driver.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

SQLALCHEMY_DATABASE_URL = "sqlite:///./promanage.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    # only needed for SQLite: allows the connection to be used across threads
    connect_args={"check_same_thread": False},
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """FastAPI dependency that yields a DB session and always closes it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
