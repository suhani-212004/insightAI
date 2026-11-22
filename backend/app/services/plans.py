"""Subscription plans and feature gates.

`None` means unlimited. Routes call `check_limit` / `require_feature` before
doing anything that a plan restricts.
"""
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models import Connector, Dataset, Membership, Organization, UsageCounter

PLANS: dict[str, dict] = {
    "free": {
        "price_usd": 0,
        "datasets": 3,
        "members": 3,
        "ai_queries_per_day": 25,
        "dashboards": 2,
        "features": {"csv_upload"},
    },
    "pro": {
        "price_usd": 29,
        "datasets": 25,
        "members": 15,
        "ai_queries_per_day": 500,
        "dashboards": 20,
        "features": {"csv_upload", "api_connectors", "webhooks", "pdf_export", "anomaly_detection"},
    },
    "enterprise": {
        "price_usd": 199,
        "datasets": None,
        "members": None,
        "ai_queries_per_day": None,
        "dashboards": None,
        "features": {"csv_upload", "api_connectors", "webhooks", "pdf_export", "anomaly_detection",
                     "scheduled_reports"},
    },
}


def plan_limits(plan: str) -> dict:
    p = PLANS.get(plan, PLANS["free"])
    return {**p, "features": sorted(p["features"])}


def has_feature(org: Organization, feature: str) -> bool:
    # Unknown plan names (e.g. a typo from a Stripe webhook) fall back to free instead of crashing.
    return feature in PLANS.get(org.plan, PLANS["free"])["features"]


def require_feature(org: Organization, feature: str) -> None:
    if not has_feature(org, feature):
        raise HTTPException(
            status.HTTP_402_PAYMENT_REQUIRED,
            f"'{feature}' is not available on the {org.plan} plan. Upgrade to unlock it.",
        )


def current_usage(db: Session, org: Organization) -> dict:
    from app.models import Dashboard

    counter = _counter(db, org.id, "ai_queries")
    return {
        "datasets": db.query(Dataset).filter_by(org_id=org.id).count(),
        "members": db.query(Membership).filter_by(org_id=org.id).count(),
        "dashboards": db.query(Dashboard).filter_by(org_id=org.id).count(),
        "connectors": db.query(Connector).filter_by(org_id=org.id).count(),
        "ai_queries_today": counter.count if counter else 0,
    }


def check_limit(db: Session, org: Organization, resource: str) -> None:
    """Raise 402 if creating one more `resource` would exceed the plan."""
    limit = PLANS.get(org.plan, PLANS["free"]).get(resource)
    if limit is None:
        return
    used = current_usage(db, org)[resource]
    if used >= limit:
        raise HTTPException(
            status.HTTP_402_PAYMENT_REQUIRED,
            f"Your {org.plan} plan allows {limit} {resource}. Upgrade to add more.",
        )


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _counter(db: Session, org_id: int, metric: str) -> UsageCounter | None:
    return db.query(UsageCounter).filter_by(org_id=org_id, metric=metric, day=_today()).first()


def consume_ai_query(db: Session, org: Organization) -> None:
    limit = PLANS.get(org.plan, PLANS["free"])["ai_queries_per_day"]
    c = _counter(db, org.id, "ai_queries")
    if c is None:
        c = UsageCounter(org_id=org.id, metric="ai_queries", day=_today(), count=0)
        db.add(c)
    if limit is not None and c.count >= limit:
        raise HTTPException(
            status.HTTP_402_PAYMENT_REQUIRED,
            f"Daily AI query limit ({limit}) reached on the {org.plan} plan.",
        )
    c.count += 1
    db.commit()


def refund_ai_query(db: Session, org: Organization) -> None:
    c = _counter(db, org.id, "ai_queries")
    if c and c.count > 0:
        c.count -= 1
        db.commit()
