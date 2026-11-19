from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import TenantContext, require_role
from app.core.config import settings
from app.core.database import SessionLocal, get_db
from app.models import Anomaly, Dataset
from app.schemas import AnomalyOut, DatasetOut
from app.services import events
from app.services.anomaly import scan_dataset
from app.services.ingestion import drop_dataset_table, ingest_frame, preview, read_csv_bytes
from app.services.plans import PLANS, check_limit, require_feature

router = APIRouter(prefix="/datasets", tags=["datasets"])


def _get(db: Session, ctx: TenantContext, dataset_id: int) -> Dataset:
    d = db.query(Dataset).filter_by(id=dataset_id, org_id=ctx.org.id).first()
    if not d:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Dataset not found")
    return d


def run_anomaly_scan(dataset_id: int) -> None:
    """Runs after the response is sent, with its own DB session."""
    db = SessionLocal()
    try:
        d = db.get(Dataset, dataset_id)
        if d:
            found = scan_dataset(db, d)
            events.publish(d.org_id, "anomalies.updated", dataset_id=d.id, count=len(found))
    finally:
        db.close()


@router.get("", response_model=list[DatasetOut])
def list_datasets(ctx: TenantContext = Depends(require_role("viewer")), db: Session = Depends(get_db)):
    return db.query(Dataset).filter_by(org_id=ctx.org.id).order_by(Dataset.id.desc()).all()


@router.post("/upload", response_model=DatasetOut, status_code=201)
async def upload_csv(
    background: BackgroundTasks,
    file: UploadFile = File(...),
    name: str = Form(""),
    ctx: TenantContext = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    if not (file.filename or "").lower().endswith((".csv", ".txt")):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Please upload a .csv file")
    check_limit(db, ctx.org, "datasets")
    data = await file.read()
    if len(data) > settings.MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, f"Max upload is {settings.MAX_UPLOAD_MB} MB")

    events.publish(ctx.org.id, "ingest.started", filename=file.filename)
    try:
        df = read_csv_bytes(data)
        dataset = ingest_frame(db, ctx.org.id, df, name=name or file.filename.rsplit(".", 1)[0], source_type="csv")
    except Exception as e:
        db.rollback()
        events.publish(ctx.org.id, "ingest.failed", filename=file.filename, error=str(e)[:200])
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Could not read CSV: {e}")

    events.publish(ctx.org.id, "ingest.completed", dataset_id=dataset.id, name=dataset.name, rows=dataset.row_count)
    if "anomaly_detection" in PLANS[ctx.org.plan]["features"]:
        background.add_task(run_anomaly_scan, dataset.id)
    return dataset


@router.get("/{dataset_id}", response_model=DatasetOut)
def get_dataset(dataset_id: int, ctx: TenantContext = Depends(require_role("viewer")), db: Session = Depends(get_db)):
    return _get(db, ctx, dataset_id)


@router.get("/{dataset_id}/preview")
def dataset_preview(dataset_id: int, limit: int = 50, ctx: TenantContext = Depends(require_role("viewer")),
                    db: Session = Depends(get_db)):
    from app.services.query_runner import _jsonable

    p = preview(_get(db, ctx, dataset_id), min(max(limit, 1), 500))
    p["rows"] = [{k: _jsonable(v) for k, v in r.items()} for r in p["rows"]]
    return p


@router.delete("/{dataset_id}", status_code=204)
def delete_dataset(dataset_id: int, ctx: TenantContext = Depends(require_role("admin")), db: Session = Depends(get_db)):
    d = _get(db, ctx, dataset_id)
    drop_dataset_table(d)
    db.delete(d)
    db.commit()
    events.publish(ctx.org.id, "dataset.deleted", dataset_id=dataset_id)


@router.get("/{dataset_id}/anomalies", response_model=list[AnomalyOut])
def list_anomalies(dataset_id: int, ctx: TenantContext = Depends(require_role("viewer")),
                   db: Session = Depends(get_db)):
    _get(db, ctx, dataset_id)
    return db.query(Anomaly).filter_by(dataset_id=dataset_id).order_by(Anomaly.score.desc()).all()


@router.post("/{dataset_id}/anomalies/scan", response_model=list[AnomalyOut])
def scan_now(dataset_id: int, ctx: TenantContext = Depends(require_role("admin")), db: Session = Depends(get_db)):
    require_feature(ctx.org, "anomaly_detection")
    return scan_dataset(db, _get(db, ctx, dataset_id))
