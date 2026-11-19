import secrets

from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import TenantContext, require_role
from app.core.database import get_db
from app.models import Connector, Dataset
from app.schemas import ConnectorIn, ConnectorOut
from app.services.connectors import ingest_records, poll_connector
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
    if body.type == "api_poll" and not (body.url or "").startswith(("http://", "https://")):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "A valid http(s) URL is required for API polling")

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
    c = db.query(Connector).filter_by(id=connector_id, org_id=ctx.org.id).first()
    if not c or c.type != "api_poll":
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
    c = db.query(Connector).filter_by(id=connector_id, org_id=ctx.org.id).first()
    if not c:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Connector not found")
    db.delete(c)
    db.commit()


@router.post("/ingest/webhook/{connector_id}/{secret}", status_code=202)
def webhook_receiver(connector_id: int, secret: str, payload=Body(...), db: Session = Depends(get_db)):
    """Public endpoint. External systems POST JSON rows here; the secret in the URL authenticates them."""
    c = db.get(Connector, connector_id)
    if not c or c.type != "webhook" or not c.enabled or not secrets.compare_digest(c.secret, secret):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    try:
        records = records_from_json(payload, c.config.get("json_path"))
    except (KeyError, ValueError, TypeError) as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Bad payload: {e}")
    dataset = ingest_records(db, c, records)
    return {"accepted": len(records), "row_count": dataset.row_count}
