"""Database engines and session helpers.

Two engines:
* `engine`          - the app role. Creates tenant schemas, writes data.
* `readonly_engine` - used only to run SQL that came from the LLM or from a widget.
                      In production point READONLY_DATABASE_URL at a role that has
                      SELECT-only grants (see docker/postgres/init.sql).

Pool sizes are configurable because the right numbers depend on how many API
processes and workers share one Postgres: processes x (pool + overflow) has to
stay below Postgres' max_connections.
"""
import logging
from collections.abc import Generator, Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings

log = logging.getLogger(__name__)


def _make_engine(url: str, pool_size: int):
    return create_engine(
        url,
        pool_pre_ping=True,
        pool_size=pool_size,
        max_overflow=settings.DB_MAX_OVERFLOW,
        pool_recycle=1800,  # drop connections before proxies / PgBouncer time them out
        future=True,
    )


engine = _make_engine(settings.DATABASE_URL, settings.DB_POOL_SIZE)
if settings.READONLY_DATABASE_URL:
    # Separate (smaller) pool: a burst of slow AI queries can't starve normal requests.
    readonly_engine = _make_engine(settings.READONLY_DATABASE_URL, settings.DB_READONLY_POOL_SIZE)
else:
    # Falling back means LLM SQL runs as the app role, which can read the users table.
    # sql_guard still blocks it, but the third safety layer is gone, so say so loudly.
    if settings.ENV == "prod":
        raise RuntimeError("READONLY_DATABASE_URL must be set in production")
    log.warning("READONLY_DATABASE_URL not set; AI/widget SQL will use the main DB role")
    readonly_engine = engine

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency: one session per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    """Session for code that runs outside a request (workers, background tasks, scripts).

    Commits if the block finishes, rolls back if it raises, and always returns the
    connection to the pool.
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
