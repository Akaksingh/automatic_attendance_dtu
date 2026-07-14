"""SQLAlchemy engine, session, and schema bootstrap."""
from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency: one DB session per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Bring the schema up to date. Idempotent.

    Postgres uses Alembic migrations (with automatic adoption of pre-Alembic
    databases); SQLite (tests) falls back to create_all since the migrations
    use Postgres-only features (pgvector, native enums).
    """
    # Import models so they're registered on Base.metadata.
    from . import models  # noqa: F401

    if engine.dialect.name == "postgresql":
        with engine.begin() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        from .migrations import run_migrations

        run_migrations()
    else:
        Base.metadata.create_all(bind=engine)
