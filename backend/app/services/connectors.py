"""API polling + webhook ingestion."""
import ipaddress
import socket
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import httpx
import pandas as pd
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Connector, Dataset
from app.services import events
from app.services.ingestion import ingest_frame, records_from_json

MAX_RESPONSE_BYTES = 10 * 1024 * 1024


class BlockedURL(ValueError):
    pass


def _is_internal(ip: str) -> bool:
    addr = ipaddress.ip_address(ip)
    return addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved or addr.is_multicast


def check_public_url(url: str, resolve: bool = True) -> None:
    """Stop connectors from being pointed at our own network (SSRF).

    Without this an admin could poll http://localhost:8000, http://db:5432 or the
    cloud metadata endpoint (169.254.169.254) and read the response back as a dataset.
    """
    if settings.ENV in ("dev", "test") and settings.ALLOW_PRIVATE_CONNECTOR_URLS:
        return
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise BlockedURL("A valid http(s) URL is required")
    host = parsed.hostname
    if host == "localhost" or host.endswith((".local", ".internal")):
        raise BlockedURL("Internal addresses are not allowed")
    try:
        ipaddress.ip_address(host)
        is_ip_literal = True
    except ValueError:
        is_ip_literal = False
    if is_ip_literal:
        if _is_internal(host):
            raise BlockedURL("Internal addresses are not allowed")
        return
    if not resolve:
        return
    try:
        infos = socket.getaddrinfo(host, parsed.port or 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror as e:
        raise BlockedURL(f"Could not resolve {host}") from e
    if any(_is_internal(info[4][0]) for info in infos):
        raise BlockedURL("Internal addresses are not allowed")


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
    # No redirects: a public URL could otherwise 302 us to an internal one.
    client = client or httpx.Client(timeout=20, follow_redirects=False)
    try:
        if owns_client:  # tests inject a mock transport and skip DNS
            check_public_url(url)
        resp = client.get(url, headers=connector.config.get("headers") or {})
        resp.raise_for_status()
        if len(resp.content) > MAX_RESPONSE_BYTES:
            raise ValueError("API response is larger than 10 MB")
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
        # A failed insert leaves the transaction aborted; without this rollback the
        # status update below fails too, and so does every later connector in the batch.
        db.rollback()
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
