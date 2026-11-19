"""Per-organisation Postgres schemas.

Each org gets schema `org_<id>`. The read-only role (used to run AI SQL) gets
USAGE on the schema and SELECT on its tables, and nothing else.
"""
import re

from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.core.config import settings
from app.core.database import engine as default_engine

_IDENT = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")


def safe_ident(name: str) -> str:
    """Validate an identifier we generated ourselves before quoting it into SQL."""
    if not _IDENT.match(name):
        raise ValueError(f"Unsafe identifier: {name!r}")
    return name


def schema_for(org_id: int) -> str:
    return safe_ident(f"org_{int(org_id)}")


def _readonly_role_exists(conn) -> bool:
    return bool(
        conn.execute(text("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": settings.READONLY_DB_ROLE}).scalar()
    )


def ensure_org_schema(org_id: int, engine: Engine = default_engine) -> str:
    schema = schema_for(org_id)
    with engine.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))
        if _readonly_role_exists(conn):
            role = safe_ident(settings.READONLY_DB_ROLE)
            conn.execute(text(f'GRANT USAGE ON SCHEMA "{schema}" TO "{role}"'))
            conn.execute(text(f'ALTER DEFAULT PRIVILEGES IN SCHEMA "{schema}" GRANT SELECT ON TABLES TO "{role}"'))
    return schema


def grant_select(org_id: int, table: str, engine: Engine = default_engine) -> None:
    schema = schema_for(org_id)
    with engine.begin() as conn:
        if _readonly_role_exists(conn):
            role = safe_ident(settings.READONLY_DB_ROLE)
            conn.execute(text(f'GRANT SELECT ON "{schema}"."{safe_ident(table)}" TO "{role}"'))


def drop_org_schema(org_id: int, engine: Engine = default_engine) -> None:
    with engine.begin() as conn:
        conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema_for(org_id)}" CASCADE'))
