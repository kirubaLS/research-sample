"""Engine and session wiring. Sync SQLAlchemy 2.0 style."""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings

_settings = get_settings()

if _settings.database_url.startswith("sqlite"):
    _kwargs: dict = {"connect_args": {"check_same_thread": False}}
else:
    # Managed Postgres sits behind a proxy that drops idle connections; recycle under it
    # and pre-ping so a reaped connection never surfaces as a 500. pre_ping also absorbs
    # the wake-up on a serverless database that has auto-suspended.
    _connect_args: dict = {}
    if _settings.uses_connection_pooler:
        # PgBouncer in transaction-pooling mode cannot carry server-side prepared
        # statements across transactions; psycopg would raise "prepared statement
        # already exists" under load. Disabling the cache is the supported fix.
        _connect_args["prepare_threshold"] = None
    _kwargs = {
        "pool_size": _settings.db_pool_size,
        "max_overflow": _settings.db_max_overflow,
        "pool_recycle": _settings.db_pool_recycle_seconds,
        "pool_pre_ping": True,
        "connect_args": _connect_args,
    }

engine = create_engine(_settings.database_url, future=True, **_kwargs)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


def get_session() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db() -> None:
    """Create tables directly.

    Development and tests only. Production applies Alembic migrations in the pre-deploy
    step so schema changes are reviewable and reversible.
    """
    from app.models import Base  # noqa: PLC0415

    Base.metadata.create_all(engine)
