"""Stripe Checkout, Customer Portal and webhook handling."""
import stripe
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Organization


def _client():
    stripe.api_key = settings.STRIPE_SECRET_KEY
    return stripe


def price_for(plan: str) -> str:
    price = {"pro": settings.STRIPE_PRICE_PRO, "enterprise": settings.STRIPE_PRICE_ENTERPRISE}.get(plan)
    if not price:
        raise ValueError(f"No Stripe price configured for plan '{plan}'")
    return price


def plan_for_price(price_id: str | None) -> str:
    if price_id and price_id == settings.STRIPE_PRICE_ENTERPRISE:
        return "enterprise"
    if price_id and price_id == settings.STRIPE_PRICE_PRO:
        return "pro"
    return "free"


def ensure_customer(db: Session, org: Organization, email: str) -> str:
    if org.stripe_customer_id:
        return org.stripe_customer_id
    customer = _client().Customer.create(email=email, name=org.name, metadata={"org_id": str(org.id)})
    org.stripe_customer_id = customer.id
    db.commit()
    return customer.id


def create_checkout(db: Session, org: Organization, email: str, plan: str) -> str:
    s = _client()
    session = s.checkout.Session.create(
        mode="subscription",
        customer=ensure_customer(db, org, email),
        line_items=[{"price": price_for(plan), "quantity": 1}],
        success_url=f"{settings.FRONTEND_URL}/settings?billing=success",
        cancel_url=f"{settings.FRONTEND_URL}/settings?billing=cancelled",
        client_reference_id=str(org.id),
        metadata={"org_id": str(org.id), "plan": plan},
        subscription_data={"metadata": {"org_id": str(org.id)}},
    )
    return session.url


def create_portal(db: Session, org: Organization, email: str) -> str:
    session = _client().billing_portal.Session.create(
        customer=ensure_customer(db, org, email), return_url=f"{settings.FRONTEND_URL}/settings"
    )
    return session.url


def construct_event(payload: bytes, signature: str | None):
    return stripe.Webhook.construct_event(payload, signature or "", settings.STRIPE_WEBHOOK_SECRET or "")


def handle_event(db: Session, event: dict) -> str | None:
    """Apply a Stripe event to our database. Returns the org's new plan, if changed."""
    etype = event["type"]
    obj = event["data"]["object"]

    if etype == "checkout.session.completed":
        org = db.get(Organization, int(obj.get("client_reference_id") or obj["metadata"]["org_id"]))
        if not org:
            return None
        org.stripe_customer_id = obj.get("customer") or org.stripe_customer_id
        org.stripe_subscription_id = obj.get("subscription") or org.stripe_subscription_id
        org.plan = (obj.get("metadata") or {}).get("plan", org.plan)
        db.commit()
        return org.plan

    if etype in ("customer.subscription.created", "customer.subscription.updated", "customer.subscription.deleted"):
        org = _org_for_subscription(db, obj)
        if not org:
            return None
        if etype == "customer.subscription.deleted" or obj.get("status") in ("canceled", "unpaid", "incomplete_expired"):
            org.plan = "free"
            org.stripe_subscription_id = None
        else:
            items = (obj.get("items") or {}).get("data") or []
            price_id = items[0]["price"]["id"] if items else None
            org.plan = plan_for_price(price_id)
            org.stripe_subscription_id = obj.get("id")
        db.commit()
        return org.plan

    return None


def _org_for_subscription(db: Session, sub: dict) -> Organization | None:
    org_id = (sub.get("metadata") or {}).get("org_id")
    if org_id:
        return db.get(Organization, int(org_id))
    return db.query(Organization).filter_by(stripe_customer_id=sub.get("customer")).first()
