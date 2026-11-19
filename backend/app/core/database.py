"""Database engines and session factory.

Two engines:
* `engine`          - the app role. Creates tenant schemas, writes data.
* `readonly_engine` - used only to run SQL that came from the LLM or from a widget.
                      In production point READONLY_DATABASE_URL at a role that has
                      SELECT-only grants (see docker/postgres/init.sql).
"""
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings

engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True, future=True)
readonly_engine = (
    create_engine(settings.READONLY_DATABASE_URL, pool_pre_ping=True, future=True)
    if settings.READONLY_DATABASE_URL
    else engine
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
