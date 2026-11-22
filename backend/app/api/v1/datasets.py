from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from app.api.deps import Page, TenantContext, get_owned, pagination, require_role
from app.core.config import settings
from app.core.database import get_db, session_scope
from app.models import Anomaly, Dataset
from app.schemas import AnomalyOut, DatasetOut
from app.services import events
from app.services.anomaly import scan_dataset
from app.services.ingestion import drop_dataset_table, ingest_frame, preview, read_csv_bytes
from app.services.plans import check_limit, has_feature, require_feature

router = APIRouter(prefix="/datasets", tags=["datasets"])


def _get(db: Session, ctx: TenantContext, dataset_id: int) -> Dataset:
    return get_owned(db, Dataset, dataset_id, ctx.org.id)


def run_anomaly_scan(dataset_id: int) -> None:
    """Runs after the response is sent, with its own DB session."""
    with session_scope() as db:
        d = db.get(Dataset, dataset_id)
        if d:
            found = scan_dataset(db, d)
            events.publish(d.org_id, "anomalies.updated", dataset_id=d.id, count=len(found))


@router.get("", response_model=list[DatasetOut])
def list_datasets(ctx: TenantContext = Depends(require_role("viewer")), page: Page = Depends(pagination),
                  db: Session = Depends(get_db)):
    return page.apply(db.query(Dataset).filter_by(org_id=ctx.org.id).order_by(Dataset.id.desc())).all()


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
    # Stream the upload with a hard cap so a huge file can't exhaust memory
    # before the size limit is applied.
    cap = settings.MAX_UPLOAD_MB * 1024 * 1024
    buf = bytearray()
    while chunk := await file.read(1024 * 1024):
        buf += chunk
        if len(buf) > cap:
            raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, f"Max upload is {settings.MAX_UPLOAD_MB} MB")
    data = bytes(buf)

    events.publish(ctx.org.id, "ingest.started", filename=file.filename)

    def _ingest() -> Dataset:
        df = read_csv_bytes(data)
        return ingest_frame(db, ctx.org.id, df, name=name or file.filename.rsplit(".", 1)[0], source_type="csv")

    try:
        # pandas + bulk inserts are blocking; running them on the event loop would
        # freeze every other request (and all SSE streams) until the upload finishes.
        dataset = await run_in_threadpool(_ingest)
    except Exception as e:
        db.rollback()
        events.publish(ctx.org.id, "ingest.failed", filename=file.filename, error=str(e)[:200])
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Could not read CSV: {e}")

    events.publish(ctx.org.id, "ingest.completed", dataset_id=dataset.id, name=dataset.name, rows=dataset.row_count)
    if has_feature(ctx.org, "anomaly_detection"):
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
