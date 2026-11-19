"""Turns CSV files / JSON records into real tables inside the org's schema.

All three sources (CSV upload, API polling, webhook) end up in `ingest_frame`,
so there is one code path to test.
"""
import io
import re
from typing import Any

import pandas as pd
from sqlalchemy import Numeric, text
from sqlalchemy.orm import Session

from app.core.database import engine
from app.models import Dataset
from app.services.tenancy import ensure_org_schema, grant_select, safe_ident, schema_for

RESERVED = {"select", "from", "where", "group", "order", "table", "user", "limit", "offset", "index"}


def slugify(name: str, fallback: str = "col") -> str:
    s = re.sub(r"[^a-z0-9]+", "_", str(name).strip().lower()).strip("_")
    if not s:
        s = fallback
    if s[0].isdigit():
        s = f"_{s}"
    if s in RESERVED:
        s = f"{s}_"
    return s[:60]


def _dedupe(names: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    out = []
    for n in names:
        if n in seen:
            seen[n] += 1
            out.append(f"{n}_{seen[n]}"[:63])
        else:
            seen[n] = 0
            out.append(n)
    return out


def clean_frame(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = _dedupe([slugify(c, f"col_{i}") for i, c in enumerate(df.columns)])
    df = df.dropna(how="all")
    for col in df.columns:
        if df[col].dtype == object:
            # Try numbers first ("1,200" -> 1200), then dates.
            stripped = df[col].astype(str).str.replace(",", "", regex=False).str.strip()
            as_num = pd.to_numeric(stripped, errors="coerce")
            non_null = df[col].notna().sum()
            if non_null and as_num.notna().sum() >= 0.95 * non_null:
                df[col] = as_num
                continue
            if any(k in col for k in ("date", "time", "day", "month", "created", "_at")):
                as_dt = pd.to_datetime(df[col], errors="coerce", format="mixed")
                if non_null and as_dt.notna().sum() >= 0.9 * non_null:
                    df[col] = as_dt
    return df


def pg_type(dtype) -> str:
    if pd.api.types.is_bool_dtype(dtype):
        return "boolean"
    if pd.api.types.is_integer_dtype(dtype):
        return "integer"
    if pd.api.types.is_float_dtype(dtype):
        return "numeric"
    if pd.api.types.is_datetime64_any_dtype(dtype):
        return "timestamp"
    return "text"


def describe_columns(df: pd.DataFrame) -> list[dict[str, str]]:
    return [{"name": c, "type": pg_type(df[c].dtype)} for c in df.columns]


def read_csv_bytes(data: bytes) -> pd.DataFrame:
    try:
        return pd.read_csv(io.BytesIO(data))
    except UnicodeDecodeError:
        return pd.read_csv(io.BytesIO(data), encoding="latin-1")


def records_from_json(payload: Any, json_path: str | None = None) -> list[dict]:
    node = payload
    for part in (json_path or "").split("."):
        if part:
            node = node[part]
    if isinstance(node, dict):
        node = [node]
    if not isinstance(node, list):
        raise ValueError("JSON payload must be an object or a list of objects")
    return node


def unique_table_name(db: Session, org_id: int, name: str) -> str:
    base = slugify(name, "dataset")[:50]
    candidate, i = base, 1
    while db.query(Dataset).filter_by(org_id=org_id, table_name=candidate).first():
        i += 1
        candidate = f"{base}_{i}"
    return safe_ident(candidate)


def ingest_frame(
    db: Session,
    org_id: int,
    df: pd.DataFrame,
    *,
    dataset: Dataset | None = None,
    name: str | None = None,
    source_type: str = "csv",
    mode: str = "replace",  # replace | append
) -> Dataset:
    if df.empty or len(df.columns) == 0:
        raise ValueError("No rows found")
    df = clean_frame(df)
    schema = ensure_org_schema(org_id)

    if dataset is None:
        dataset = Dataset(
            org_id=org_id,
            name=name or "dataset",
            table_name=unique_table_name(db, org_id, name or "dataset"),
            source_type=source_type,
        )
        db.add(dataset)
        db.flush()

    table = safe_ident(dataset.table_name)
    if mode == "append" and dataset.columns:
        # Keep the existing column set; new unknown columns are dropped.
        known = [c["name"] for c in dataset.columns]
        df = df.reindex(columns=known)

    column_info = describe_columns(df)
    # Store decimals as NUMERIC (not double precision) so SQL like round(x, 2) works.
    dtypes = {c: Numeric() for c in df.columns if pd.api.types.is_float_dtype(df[c].dtype)}
    # NaN -> NULL (Postgres NUMERIC would otherwise store 'NaN' and poison sums).
    for c in dtypes:
        df[c] = df[c].astype(object).where(df[c].notna(), None)
    df.to_sql(table, engine, schema=schema, if_exists=mode, index=False, chunksize=5000, method="multi",
              dtype=dtypes or None)
    grant_select(org_id, table)

    with engine.connect() as conn:
        count = conn.execute(text(f'SELECT count(*) FROM "{schema}"."{table}"')).scalar_one()
    if not dataset.columns or mode == "replace":
        dataset.columns = column_info
    dataset.row_count = int(count)
    db.commit()
    db.refresh(dataset)
    return dataset


def drop_dataset_table(dataset: Dataset) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(f'DROP TABLE IF EXISTS "{schema_for(dataset.org_id)}"."{safe_ident(dataset.table_name)}"')
        )


def preview(dataset: Dataset, limit: int = 50) -> dict:
    schema = schema_for(dataset.org_id)
    with engine.connect() as conn:
        res = conn.execute(text(f'SELECT * FROM "{schema}"."{safe_ident(dataset.table_name)}" LIMIT :n'), {"n": limit})
        cols = list(res.keys())
        rows = [dict(r._mapping) for r in res]
    return {"columns": cols, "rows": rows}
