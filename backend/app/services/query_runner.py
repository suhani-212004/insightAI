"""Runs validated SQL for one tenant, safely."""
import datetime as dt
import decimal
import math

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import readonly_engine
from app.models import Dataset
from app.services.sql_guard import validate_sql
from app.services.tenancy import schema_for


def tenant_tables(db: Session, org_id: int) -> set[str]:
    return {d.table_name for d in db.query(Dataset).filter_by(org_id=org_id).all()}


def _jsonable(v):
    if isinstance(v, decimal.Decimal):
        f = float(v)
        return int(f) if f.is_integer() else f
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return None
    if isinstance(v, (dt.datetime, dt.date)):
        return v.isoformat()
    if isinstance(v, dt.timedelta):
        return v.total_seconds()
    return v


def run_tenant_query(db: Session, org_id: int, sql: str, limit: int | None = None) -> dict:
    limit = limit or settings.QUERY_ROW_LIMIT
    schema = schema_for(org_id)
    safe_sql = validate_sql(sql, tenant_tables(db, org_id), schema)
    wrapped = f"SELECT * FROM ({safe_sql}) AS _q LIMIT {int(limit) + 1}"

    with readonly_engine.connect() as conn:
        with conn.begin():
            conn.execute(text("SET TRANSACTION READ ONLY"))
            conn.execute(text(f'SET LOCAL search_path TO "{schema}"'))
            conn.execute(text(f"SET LOCAL statement_timeout = {int(settings.QUERY_TIMEOUT_MS)}"))
            # Escape ':' so SQLAlchemy doesn't treat '10:30' or '::date' as bind params.
            res = conn.execute(text(wrapped.replace(":", r"\:")))
            columns = list(res.keys())
            rows = [{k: _jsonable(v) for k, v in r._mapping.items()} for r in res]

    truncated = len(rows) > limit
    return {"columns": columns, "rows": rows[:limit], "truncated": truncated, "sql": safe_sql}
