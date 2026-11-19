from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.api.deps import TenantContext, require_role
from app.core.database import get_db
from app.models import Dashboard, ReportSchedule, Widget
from app.schemas import (
    DashboardIn,
    DashboardOut,
    LayoutIn,
    QueryResult,
    ScheduleIn,
    ScheduleOut,
    WidgetIn,
    WidgetOut,
)
from app.services.plans import check_limit, require_feature
from app.services.query_runner import run_tenant_query
from app.services.sql_guard import UnsafeSQL

router = APIRouter(tags=["dashboards"])


def _dash(db: Session, ctx: TenantContext, dashboard_id: int) -> Dashboard:
    d = db.query(Dashboard).filter_by(id=dashboard_id, org_id=ctx.org.id).first()
    if not d:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Dashboard not found")
    return d


def _widget(db: Session, ctx: TenantContext, widget_id: int) -> Widget:
    w = (
        db.query(Widget).join(Dashboard)
        .filter(Widget.id == widget_id, Dashboard.org_id == ctx.org.id)
        .first()
    )
    if not w:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Widget not found")
    return w


def _run(db: Session, org_id: int, sql: str) -> dict:
    try:
        return run_tenant_query(db, org_id, sql)
    except UnsafeSQL as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    except DBAPIError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e.orig).split("\n")[0])


# ---------- ad-hoc query (widget editor "Run" button) ----------
@router.post("/query", response_model=QueryResult)
def run_query(body: dict, ctx: TenantContext = Depends(require_role("admin")), db: Session = Depends(get_db)):
    return _run(db, ctx.org.id, body.get("sql", ""))


# ---------- dashboards ----------
@router.get("/dashboards", response_model=list[DashboardOut])
def list_dashboards(ctx: TenantContext = Depends(require_role("viewer")), db: Session = Depends(get_db)):
    return db.query(Dashboard).filter_by(org_id=ctx.org.id).order_by(Dashboard.id).all()


@router.post("/dashboards", response_model=DashboardOut, status_code=201)
def create_dashboard(body: DashboardIn, ctx: TenantContext = Depends(require_role("admin")),
                     db: Session = Depends(get_db)):
    check_limit(db, ctx.org, "dashboards")
    d = Dashboard(org_id=ctx.org.id, name=body.name, layout=[])
    db.add(d)
    db.commit()
    db.refresh(d)
    return d


@router.get("/dashboards/{dashboard_id}", response_model=DashboardOut)
def get_dashboard(dashboard_id: int, ctx: TenantContext = Depends(require_role("viewer")),
                  db: Session = Depends(get_db)):
    return _dash(db, ctx, dashboard_id)


@router.patch("/dashboards/{dashboard_id}", response_model=DashboardOut)
def rename_dashboard(dashboard_id: int, body: DashboardIn, ctx: TenantContext = Depends(require_role("admin")),
                     db: Session = Depends(get_db)):
    d = _dash(db, ctx, dashboard_id)
    d.name = body.name
    db.commit()
    return d


@router.put("/dashboards/{dashboard_id}/layout", response_model=DashboardOut)
def save_layout(dashboard_id: int, body: LayoutIn, ctx: TenantContext = Depends(require_role("admin")),
                db: Session = Depends(get_db)):
    d = _dash(db, ctx, dashboard_id)
    valid_ids = {str(w.id) for w in d.widgets}
    d.layout = [
        {k: item[k] for k in ("i", "x", "y", "w", "h") if k in item}
        for item in body.layout
        if str(item.get("i")) in valid_ids
    ]
    db.commit()
    return d


@router.delete("/dashboards/{dashboard_id}", status_code=204)
def delete_dashboard(dashboard_id: int, ctx: TenantContext = Depends(require_role("admin")),
                     db: Session = Depends(get_db)):
    db.delete(_dash(db, ctx, dashboard_id))
    db.commit()


