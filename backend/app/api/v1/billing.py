import logging

import stripe
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.deps import TenantContext, require_role
from app.core.config import settings
from app.core.database import get_db
from app.schemas import CheckoutIn, PlanOut
from app.services import billing, events
from app.services.plans import PLANS, current_usage, plan_limits

log = logging.getLogger(__name__)
router = APIRouter(prefix="/billing", tags=["billing"])


@router.get("/plans")
def all_plans():
    return {name: plan_limits(name) for name in PLANS}


@router.get("", response_model=PlanOut)
def my_plan(ctx: TenantContext = Depends(require_role("viewer")), db: Session = Depends(get_db)):
    return {
        "plan": ctx.org.plan,
        "limits": plan_limits(ctx.org.plan),
        "usage": current_usage(db, ctx.org),
        "stripe_enabled": settings.stripe_enabled,
    }


@router.post("/checkout")
def checkout(body: CheckoutIn, ctx: TenantContext = Depends(require_role("owner")), db: Session = Depends(get_db)):
    if not settings.stripe_enabled:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Stripe is not configured")
    try:
        return {"url": billing.create_checkout(db, ctx.org, ctx.user.email, body.plan)}
    except (ValueError, stripe.StripeError) as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))


@router.post("/portal")
def portal(ctx: TenantContext = Depends(require_role("owner")), db: Session = Depends(get_db)):
    if not settings.stripe_enabled:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Stripe is not configured")
    return {"url": billing.create_portal(db, ctx.org, ctx.user.email)}


@router.post("/webhook")
async def stripe_webhook(request: Request, stripe_signature: str | None = Header(default=None),
                         db: Session = Depends(get_db)):
    payload = await request.body()
    try:
        event = billing.construct_event(payload, stripe_signature)
    except (ValueError, stripe.SignatureVerificationError):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid signature")
    new_plan = billing.handle_event(db, event.to_dict() if hasattr(event, "to_dict") else event)
    log.info("stripe event %s -> plan %s", event["type"], new_plan)
    return {"received": True}


@router.post("/dev/set-plan")
def dev_set_plan(body: dict, ctx: TenantContext = Depends(require_role("owner")),
                 db: Session = Depends(get_db)):
    """Local-only shortcut to switch plans without Stripe. Disabled in production."""
    if settings.ENV == "prod":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    plan = body.get("plan")
    if plan not in PLANS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown plan")
    ctx.org.plan = plan
    db.commit()
    events.publish(ctx.org.id, "billing.updated", plan=plan)
    return {"plan": plan}
