"""Background worker (ARQ + Redis).

Run:  arq app.workers.tasks.WorkerSettings

Cron jobs:
* every minute      - poll API connectors that are due
* every hour        - re-scan anomalies for orgs with the feature
* every day 07:00   - send scheduled PDF reports
"""
import logging
from datetime import datetime, timedelta, timezone

from arq import cron
from arq.connections import RedisSettings

from app.core.config import settings
from app.core.database import SessionLocal
from app.models import Dataset, Organization, ReportSchedule
from app.services.anomaly import scan_dataset
from app.services.connectors import due_connectors, poll_connector
from app.services.plans import PLANS

log = logging.getLogger("worker")


async def poll_due_connectors(ctx) -> int:
    db = SessionLocal()
    n = 0
    try:
        for c in due_connectors(db):
            try:
                poll_connector(db, c)
                n += 1
            except Exception as e:
                log.warning("connector %s failed: %s", c.id, e)
    finally:
        db.close()
    return n


async def rescan_anomalies(ctx) -> int:
    db = SessionLocal()
    n = 0
    try:
        orgs = [o for o in db.query(Organization).all() if "anomaly_detection" in PLANS[o.plan]["features"]]
        for org in orgs:
            for d in db.query(Dataset).filter_by(org_id=org.id).all():
                if d.columns:
                    scan_dataset(db, d)
                    n += 1
    finally:
        db.close()
    return n


def _is_due(s: ReportSchedule, now: datetime) -> bool:
    if s.last_sent_at is None:
        return True
    gap = timedelta(days=7 if s.frequency == "weekly" else 1) - timedelta(hours=1)
    return now - s.last_sent_at >= gap


async def send_scheduled_reports(ctx) -> int:
    from app.models import Membership
    from app.services.reports import print_url, render_pdf

    db = SessionLocal()
    sent = 0
    now = datetime.now(timezone.utc)
    try:
        for s in db.query(ReportSchedule).all():
            if not _is_due(s, now):
                continue
            owner = db.query(Membership).filter_by(org_id=s.org_id, role="owner").first()
            if not owner:
                continue
            try:
                pdf = await render_pdf(print_url(s.dashboard_id, s.org_id, owner.user_id))
            except Exception as e:
                log.warning("report %s failed: %s", s.id, e)
                continue
            # Plug in an email provider here (SES, Resend, SendGrid...). For the
            # project demo we save the file so it can be inspected.
            path = f"/tmp/report_{s.id}_{now:%Y%m%d}.pdf"
            with open(path, "wb") as f:
                f.write(pdf)
            log.info("report %s written to %s for %s", s.id, path, s.recipients)
            s.last_sent_at = now
            db.commit()
            sent += 1
    finally:
        db.close()
    return sent


class WorkerSettings:
    redis_settings = RedisSettings.from_dsn(settings.REDIS_URL)
    functions = [poll_due_connectors, rescan_anomalies, send_scheduled_reports]
    cron_jobs = [
        cron(poll_due_connectors, second=0),
        cron(rescan_anomalies, minute=5, second=0),
        cron(send_scheduled_reports, hour=7, minute=0, second=0),
    ]
