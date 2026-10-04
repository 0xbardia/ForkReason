"""Database engine and session handling."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from .config import get_settings
from .models import Base

log = logging.getLogger(__name__)

_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def _engine_kwargs(url: str) -> dict:
    return {
        "pool_pre_ping": True,
        "pool_recycle": 1800,
        "future": True,
        # SQLite is supported only so unit tests can run without a server.
        "connect_args": {"timeout": 10} if url.startswith("sqlite") else {"connect_timeout": 10},
    }


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        settings = get_settings()
        kwargs = _engine_kwargs(settings.database_url)
        if settings.database_url.startswith("sqlite"):
            _engine = create_engine(settings.database_url, **kwargs)
        else:
            _engine = create_engine(
                settings.database_url,
                pool_size=5,
                max_overflow=10,
                **kwargs,
            )
        if settings.database_url.startswith("sqlite"):
            _enable_sqlite_pragmas(_engine)
    return _engine


def _enable_sqlite_pragmas(engine: Engine) -> None:
    """Test-only. Enables foreign keys and WAL so SQLite behaves sanely."""

    @event.listens_for(engine, "connect")
    def _set_pragmas(dbapi_connection, _record):  # pragma: no cover - test only
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def get_session_factory() -> sessionmaker[Session]:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(
            bind=get_engine(), autoflush=False, expire_on_commit=False, future=True
        )
    return _SessionLocal


@contextmanager
def session_scope() -> Iterator[Session]:
    """Transactional scope. Commits on success, rolls back on error."""
    factory = get_session_factory()
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_db() -> Iterator[Session]:
    """FastAPI dependency."""
    factory = get_session_factory()
    session = factory()
    try:
        yield session
    finally:
        session.close()


def create_all() -> None:
    """Create tables directly. Used by tests; production uses Alembic."""
    Base.metadata.create_all(bind=get_engine())


def drop_all() -> None:
    Base.metadata.drop_all(bind=get_engine())


def ping() -> bool:
    """Cheap liveness probe for the database."""
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as exc:  # noqa: BLE001 - health probe must not raise
        log.warning("database ping failed", extra={"error": str(exc)[:200]})
        return False


def reset_engine() -> None:
    """Drop cached engine/session. Used by tests that swap the database URL."""
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None