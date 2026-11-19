"""API polling + webhook ingestion."""
from datetime import datetime, timedelta, timezone

import httpx
import pandas as pd
from sqlalchemy.orm import Session

from app.models import Connector, Dataset
from app.services import events
from app.services.ingestion import ingest_frame, records_from_json


def ingest_records(db: Session, connector: Connector, records: list[dict]) -> Dataset:
    dataset = db.get(Dataset, connector.dataset_id)
    if not records:
        return dataset
    df = pd.json_normalize(records)
    mode = "append" if dataset.columns else "replace"
    dataset = ingest_frame(db, connector.org_id, df, dataset=dataset, mode=mode, source_type=connector.type)
    events.publish(connector.org_id, "dataset.updated", dataset_id=dataset.id, rows=dataset.row_count,
                   added=len(records), source=connector.type)
    return dataset


def poll_connector(db: Session, connector: Connector, client: httpx.Client | None = None) -> int:
    url = connector.config.get("url")
    if not url:
        raise ValueError("Connector has no URL")
    owns_client = client is None
    client = client or httpx.Client(timeout=20, follow_redirects=True)
    try:
        resp = client.get(url, headers=connector.config.get("headers") or {})
        resp.raise_for_status()
        records = records_from_json(resp.json(), connector.config.get("json_path"))
        # Polling replaces the table with the latest snapshot of the API.
        dataset = db.get(Dataset, connector.dataset_id)
        if records:
            ingest_frame(db, connector.org_id, pd.json_normalize(records), dataset=dataset, mode="replace",
                         source_type="api_poll")
            events.publish(connector.org_id, "dataset.updated", dataset_id=dataset.id,
                           rows=dataset.row_count, source="api_poll")
        connector.last_status = f"ok: {len(records)} rows"
        return len(records)
    except Exception as e:
        connector.last_status = f"error: {str(e)[:200]}"
        raise
    finally:
        connector.last_run_at = datetime.now(timezone.utc)
        db.commit()
        if owns_client:
            client.close()


def due_connectors(db: Session) -> list[Connector]:
    now = datetime.now(timezone.utc)
    due = []
    for c in db.query(Connector).filter_by(type="api_poll", enabled=True).all():
        interval = timedelta(minutes=int(c.config.get("interval_minutes", 60)))
        if c.last_run_at is None or c.last_run_at + interval <= now:
            due.append(c)
    return due
