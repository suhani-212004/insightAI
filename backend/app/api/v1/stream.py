from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.api.deps import TenantContext, require_role
from app.services.events import subscribe

router = APIRouter(tags=["realtime"])


@router.get("/stream")
async def stream(ctx: TenantContext = Depends(require_role("viewer"))):
    """Server-Sent Events. Browser: new EventSource(`/api/v1/stream?token=...&org_id=...`)."""
    org_id = ctx.org.id

    async def gen():
        yield 'data: {"type": "connected"}\n\n'
        async for chunk in subscribe(org_id):
            yield chunk

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
