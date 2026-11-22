from fastapi import APIRouter, Header, Query
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse

from app.api.deps import get_current_user_sse, require_role
from app.core.database import session_scope
from app.services.events import subscribe

router = APIRouter(tags=["realtime"])


def _authorise(authorization: str | None, token: str | None, x_org_id: int | None, org_id: int | None) -> int:
    # Not using Depends(get_db) here on purpose: that session would stay checked out
    # for as long as the browser keeps the stream open, and a handful of open tabs
    # would exhaust the connection pool. Check access, then give the connection back.
    with session_scope() as db:
        user = get_current_user_sse(authorization=authorization, token=token, db=db)
        ctx = require_role("viewer", allow_query_token=True)(user=user, x_org_id=x_org_id, org_id=org_id, db=db)
        return ctx.org.id


@router.get("/stream")
async def stream(
    authorization: str | None = Header(default=None),
    token: str | None = Query(default=None),
    x_org_id: int | None = Header(default=None, alias="X-Org-Id"),
    org_id: int | None = Query(default=None),
):
    """Server-Sent Events. Browser: new EventSource(`/api/v1/stream?token=...&org_id=...`)."""
    oid = await run_in_threadpool(_authorise, authorization, token, x_org_id, org_id)

    async def gen():
        yield 'data: {"type": "connected"}\n\n'
        async for chunk in subscribe(oid):
            yield chunk

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
