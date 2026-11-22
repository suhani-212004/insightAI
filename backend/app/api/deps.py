"""Shared FastAPI dependencies: current user, current tenant, role checks.

Every tenant-scoped route depends on `require_role(...)`. It reads the org from
the `X-Org-Id` header, confirms the user is a member, and enforces the minimum
role. Routes then filter every query by `ctx.org.id`, so one org can never see
another org's rows.
"""
from dataclasses import dataclass
from typing import TypeVar

import jwt
from fastapi import Depends, Header, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import decode_token
from app.models import Membership, Organization, User

ROLE_RANK = {"viewer": 0, "admin": 1, "owner": 2}


@dataclass
class TenantContext:
    user: User
    org: Organization
    role: str

    def can(self, min_role: str) -> bool:
        return ROLE_RANK[self.role] >= ROLE_RANK[min_role]


def _token_from_request(authorization: str | None, token_qs: str | None) -> str:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization.split(" ", 1)[1]
    if token_qs:  # EventSource (SSE) cannot send headers, so it passes ?token=
        return token_qs
    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")


def _user_from_token(raw: str, db: Session) -> User:
    try:
        payload = decode_token(raw)
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
    if payload.get("scope") not in (None, "access"):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong token scope")
    user = db.get(User, int(payload["sub"]))
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found")
    return user


def get_current_user(authorization: str | None = Header(default=None), db: Session = Depends(get_db)) -> User:
    return _user_from_token(_token_from_request(authorization, None), db)


def get_current_user_sse(
    authorization: str | None = Header(default=None),
    token: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> User:
    """Same as get_current_user, but also accepts ?token= because EventSource can't set headers.
    Kept separate so tokens in URLs (which end up in access logs) only work for the stream."""
    return _user_from_token(_token_from_request(authorization, token), db)


def require_role(min_role: str = "viewer", *, allow_query_token: bool = False):
    user_dep = get_current_user_sse if allow_query_token else get_current_user

    def checker(
        user: User = Depends(user_dep),
        x_org_id: int | None = Header(default=None, alias="X-Org-Id"),
        org_id: int | None = Query(default=None),
        db: Session = Depends(get_db),
    ) -> TenantContext:
        oid = x_org_id or org_id
        if oid is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "X-Org-Id header is required")
        m = db.query(Membership).filter_by(user_id=user.id, org_id=oid).first()
        if not m:
            # 404 rather than 403 so we don't confirm that the org exists
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Organisation not found")
        if ROLE_RANK[m.role] < ROLE_RANK[min_role]:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Requires {min_role} role or higher")
        return TenantContext(user=user, org=m.organization, role=m.role)

    return checker


M = TypeVar("M")


def get_owned(db: Session, model: type[M], obj_id: int, org_id: int, label: str | None = None) -> M:
    """Fetch a row by id *within one org*, or 404.

    Every tenant-scoped lookup goes through here so the `org_id` filter can't be
    forgotten in a new route. Rows from another org look exactly like missing rows.
    """
    obj = db.query(model).filter_by(id=obj_id, org_id=org_id).first()
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{label or model.__name__} not found")
    return obj


@dataclass
class Page:
    limit: int
    offset: int

    def apply(self, query):
        return query.limit(self.limit).offset(self.offset)


def pagination(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> Page:
    """`?limit=&offset=` for list endpoints, so one big org can't pull every row at once."""
    return Page(limit=limit, offset=offset)
