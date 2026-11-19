from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import TenantContext, require_role
from app.core.database import get_db
from app.models import ChatSession
from app.schemas import AskIn, AskOut, ChatMessageOut, ChatSessionOut
from app.services import ai_query
from app.services.plans import consume_ai_query

router = APIRouter(prefix="/ai", tags=["ai"])


@router.post("/ask", response_model=AskOut)
def ask(body: AskIn, ctx: TenantContext = Depends(require_role("viewer")), db: Session = Depends(get_db)):
    consume_ai_query(db, ctx.org)
    try:
        msg = ai_query.ask(db, ctx.org.id, ctx.user.id, body.question, body.session_id)
    except LookupError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e))
    return {"session_id": msg.session_id, "message": msg}


@router.get("/sessions", response_model=list[ChatSessionOut])
def sessions(ctx: TenantContext = Depends(require_role("viewer")), db: Session = Depends(get_db)):
    return (
        db.query(ChatSession)
        .filter_by(org_id=ctx.org.id, user_id=ctx.user.id)
        .order_by(ChatSession.id.desc())
        .limit(50)
        .all()
    )


@router.get("/sessions/{session_id}", response_model=list[ChatMessageOut])
def session_messages(session_id: int, ctx: TenantContext = Depends(require_role("viewer")),
                     db: Session = Depends(get_db)):
    s = db.query(ChatSession).filter_by(id=session_id, org_id=ctx.org.id, user_id=ctx.user.id).first()
    if not s:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Chat session not found")
    return s.messages


@router.delete("/sessions/{session_id}", status_code=204)
def delete_session(session_id: int, ctx: TenantContext = Depends(require_role("viewer")),
                   db: Session = Depends(get_db)):
    s = db.query(ChatSession).filter_by(id=session_id, org_id=ctx.org.id, user_id=ctx.user.id).first()
    if not s:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Chat session not found")
    db.delete(s)
    db.commit()
