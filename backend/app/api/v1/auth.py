from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.security import create_token, hash_password, verify_password
from app.models import User
from app.schemas import LoginIn, SignupIn, TokenOut, UserOut
from app.services.orgs import create_org, user_orgs

router = APIRouter(prefix="/auth", tags=["auth"])


def _token_response(db: Session, user: User) -> dict:
    return {
        "access_token": create_token(user.id, scope="access"),
        "user": UserOut.model_validate(user),
        "orgs": user_orgs(db, user),
    }


@router.post("/signup", response_model=TokenOut, status_code=201)
def signup(body: SignupIn, db: Session = Depends(get_db)):
    email = body.email.lower()
    if db.query(User).filter_by(email=email).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")
    user = User(email=email, full_name=body.full_name, password_hash=hash_password(body.password))
    db.add(user)
    db.flush()
    create_org(db, body.org_name, user)
    return _token_response(db, user)


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.query(User).filter_by(email=body.email.lower()).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password")
    return _token_response(db, user)


@router.get("/me", response_model=TokenOut)
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _token_response(db, user)
