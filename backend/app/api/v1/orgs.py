from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import TenantContext, get_current_user, require_role
from app.core.database import get_db
from app.core.security import hash_password
from app.models import Membership, User
from app.schemas import InviteIn, MemberOut, OrgBrief, OrgCreate, RoleUpdate
from app.services.orgs import create_org, user_orgs
from app.services.plans import check_limit

router = APIRouter(prefix="/orgs", tags=["organisations"])


@router.get("", response_model=list[OrgBrief])
def list_orgs(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return user_orgs(db, user)


@router.post("", response_model=OrgBrief, status_code=201)
def new_org(body: OrgCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    org = create_org(db, body.name, user)
    return {"id": org.id, "name": org.name, "slug": org.slug, "plan": org.plan, "role": "owner"}


@router.get("/members", response_model=list[MemberOut])
def members(ctx: TenantContext = Depends(require_role("viewer")), db: Session = Depends(get_db)):
    rows = db.query(Membership, User).join(User).filter(Membership.org_id == ctx.org.id).order_by(User.email).all()
    return [{"user_id": u.id, "email": u.email, "full_name": u.full_name, "role": m.role} for m, u in rows]


@router.post("/members", response_model=MemberOut, status_code=201)
def invite(body: InviteIn, ctx: TenantContext = Depends(require_role("admin")), db: Session = Depends(get_db)):
    if body.role == "owner" and ctx.role != "owner":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only owners can add owners")
    check_limit(db, ctx.org, "members")
    email = body.email.lower()
    user = db.query(User).filter_by(email=email).first()
    if not user:
        if not body.password:
            # A production app would send an email invite link here.
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "User does not exist; provide a temporary password")
        user = User(email=email, full_name=email.split("@")[0], password_hash=hash_password(body.password))
        db.add(user)
        db.flush()
    if db.query(Membership).filter_by(user_id=user.id, org_id=ctx.org.id).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Already a member")
    db.add(Membership(user_id=user.id, org_id=ctx.org.id, role=body.role))
    db.commit()
    return {"user_id": user.id, "email": user.email, "full_name": user.full_name, "role": body.role}


def _owner_count(db: Session, org_id: int) -> int:
    return db.query(Membership).filter_by(org_id=org_id, role="owner").count()


@router.patch("/members/{user_id}", response_model=MemberOut)
def change_role(user_id: int, body: RoleUpdate, ctx: TenantContext = Depends(require_role("owner")),
                db: Session = Depends(get_db)):
    m = db.query(Membership).filter_by(user_id=user_id, org_id=ctx.org.id).first()
    if not m:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Member not found")
    if m.role == "owner" and body.role != "owner" and _owner_count(db, ctx.org.id) == 1:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "An organisation needs at least one owner")
    m.role = body.role
    db.commit()
    return {"user_id": m.user.id, "email": m.user.email, "full_name": m.user.full_name, "role": m.role}


@router.delete("/members/{user_id}", status_code=204)
def remove_member(user_id: int, ctx: TenantContext = Depends(require_role("admin")), db: Session = Depends(get_db)):
    m = db.query(Membership).filter_by(user_id=user_id, org_id=ctx.org.id).first()
    if not m:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Member not found")
    if m.role == "owner" and ctx.role != "owner":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only owners can remove owners")
    if m.role == "owner" and _owner_count(db, ctx.org.id) == 1:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "An organisation needs at least one owner")
    db.delete(m)
    db.commit()
