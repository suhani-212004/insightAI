from sqlalchemy.orm import Session

from app.models import Membership, Organization, User
from app.services.ingestion import slugify
from app.services.tenancy import ensure_org_schema


def create_org(db: Session, name: str, owner: User, plan: str = "free") -> Organization:
    base = slugify(name, "org").replace("_", "-")
    slug, i = base, 1
    while db.query(Organization).filter_by(slug=slug).first():
        i += 1
        slug = f"{base}-{i}"
    org = Organization(name=name, slug=slug, plan=plan)
    db.add(org)
    db.flush()
    db.add(Membership(user_id=owner.id, org_id=org.id, role="owner"))
    db.commit()
    ensure_org_schema(org.id)
    return org


def user_orgs(db: Session, user: User) -> list[dict]:
    rows = (
        db.query(Membership, Organization)
        .join(Organization, Membership.org_id == Organization.id)
        .filter(Membership.user_id == user.id)
        .order_by(Organization.id)
        .all()
    )
    return [{"id": o.id, "name": o.name, "slug": o.slug, "plan": o.plan, "role": m.role} for m, o in rows]
