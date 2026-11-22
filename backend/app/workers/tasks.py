"""Background worker (ARQ + Redis).

Run:  arq app.workers.tasks.WorkerSettings

Cron jobs:
* every minute      - poll API connectors that are due
* every hour        - re-scan anomalies for orgs with the feature
* every day 07:00   - send scheduled PDF reports

The polling and scanning code is synchronous (SQLAlchemy, pandas, httpx), so each
job hands it to a thread with asyncio.to_thread. Otherwise one slow API or a big
table would block the worker's event loop and every other job would wait.
Each unit of work (one connector, one dataset) gets its own session so a failure
is isolated and doesn't roll back the rest of the batch.
"""
import asyncio
import logging
import os
import tempfile
from datetime import datetime, timedelta, timezone

from arq import cron
from arq.connections import RedisSettings

from app.core.config import settings
from app.core.database import session_scope
from app.models import Connector, Dataset, Membership, Organization, ReportSchedule
from app.services.anomaly import scan_dataset
from app.services.connectors import due_connectors, poll_connector
from app.services.plans import has_feature

log = logging.getLogger("worker")


# ---------- connector polling ----------
def _due_connector_ids() -> list[int]:
    with session_scope() as db:
        return [c.id for c in due_connectors(db)]


def _poll_one(connector_id: int) -> bool:
    try:
        with session_scope() as db:
            c = db.get(Connector, connector_id)
            if c is None:
                return False
            poll_connector(db, c)
            return True
    except Exception as e:
        # poll_connector already stored the error on the connector row
        log.warning("connector %s failed: %s", connector_id, e)
        return False


async def poll_due_connectors(ctx) -> int:
    ids = await asyncio.to_thread(_due_connector_ids)
    results = [await asyncio.to_thread(_poll_one, cid) for cid in ids]
    return sum(results)


# ---------- anomaly scans ----------
def _scannable_dataset_ids() -> list[int]:
    with session_scope() as db:
        org_ids = [o.id for o in db.query(Organization).all() if has_feature(o, "anomaly_detection")]
        if not org_ids:
            return []
        rows = db.query(Dataset).filter(Dataset.org_id.in_(org_ids)).all()
        return [d.id for d in rows if d.columns]


def _scan_one(dataset_id: int) -> bool:
    try:
        with session_scope() as db:
            d = db.get(Dataset, dataset_id)
            if d is None:
                return False
            scan_dataset(db, d)
            return True
    except Exception as e:
        log.warning("anomaly scan for dataset %s failed: %s", dataset_id, e)
        return False


async def rescan_anomalies(ctx) -> int:
    ids = await asyncio.to_thread(_scannable_dataset_ids)
    results = [await asyncio.to_thread(_scan_one, did) for did in ids]
    return sum(results)


# ---------- scheduled reports ----------
def _is_due(s: ReportSchedule, now: datetime) -> bool:
    if s.last_sent_at is None:
        return True
    gap = timedelta(days=7 if s.frequency == "weekly" else 1) - timedelta(hours=1)
    return now - s.last_sent_at >= gap


def report_dir() -> str:
    path = os.environ.get("REPORT_DIR") or os.path.join(tempfile.gettempdir(), "insightai_reports")
    os.makedirs(path, exist_ok=True)
    return path


async def send_scheduled_reports(ctx) -> int:
    from app.services.reports import print_url, render_pdf

    now = datetime.now(timezone.utc)
    with session_scope() as db:
        jobs = []
        for s in db.query(ReportSchedule).all():
            if not _is_due(s, now):
                continue
            owner = db.query(Membership).filter_by(org_id=s.org_id, role="owner").first()
            if owner:
                jobs.append((s.id, s.dashboard_id, s.org_id, owner.user_id, list(s.recipients)))

    sent = 0
    for schedule_id, dashboard_id, org_id, user_id, recipients in jobs:
        try:
            pdf = await render_pdf(print_url(dashboard_id, org_id, user_id))
        except Exception as e:
            log.warning("report %s failed: %s", schedule_id, e)
            continue
        # Plug in an email provider here (SES, Resend, SendGrid...). For the
        # project demo we save the file so it can be inspected.
        path = os.path.join(report_dir(), f"report_{schedule_id}_{now:%Y%m%d}.pdf")
        with open(path, "wb") as f:
            f.write(pdf)
        log.info("report %s written to %s for %s", schedule_id, path, recipients)
        with session_scope() as db:
            s = db.get(ReportSchedule, schedule_id)
            if s:
                s.last_sent_at = now
        sent += 1
    return sent


class WorkerSettings:
    redis_settings = RedisSettings.from_dsn(settings.REDIS_URL)
    functions = [poll_due_connectors, rescan_anomalies, send_scheduled_reports]
    cron_jobs = [
        cron(poll_due_connectors, second=0),
        cron(rescan_anomalies, minute=5, second=0),
        cron(send_scheduled_reports, hour=7, minute=0, second=0),
    ]
