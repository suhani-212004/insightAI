"""Statistical outlier detection on numeric columns.

Two methods, combined:
* z-score:  |x - mean| / std > 3     (good for roughly normal data)
* IQR:      x < Q1 - 3*IQR or x > Q3 + 3*IQR   (robust for skewed data)

A value is flagged if either method fires. We keep the strongest few per column.
"""
import numpy as np
import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import engine
from app.models import Anomaly, Dataset
from app.services.tenancy import safe_ident, schema_for

Z_THRESHOLD = 3.0
IQR_K = 3.0
MAX_PER_COLUMN = 10
MIN_ROWS = 8


def detect(df: pd.DataFrame) -> list[dict]:
    found: list[dict] = []
    if len(df) < MIN_ROWS:
        return found
    for col in df.select_dtypes(include=[np.number]).columns:
        s = pd.to_numeric(df[col], errors="coerce").dropna()
        if len(s) < MIN_ROWS or s.nunique() < 3:
            continue
        hits: dict[int, dict] = {}

        std = s.std(ddof=0)
        if std > 0:
            z = (s - s.mean()).abs() / std
            for idx, score in z[z > Z_THRESHOLD].items():
                hits[idx] = {"column": col, "row_index": int(idx), "value": float(s[idx]),
                             "score": round(float(score), 2), "method": "zscore"}

        q1, q3 = s.quantile(0.25), s.quantile(0.75)
        iqr = q3 - q1
        if iqr > 0:
            lo, hi = q1 - IQR_K * iqr, q3 + IQR_K * iqr
            for idx, v in s[(s < lo) | (s > hi)].items():
                if idx not in hits:
                    dist = (lo - v) if v < lo else (v - hi)
                    hits[idx] = {"column": col, "row_index": int(idx), "value": float(v),
                                 "score": round(float(dist / iqr), 2), "method": "iqr"}

        found.extend(sorted(hits.values(), key=lambda h: -h["score"])[:MAX_PER_COLUMN])
    return found


def scan_dataset(db: Session, dataset: Dataset, max_rows: int = 200_000) -> list[Anomaly]:
    schema = schema_for(dataset.org_id)
    with engine.connect() as conn:
        df = pd.read_sql(
            text(f'SELECT * FROM "{schema}"."{safe_ident(dataset.table_name)}" LIMIT :n'), conn, params={"n": max_rows}
        )
    db.query(Anomaly).filter_by(dataset_id=dataset.id).delete()
    rows = [Anomaly(org_id=dataset.org_id, dataset_id=dataset.id, **h) for h in detect(df)]
    db.add_all(rows)
    db.commit()
    return rows
