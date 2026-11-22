import secrets

from fastapi import APIRouter, Body, Depends, Header, HTTPException, status
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.api.deps import TenantContext, get_owned, require_role
from app.core.config import settings
from app.core.database import get_db
from app.models import Connector, Dataset, Organization
from app.schemas import ConnectorIn, ConnectorOut
from app.services.connectors import BlockedURL, check_public_url, ingest_records, poll_connector
from app.services.ingestion import records_from_json, unique_table_name
from app.services.plans import check_limit, require_feature

router = APIRouter(tags=["connectors"])


def _out(c: Connector) -> dict:
    data = ConnectorOut.model_validate(c).model_dump()
    if c.type == "webhook":
        data["webhook_url"] = f"/api/v1/ingest/webhook/{c.id}/{c.secret}"
    return data


@router.get("/connectors", response_model=list[ConnectorOut])
def list_connectors(ctx: TenantContext = Depends(require_role("admin")), db: Session = Depends(get_db)):
    return [_out(c) for c in db.query(Connector).filter_by(org_id=ctx.org.id).order_by(Connector.id).all()]


@router.post("/connectors", response_model=ConnectorOut, status_code=201)
def create_connector(body: ConnectorIn, ctx: TenantContext = Depends(require_role("admin")),
                     db: Session = Depends(get_db)):
    require_feature(ctx.org, "api_connectors" if body.type == "api_poll" else "webhooks")
    check_limit(db, ctx.org, "datasets")
    if body.type == "api_poll":
        if not (body.url or "").startswith(("http://", "https://")):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "A valid http(s) URL is required for API polling")
        try:
            # Cheap check now (no DNS); the full resolve-and-check happens on every poll.
            check_public_url(body.url, resolve=False)
        except BlockedURL as e:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))

    dataset = Dataset(org_id=ctx.org.id, name=body.dataset_name, source_type=body.type,
                      table_name=unique_table_name(db, ctx.org.id, body.dataset_name), columns=[])
    db.add(dataset)
    db.flush()
    config = {"url": body.url, "interval_minutes": body.interval_minutes, "json_path": body.json_path} \
        if body.type == "api_poll" else {}
    c = Connector(org_id=ctx.org.id, dataset_id=dataset.id, type=body.type, config=config,
                  secret=secrets.token_urlsafe(24))
    db.add(c)
    db.commit()
    return _out(c)


@router.post("/connectors/{connector_id}/run", response_model=ConnectorOut)
def run_connector(connector_id: int, ctx: TenantContext = Depends(require_role("admin")),
                  db: Session = Depends(get_db)):
    c = get_owned(db, Connector, connector_id, ctx.org.id, "API connector")
    if c.type != "api_poll":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "API connector not found")
    try:
        poll_connector(db, c)
    except Exception:
        pass  # status is recorded on the connector
    db.refresh(c)
    return _out(c)


@router.delete("/connectors/{connector_id}", status_code=204)
def delete_connector(connector_id: int, ctx: TenantContext = Depends(require_role("admin")),
                     db: Session = Depends(get_db)):
    db.delete(get_owned(db, Connector, connector_id, ctx.org.id))
    db.commit()


@router.post("/ingest/webhook/{connector_id}/{secret}", status_code=202)
def webhook_receiver(connector_id: int, secret: str, payload=Body(...), db: Session = Depends(get_db),
                     content_length: int | None = Header(default=None)):
    """Public endpoint. External systems POST JSON rows here; the secret in the URL authenticates them."""
    if content_length and content_length > settings.MAX_WEBHOOK_KB * 1024:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, f"Max payload is {settings.MAX_WEBHOOK_KB} KB")
    c = db.get(Connector, connector_id)
    if not c or c.type != "webhook" or not c.enabled or not secrets.compare_digest(c.secret, secret):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    org = db.get(Organization, c.org_id)
    require_feature(org, "webhooks")  # stops working if the org downgrades
    try:
        records = records_from_json(payload, c.config.get("json_path"))
    except (KeyError, ValueError, TypeError) as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Bad payload: {e}")
    try:
        dataset = ingest_records(db, c, records)
    except (DBAPIError, ValueError) as e:
        # Usually a type clash, e.g. "abc" sent for a column that was numeric in the first batch.
        db.rollback()
        detail = str(getattr(e, "orig", e)).split("\n")[0]
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Rows don't match the dataset: {detail}")
    return {"accepted": len(records), "row_count": dataset.row_count}