# ---------- widgets ----------
@router.post("/dashboards/{dashboard_id}/widgets", response_model=WidgetOut, status_code=201)
def add_widget(dashboard_id: int, body: WidgetIn, ctx: TenantContext = Depends(require_role("admin")),
               db: Session = Depends(get_db)):
    d = _dash(db, ctx, dashboard_id)
    result = _run(db, ctx.org.id, body.sql)  # validate before saving
    w = Widget(dashboard_id=d.id, title=body.title, sql=result["sql"], chart=body.chart.model_dump())
    db.add(w)
    db.flush()
    bottom = max((item["y"] + item["h"] for item in d.layout), default=0)
    d.layout = [*d.layout, {"i": str(w.id), "x": 0, "y": bottom, "w": 6, "h": 8}]
    db.commit()
    db.refresh(w)
    return w


@router.put("/widgets/{widget_id}", response_model=WidgetOut)
def update_widget(widget_id: int, body: WidgetIn, ctx: TenantContext = Depends(require_role("admin")),
                  db: Session = Depends(get_db)):
    w = _widget(db, ctx, widget_id)
    result = _run(db, ctx.org.id, body.sql)
    w.title, w.sql, w.chart = body.title, result["sql"], body.chart.model_dump()
    db.commit()
    return w


@router.delete("/widgets/{widget_id}", status_code=204)
def delete_widget(widget_id: int, ctx: TenantContext = Depends(require_role("admin")),
                  db: Session = Depends(get_db)):
    w = _widget(db, ctx, widget_id)
    d = w.dashboard
    d.layout = [item for item in d.layout if item.get("i") != str(w.id)]
    db.delete(w)
    db.commit()


@router.get("/widgets/{widget_id}/data", response_model=QueryResult)
def widget_data(widget_id: int, ctx: TenantContext = Depends(require_role("viewer")), db: Session = Depends(get_db)):
    return _run(db, ctx.org.id, _widget(db, ctx, widget_id).sql)


# ---------- PDF export + schedules ----------
@router.post("/dashboards/{dashboard_id}/export")
async def export_pdf(dashboard_id: int, ctx: TenantContext = Depends(require_role("viewer")),
                     db: Session = Depends(get_db)):
    require_feature(ctx.org, "pdf_export")
    d = _dash(db, ctx, dashboard_id)
    from app.services.reports import print_url, render_pdf

    try:
        pdf = await render_pdf(print_url(d.id, ctx.org.id, ctx.user.id))
    except Exception as e:  # browser not installed, frontend not reachable, ...
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, f"PDF rendering failed: {e}")
    filename = f"{d.name.replace(' ', '_')}.pdf"
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/dashboards/{dashboard_id}/schedules", response_model=list[ScheduleOut])
def list_schedules(dashboard_id: int, ctx: TenantContext = Depends(require_role("admin")),
                   db: Session = Depends(get_db)):
    _dash(db, ctx, dashboard_id)
    return db.query(ReportSchedule).filter_by(dashboard_id=dashboard_id).all()


@router.post("/dashboards/{dashboard_id}/schedules", response_model=ScheduleOut, status_code=201)
def create_schedule(dashboard_id: int, body: ScheduleIn, ctx: TenantContext = Depends(require_role("admin")),
                    db: Session = Depends(get_db)):
    require_feature(ctx.org, "scheduled_reports")
    _dash(db, ctx, dashboard_id)
    s = ReportSchedule(org_id=ctx.org.id, dashboard_id=dashboard_id, frequency=body.frequency,
                       recipients=[str(r) for r in body.recipients] or [ctx.user.email])
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


@router.delete("/schedules/{schedule_id}", status_code=204)
def delete_schedule(schedule_id: int, ctx: TenantContext = Depends(require_role("admin")),
                    db: Session = Depends(get_db)):
    s = db.query(ReportSchedule).filter_by(id=schedule_id, org_id=ctx.org.id).first()
    if not s:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Schedule not found")
    db.delete(s)
    db.commit()
